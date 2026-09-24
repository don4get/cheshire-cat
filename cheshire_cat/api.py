"""JSON API consumed by the Dioxus dashboard.

The API is optional because the research and ingestion workflows do not need a
web server. Start it with ``uv run cheshire-cat api`` when serving the Rust UI.
"""

from __future__ import annotations

from datetime import date, timedelta
from threading import Lock
from time import monotonic
from typing import Any

import pandas as pd
from sqlalchemy import func, select

from .challenger_jobs import challenger_status, submit_challenger
from .dashboard import dashboard_data, fundamental_metrics, portfolio_valuation
from .database import (
    FinancialReport,
    FundamentalFact,
    FundamentalIngestionState,
    PortfolioTransaction,
    Price,
    TickerSymbol,
    create_schema,
    get_engine,
)
from .fundamental_ratios import compute_fundamental_ratios, relevant_concepts
from .fundamental_coverage import audit_fundamental_coverage
from .fundamentals_asof import AsOfPolicy, compute_asof_features
from .fundamental_research import run_fundamental_experiment
from .playground import run_playground
from .portfolio_timeline import portfolio_snapshot, submit_timeline, timeline_status
from .recommendations import suggest_investments
from .research_jobs import latest_run, submit_run
from .universe_snapshots import load_universe_snapshot
from .validation_jobs import audit_status, submit_audit

FUNDAMENTAL_SNAPSHOT_LIMIT = 2_000


def create_app(database_url: str | None = None):
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel, Field
    except ImportError as exc:
        raise RuntimeError("Install API support with `uv sync --extra api`.") from exc

    class TradeRequest(BaseModel):
        portfolio: str = Field(min_length=1, max_length=128)
        symbol: str = Field(min_length=1, max_length=32)
        trade_date: date
        quantity: float
        price: float = Field(gt=0)
        fees: float = Field(default=0, ge=0)

    app = FastAPI(title="Cheshire Cat market data API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8080", "http://localhost:8080"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    create_schema(database_url)
    universe_cache: dict[str, Any] = {"expires_at": 0.0, "rows": [], "price_symbols": []}
    universe_cache_lock = Lock()

    def cached_universe() -> tuple[list[dict[str, Any]], list[str]]:
        """Cache expensive coverage aggregates while ingestion is running."""

        now = monotonic()
        if universe_cache["expires_at"] > now:
            return universe_cache["rows"], universe_cache["price_symbols"]
        with universe_cache_lock:
            if universe_cache["expires_at"] > monotonic():
                return universe_cache["rows"], universe_cache["price_symbols"]
            with get_engine(database_url).connect() as connection:
                price_counts = (
                    select(Price.symbol, func.count(Price.id).label("price_rows"))
                    .group_by(Price.symbol)
                    .subquery()
                )
                fundamental_counts = (
                    select(FundamentalFact.symbol, func.count(FundamentalFact.id).label("fundamental_rows"))
                    .group_by(FundamentalFact.symbol)
                    .subquery()
                )
                report_counts = (
                    select(FinancialReport.symbol, func.count(FinancialReport.id).label("report_rows"))
                    .group_by(FinancialReport.symbol)
                    .subquery()
                )
                rows = connection.execute(
                    select(
                        TickerSymbol.symbol,
                        TickerSymbol.exchange,
                        TickerSymbol.name,
                        TickerSymbol.sector,
                        func.coalesce(price_counts.c.price_rows, 0).label("price_rows"),
                        func.coalesce(fundamental_counts.c.fundamental_rows, 0).label("fundamental_rows"),
                        func.coalesce(report_counts.c.report_rows, 0).label("report_rows"),
                    )
                    .select_from(TickerSymbol)
                    .outerjoin(price_counts, price_counts.c.symbol == TickerSymbol.symbol)
                    .outerjoin(fundamental_counts, fundamental_counts.c.symbol == TickerSymbol.symbol)
                    .outerjoin(report_counts, report_counts.c.symbol == TickerSymbol.symbol)
                    .order_by(TickerSymbol.symbol)
                ).mappings().all()
                price_symbols = connection.execute(
                    select(Price.symbol).distinct().order_by(Price.symbol)
                ).scalars().all()
            universe_cache["rows"] = [dict(row) for row in rows]
            universe_cache["price_symbols"] = price_symbols
            universe_cache["expires_at"] = monotonic() + 60.0
            return universe_cache["rows"], universe_cache["price_symbols"]

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/dashboard")
    def get_dashboard(symbol: str | None = None) -> dict[str, Any]:
        universe_rows, price_symbols = cached_universe()
        selected_symbol = symbol or (price_symbols[0] if price_symbols else None)
        selected_metadata = next(
            (row for row in universe_rows if row["symbol"] == (selected_symbol or "").upper()),
            None,
        )
        selected_exchange = selected_metadata["exchange"] if selected_metadata else None
        data = dashboard_data(
            database_url,
            selected_symbol,
            fundamental_limit=FUNDAMENTAL_SNAPSHOT_LIMIT,
        )
        prices = data["prices"]
        facts = data["fundamentals"]
        valuation = portfolio_valuation(data)
        tracked_symbols = {row["symbol"] for row in universe_rows}
        symbols = sorted(
            tracked_symbols
            | (set(price_symbols) & tracked_symbols)
            | (set(prices.get("symbol", pd.Series(dtype=str)).dropna()) & tracked_symbols)
        )
        metrics = fundamental_metrics(prices)
        last_price = None
        if not metrics.empty:
            last_price = metrics.iloc[0].get("last_price")
        if last_price is None and not prices.empty:
            last_price = prices.iloc[-1].get("adj_close") or prices.iloc[-1].get("close")
        sector = selected_metadata.get("sector") if selected_metadata else None
        ratio_facts = _selected_ratio_facts(database_url, selected_symbol)
        peer_rows = [
            row
            for row in universe_rows
            if sector
            and row.get("sector") == sector
            and row["symbol"] != (selected_symbol or "").upper()
            and row["price_rows"] > 0
            and row["fundamental_rows"] > 0
        ][:12]
        return {
            "symbols": symbols,
            "universe": [dict(row) for row in universe_rows],
            "selected_symbol": selected_symbol.upper() if selected_symbol else None,
            "selected_exchange": selected_exchange,
            "prices": _records(prices),
            "metrics": _records(metrics),
            "fundamentals": _records(facts),
            "fundamental_total": selected_metadata["fundamental_rows"] if selected_metadata else len(facts),
            "fundamentals_truncated": bool(selected_metadata and selected_metadata["fundamental_rows"] > len(facts)),
            "reports": _records(data["reports"]),
            "portfolio": _records(valuation.reset_index()) if not valuation.empty else [],
            "sector": sector,
            "fundamental_ratios": compute_fundamental_ratios(ratio_facts, last_price),
            "sector_peers": _peer_comparison(database_url, peer_rows),
        }

    @app.get("/api/playground")
    def get_playground(
        symbols: str | None = None,
        years: int = 20,
        initial_cash: float = 100_000.0,
        transaction_cost: float = 0.001,
    ) -> dict[str, Any]:
        """Compare registered bots on the same stored price history."""

        if not 1 <= years <= 20:
            raise HTTPException(status_code=400, detail="years must be between 1 and 20")
        if initial_cash <= 0:
            raise HTTPException(status_code=400, detail="initial_cash must be positive")
        if not 0 <= transaction_cost < 1:
            raise HTTPException(status_code=400, detail="transaction_cost must be between 0 and 1")

        requested_symbols = list(
            dict.fromkeys(
                item.strip().upper()
                for item in (symbols or "").split(",")
                if item.strip()
            )
        )
        with get_engine(database_url).connect() as connection:
            if not requested_symbols:
                default_symbol = connection.execute(
                    select(Price.symbol).order_by(Price.date.desc(), Price.symbol).limit(1)
                ).scalar()
                requested_symbols = [default_symbol] if default_symbol else []
            if len(requested_symbols) > 25:
                raise HTTPException(status_code=400, detail="A playground run supports at most 25 symbols")
            latest_date = connection.execute(
                select(func.max(Price.date)).where(Price.symbol.in_(requested_symbols))
            ).scalar()
            if latest_date is None:
                raise HTTPException(status_code=404, detail="No stored prices for the requested symbols")
            start_date = latest_date - timedelta(days=round(years * 365.25))
            rows = connection.execute(
                select(Price.date, Price.symbol, Price.close, Price.adj_close)
                .where(
                    Price.symbol.in_(requested_symbols),
                    Price.date >= start_date,
                    Price.date <= latest_date,
                )
                .order_by(Price.date, Price.symbol)
            ).mappings().all()
        prices = pd.DataFrame([dict(row) for row in rows])
        if prices.empty:
            raise HTTPException(status_code=404, detail="No stored prices in the requested period")
        annualization = _price_annualization(prices)
        result = run_playground(
            prices,
            initial_cash=initial_cash,
            transaction_cost=transaction_cost,
            annualization=annualization,
        )
        result["requested_years"] = years
        result["fundamental_readiness"] = _fundamental_readiness(
            database_url, requested_symbols, latest_date
        )
        return result

    @app.get("/api/fundamentals/readiness")
    def get_fundamental_readiness(
        symbols: str | None = None,
        as_of: date | None = None,
        max_staleness_days: int = 548,
    ) -> dict[str, Any]:
        requested = [
            item.strip().upper()
            for item in (symbols or "").split(",")
            if item.strip()
        ]
        if len(requested) > 100:
            raise HTTPException(status_code=400, detail="At most 100 symbols may be audited")
        if max_staleness_days < 1 or max_staleness_days > 3_650:
            raise HTTPException(status_code=400, detail="max_staleness_days must be between 1 and 3650")
        if not requested:
            _, price_symbols = cached_universe()
            requested = price_symbols[:25]
        cutoff = as_of or _latest_price_date(database_url, requested)
        if cutoff is None:
            raise HTTPException(status_code=404, detail="No stored prices for the requested symbols")
        return _fundamental_readiness(
            database_url, requested, cutoff, max_staleness_days=max_staleness_days
        )

    @app.get("/api/fundamentals/coverage")
    def get_fundamental_coverage(
        dates: str,
        max_staleness_days: int = 548,
        symbols: str | None = None,
    ) -> dict[str, Any]:
        requested_dates = [item.strip() for item in dates.split(",") if item.strip()]
        if not requested_dates or len(requested_dates) > 260:
            raise HTTPException(status_code=400, detail="Provide between 1 and 260 decision dates")
        requested_symbols = list(dict.fromkeys(
            item.strip().upper() for item in (symbols or "").split(",") if item.strip()
        ))
        if len(requested_symbols) > 100:
            raise HTTPException(status_code=400, detail="At most 100 symbols may be audited")
        with get_engine(database_url).connect() as connection:
            universe_query = select(TickerSymbol.symbol, TickerSymbol.exchange.label("market")).order_by(TickerSymbol.symbol)
            if requested_symbols:
                universe_query = universe_query.where(TickerSymbol.symbol.in_(requested_symbols))
            else:
                # Coverage is an expensive inventory operation. Keep an
                # interactive request bounded and make larger audits explicit
                # through a symbol batch or the CLI.
                universe_query = universe_query.limit(100)
            universe_rows = connection.execute(universe_query).mappings().all()
            selected_symbols = [row["symbol"] for row in universe_rows]
            fact_query = select(
                FundamentalFact.symbol, FundamentalFact.taxonomy, FundamentalFact.concept,
                FundamentalFact.unit, FundamentalFact.currency, FundamentalFact.period_start, FundamentalFact.period_end,
                FundamentalFact.filed, FundamentalFact.form, FundamentalFact.frame,
                FundamentalFact.value, FundamentalFact.source_url,
                FundamentalFact.source_document_id, FundamentalFact.source_version,
                FundamentalFact.context_ref, FundamentalFact.available_on,
                FundamentalFact.available_at, FundamentalFact.availability_status,
                FundamentalFact.statement_kind, FundamentalFact.duration_days,
            ).where(FundamentalFact.symbol.in_(selected_symbols))
            fact_rows = connection.execute(fact_query).mappings().all()
            report_rows = connection.execute(
                select(
                    FinancialReport.symbol,
                    FinancialReport.form,
                    FinancialReport.filing_date,
                    FinancialReport.period_end,
                    FinancialReport.source_url,
                ).where(FinancialReport.symbol.in_(selected_symbols))
            ).mappings().all()
            ingestion_rows = connection.execute(
                select(
                    FundamentalIngestionState.source,
                    FundamentalIngestionState.symbol,
                    FundamentalIngestionState.status,
                    FundamentalIngestionState.rows_ingested,
                    FundamentalIngestionState.attempted_at,
                    FundamentalIngestionState.completed_at,
                    FundamentalIngestionState.last_error,
                ).where(FundamentalIngestionState.symbol.in_(selected_symbols))
            ).mappings().all()
        report = audit_fundamental_coverage(
            [dict(row) for row in fact_rows],
            requested_dates,
            universe=[dict(row) for row in universe_rows],
            policy=AsOfPolicy(max_staleness_days=max_staleness_days),
            reports=[dict(row) for row in report_rows],
            ingestion_states=[dict(row) for row in ingestion_rows],
        )
        report["request_scope"] = {
            "symbols": selected_symbols,
            "bounded_default_cohort": not bool(requested_symbols),
            "max_symbols": 100,
        }
        return report

    @app.get("/api/recommendations")
    def get_recommendations(
        portfolio: str,
        amount: float,
        strategy: str = "equal_weight",
    ) -> dict[str, Any]:
        if amount <= 0:
            raise HTTPException(status_code=400, detail="amount must be positive")
        with get_engine(database_url).connect() as connection:
            transactions = connection.execute(
                select(
                    PortfolioTransaction.symbol,
                    func.sum(PortfolioTransaction.quantity).label("quantity"),
                )
                .where(PortfolioTransaction.portfolio == portfolio)
                .group_by(PortfolioTransaction.symbol)
            ).mappings().all()
            symbols = [str(row["symbol"]).upper() for row in transactions]
            price_rows = connection.execute(
                select(Price.symbol, Price.close, Price.adj_close, Price.date)
                .where(Price.symbol.in_(symbols))
                .order_by(Price.date.desc())
            ).mappings().all()
        prices = {}
        for row in price_rows:
            prices.setdefault(row["symbol"], row["adj_close"] or row["close"])
        try:
            return suggest_investments(
                [dict(row) for row in transactions], amount, strategy=strategy, prices=prices
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/fundamentals/research")
    def get_fundamental_research(
        symbols: str,
        years: int = 10,
        initial_cash: float = 100_000.0,
        transaction_cost: float = 0.001,
        search_budget: int = 8,
        persist: bool = False,
        universe_snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        """Run matched fundamental/price/hybrid candidates on stored data."""

        requested = list(dict.fromkeys(item.strip().upper() for item in symbols.split(",") if item.strip()))
        if not requested or len(requested) > 100:
            raise HTTPException(status_code=400, detail="Provide between 1 and 100 symbols")
        if not 5 <= years <= 20:
            raise HTTPException(status_code=400, detail="years must be between 5 and 20")
        if initial_cash <= 0 or not 0 <= transaction_cost < 0.1:
            raise HTTPException(status_code=400, detail="Invalid cash or transaction cost")
        with get_engine(database_url).connect() as connection:
            rows = connection.execute(
                select(Price.date, Price.symbol, Price.close, Price.adj_close, Price.volume)
                .where(Price.symbol.in_(requested))
                .order_by(Price.date, Price.symbol)
            ).mappings().all()
            facts = connection.execute(
                select(
                    FundamentalFact.symbol, FundamentalFact.taxonomy, FundamentalFact.concept,
                    FundamentalFact.unit, FundamentalFact.currency, FundamentalFact.period_start, FundamentalFact.period_end,
                    FundamentalFact.filed, FundamentalFact.form, FundamentalFact.frame,
                    FundamentalFact.value, FundamentalFact.source_url,
                    FundamentalFact.source_document_id, FundamentalFact.source_version,
                    FundamentalFact.context_ref, FundamentalFact.available_on,
                    FundamentalFact.available_at, FundamentalFact.availability_status,
                    FundamentalFact.statement_kind, FundamentalFact.duration_days,
                ).where(FundamentalFact.symbol.in_(requested))
            ).mappings().all()
            sector_rows = connection.execute(
                select(TickerSymbol.symbol, TickerSymbol.sector).where(TickerSymbol.symbol.in_(requested))
            ).mappings().all()
        prices = pd.DataFrame([dict(row) for row in rows])
        if prices.empty:
            raise HTTPException(status_code=404, detail="No stored prices for requested symbols")
        prices["volume"] = pd.to_numeric(prices["volume"], errors="coerce").fillna(0)
        prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
        prices["adj_close"] = pd.to_numeric(prices["adj_close"], errors="coerce").fillna(prices["close"])
        try:
            from .research import prepare_panel

            panel = prepare_panel(
                prices,
                metadata={"market": "requested-cohort", "currency": "mixed", "source": "stored-prices"},
            )
            if universe_snapshot_id is not None:
                snapshot = load_universe_snapshot(universe_snapshot_id, database_url)
                if snapshot is None:
                    raise HTTPException(status_code=404, detail="Universe snapshot not found")
                allowed = {
                    row["symbol"]
                    for row in snapshot["memberships"]
                    if row.get("membership_status") == "active"
                    and row.get("price_eligible") is not False
                }
                panel.universe_mask = pd.DataFrame(
                    [panel.close.columns.to_series().isin(allowed).to_numpy()] * len(panel.close),
                    index=panel.close.index,
                    columns=panel.close.columns,
                )
                panel.metadata["universe_snapshot_id"] = universe_snapshot_id
            end = panel.close.index.max()
            start_date = end - pd.Timedelta(days=round(years * 365.25))
            # Keep the warm-up bars needed by momentum, volatility and
            # liquidity filters. Trimming the panel before feature generation
            # silently turned the first research weeks into zero-history rows.
            start = max(1, int(panel.close.index.searchsorted(start_date)))
            panel.close = panel.close.loc[:end]
            panel.liquidity = panel.liquidity.loc[panel.close.index]
            if len(panel.close) - start < 20:
                raise ValueError("Not enough matched weekly history")
            feature_rows = []
            for decision_date in panel.close.index:
                snapshot = compute_asof_features(
                    [dict(row) for row in facts],
                    prices,
                    decision_date.date(),
                    symbols=requested,
                    sector_by_symbol={row["symbol"]: row["sector"] for row in sector_rows},
                )
                if not snapshot.empty:
                    feature_rows.append(snapshot)
            features = pd.concat(feature_rows, ignore_index=True) if feature_rows else pd.DataFrame()
            report = run_fundamental_experiment(
                panel,
                features,
                start,
                initial_cash=initial_cash,
                transaction_cost=transaction_cost,
                universe_snapshot_id=universe_snapshot_id,
                sector_by_symbol={row["symbol"]: row["sector"] for row in sector_rows},
                search_budget=search_budget,
            )
            if persist:
                from .fundamental_research_jobs import create_run, save_result

                run_id = create_run(database_url, "requested-cohort", report["manifest"])
                saved = save_result(database_url, run_id, report)
                report["run_id"] = saved["id"]
            return report
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/fundamentals/research/{run_id}")
    def get_saved_fundamental_research(run_id: str) -> dict[str, Any]:
        from .fundamental_research_jobs import get_run

        saved = get_run(database_url, run_id)
        if saved is None:
            raise HTTPException(status_code=404, detail="Fundamental research run not found")
        return saved

    @app.get("/api/research")
    def get_research(market: str = "NASDAQ", run_id: str | None = None) -> dict[str, Any]:
        if market not in {"NASDAQ", "EURONEXT_PARIS"}:
            raise HTTPException(status_code=400, detail="Unknown research market")
        return latest_run(database_url, market, run_id) or {
            "status": "not_started", "market": market, "progress": "Start a research run to train and validate the bot",
        }

    @app.post("/api/research", status_code=202)
    def start_research(market: str = "NASDAQ") -> dict[str, Any]:
        if market not in {"NASDAQ", "EURONEXT_PARIS"}:
            raise HTTPException(status_code=400, detail="Unknown research market")
        run_id = submit_run(database_url, market)
        return {"id": run_id, "status": "accepted", "market": market}

    @app.get("/api/research/selection")
    def get_research_selection(market: str = "NASDAQ") -> dict[str, Any]:
        if market not in {"NASDAQ", "EURONEXT_PARIS"}:
            raise HTTPException(status_code=400, detail="Unknown research market")
        run = latest_run(database_url, market)
        if not run or run["status"] != "complete":
            raise HTTPException(status_code=404, detail="No completed selection for this market")
        result = run["result"]
        return {
            "run_id": run["id"], "market": market, "currency": result["currency"],
            "version": result["version"], "split": result["split"],
            "parameters": run["parameters"], "selection": result["selection"],
            "data_fingerprint": result["data_fingerprint"],
        }

    @app.get("/api/research/{run_id}/portfolios")
    def get_portfolio_timeline(run_id: str, on_date: date | None = None) -> dict[str, Any]:
        if on_date is None:
            return timeline_status(database_url, run_id)
        snapshot = portfolio_snapshot(database_url, run_id, on_date)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="No portfolio snapshot for this date")
        return snapshot

    @app.post("/api/research/{run_id}/portfolios", status_code=202)
    def prepare_portfolio_timeline(run_id: str) -> dict[str, Any]:
        from .database import ResearchRun

        with get_engine(database_url).connect() as connection:
            status = connection.execute(select(ResearchRun.status).where(ResearchRun.id == run_id)).scalar_one_or_none()
        if status != "complete":
            raise HTTPException(status_code=404, detail="A completed research run is required")
        return submit_timeline(database_url, run_id)

    @app.get("/api/research/{run_id}/validation")
    def get_validation_audit(run_id: str) -> dict[str, Any]:
        return audit_status(database_url, run_id)

    @app.post("/api/research/{run_id}/validation", status_code=202)
    def prepare_validation_audit(run_id: str) -> dict[str, Any]:
        from .database import ResearchRun

        with get_engine(database_url).connect() as connection:
            status = connection.execute(select(ResearchRun.status).where(ResearchRun.id == run_id)).scalar_one_or_none()
        if status != "complete":
            raise HTTPException(status_code=404, detail="A completed research run is required")
        return submit_audit(database_url, run_id)

    @app.get("/api/research/{run_id}/challenger")
    def get_challenger(run_id: str) -> dict[str, Any]:
        return challenger_status(database_url, run_id)

    @app.post("/api/research/{run_id}/challenger", status_code=202)
    def prepare_challenger(run_id: str) -> dict[str, Any]:
        from .database import ResearchRun

        with get_engine(database_url).connect() as connection:
            status = connection.execute(select(ResearchRun.status).where(ResearchRun.id == run_id)).scalar_one_or_none()
        if status != "complete":
            raise HTTPException(status_code=404, detail="A completed incumbent research run is required")
        return submit_challenger(database_url, run_id)

    @app.post("/api/portfolio/trades", status_code=201)
    def create_trade(request: TradeRequest) -> dict[str, str]:
        if request.quantity == 0:
            raise HTTPException(status_code=400, detail="quantity must not be zero")
        create_schema(database_url)
        with get_engine(database_url).begin() as connection:
            connection.execute(
                PortfolioTransaction.__table__.insert().values(
                    portfolio=request.portfolio,
                    symbol=request.symbol.upper(),
                    trade_date=request.trade_date,
                    quantity=request.quantity,
                    price=request.price,
                    fees=request.fees,
                )
            )
        return {"status": "recorded", "symbol": request.symbol.upper()}

    return app


def run_api(
    database_url: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Install API support with `uv sync --extra api`.") from exc
    uvicorn.run(create_app(database_url), host=host, port=port, reload=reload)


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    result = frame.copy()
    result = result.where(pd.notna(result), None)
    return result.to_dict("records")


def _peer_comparison(database_url: str | None, peer_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not peer_rows:
        return []
    symbols = [row["symbol"] for row in peer_rows]
    with get_engine(database_url).connect() as connection:
        latest_prices = (
            select(Price.symbol, func.max(Price.date).label("latest_date"))
            .where(Price.symbol.in_(symbols))
            .group_by(Price.symbol)
            .subquery()
        )
        prices = {
            row.symbol: row.adj_close or row.close
            for row in connection.execute(
                select(Price.symbol, Price.close, Price.adj_close)
                .join(
                    latest_prices,
                    (latest_prices.c.symbol == Price.symbol)
                    & (latest_prices.c.latest_date == Price.date),
                )
            )
        }
        facts = connection.execute(
            select(
                FundamentalFact.symbol,
                FundamentalFact.taxonomy,
                FundamentalFact.concept,
                FundamentalFact.unit,
                FundamentalFact.currency,
                FundamentalFact.period_start,
                FundamentalFact.period_end,
                FundamentalFact.filed,
                FundamentalFact.form,
                FundamentalFact.frame,
                FundamentalFact.value,
            )
            .where(
                FundamentalFact.symbol.in_(symbols),
                FundamentalFact.concept.in_(relevant_concepts()),
            )
        ).mappings().all()
    frame = pd.DataFrame([dict(row) for row in facts])
    result = []
    for peer in peer_rows:
        peer_facts = frame[frame["symbol"] == peer["symbol"]] if not frame.empty else frame
        result.append(
            {
                "symbol": peer["symbol"],
                "name": peer["name"],
                "exchange": peer["exchange"],
                "sector": peer["sector"],
                "last_price": prices.get(peer["symbol"]),
                "ratios": compute_fundamental_ratios(peer_facts, prices.get(peer["symbol"])),
            }
        )
    return result


def _selected_ratio_facts(database_url: str | None, symbol: str | None) -> pd.DataFrame:
    """Load only concepts needed for ratios instead of the whole fact ledger."""

    if not symbol:
        return pd.DataFrame()
    with get_engine(database_url).connect() as connection:
        rows = connection.execute(
            select(
                FundamentalFact.symbol,
                FundamentalFact.taxonomy,
                FundamentalFact.concept,
                FundamentalFact.unit,
                FundamentalFact.currency,
                FundamentalFact.period_start,
                FundamentalFact.period_end,
                FundamentalFact.filed,
                FundamentalFact.form,
                FundamentalFact.frame,
                FundamentalFact.value,
            ).where(
                FundamentalFact.symbol == symbol.upper(),
                FundamentalFact.concept.in_(relevant_concepts()),
            )
        ).mappings().all()
    return pd.DataFrame([dict(row) for row in rows])


def _price_annualization(prices: pd.DataFrame) -> int:
    """Infer the stored bar frequency so weekly history is not annualized as daily."""

    dates = pd.Series(pd.to_datetime(prices["date"]).drop_duplicates()).sort_values()
    if len(dates) < 2:
        return 252
    median_gap = dates.diff().dt.days.dropna().median()
    return 52 if median_gap >= 4 else 252


def _latest_price_date(database_url: str | None, symbols: list[str]) -> date | None:
    with get_engine(database_url).connect() as connection:
        return connection.execute(
            select(func.max(Price.date)).where(Price.symbol.in_(symbols))
        ).scalar()


def _fundamental_readiness(
    database_url: str | None,
    symbols: list[str],
    cutoff: date,
    *,
    max_staleness_days: int = 548,
) -> dict[str, Any]:
    symbols = list(dict.fromkeys(symbol.upper() for symbol in symbols))
    with get_engine(database_url).connect() as connection:
        fact_rows = connection.execute(
            select(
                FundamentalFact.symbol, FundamentalFact.taxonomy, FundamentalFact.concept,
                FundamentalFact.unit, FundamentalFact.currency, FundamentalFact.period_start, FundamentalFact.period_end,
                FundamentalFact.filed, FundamentalFact.form, FundamentalFact.frame,
                FundamentalFact.value, FundamentalFact.source_url,
                FundamentalFact.source_document_id, FundamentalFact.source_version,
                FundamentalFact.context_ref, FundamentalFact.available_on,
                FundamentalFact.available_at, FundamentalFact.availability_status,
                FundamentalFact.statement_kind, FundamentalFact.duration_days,
            ).where(FundamentalFact.symbol.in_(symbols))
        ).mappings().all()
        price_rows = connection.execute(
            select(Price.symbol, Price.date, Price.close, Price.adj_close)
            .where(Price.symbol.in_(symbols), Price.date <= cutoff)
            .order_by(Price.date)
        ).mappings().all()
        sector_rows = connection.execute(
            select(TickerSymbol.symbol, TickerSymbol.sector).where(TickerSymbol.symbol.in_(symbols))
        ).mappings().all()
    facts = [dict(row) for row in fact_rows]
    prices = [dict(row) for row in price_rows]
    feature_rows = compute_asof_features(
        facts,
        prices,
        cutoff,
        policy=AsOfPolicy(max_staleness_days=max_staleness_days),
        symbols=symbols,
        sector_by_symbol={row["symbol"]: row["sector"] for row in sector_rows},
    )
    feature_names = sorted(feature_rows["feature"].unique()) if not feature_rows.empty else []
    cohorts = {"price_only": symbols, "fundamental": [], "hybrid": []}
    cohort_rows = []
    for symbol in symbols:
        rows = feature_rows[feature_rows["symbol"] == symbol] if not feature_rows.empty else pd.DataFrame()
        usable = rows[rows["status"] == "usable"] if not rows.empty else rows
        usable_names = sorted(usable["feature"].tolist()) if not usable.empty else []
        sources = sorted({str(value) for value in usable["source_document_id"].dropna()}) if not usable.empty else []
        if usable_names:
            cohorts["fundamental"].append(symbol)
        if usable_names and symbol in symbols:
            cohorts["hybrid"].append(symbol)
        cohort_rows.append(
            {
                "symbol": symbol,
                "usable_features": usable_names,
                "usable_feature_count": len(usable_names),
                "feature_count": len(feature_names),
                "missing_features": sorted(set(feature_names) - set(usable_names)),
                "sources": sources,
            }
        )
    exclusions = {}
    if not feature_rows.empty:
        exclusions = {
            str(key): int(value)
            for key, value in feature_rows.loc[feature_rows["status"] == "excluded", "excluded_reason"].value_counts().items()
        }
    source_links = sorted({str(row["source_url"]) for row in facts if row.get("source_url")})
    return {
        "as_of": cutoff.isoformat(),
        "feature_version": AsOfPolicy().feature_version,
        "max_staleness_days": max_staleness_days,
        "status": (
            "ready"
            if cohorts["fundamental"] and len(cohorts["fundamental"]) == len(symbols)
            else "partial"
            if cohorts["fundamental"]
            else "unavailable"
        ),
        "symbols": symbols,
        "cohorts": cohorts,
        "cohort_rows": cohort_rows,
        "feature_names": feature_names,
        "exclusion_reasons": exclusions,
        "source_links": source_links,
        "explanation": "Fundamental features use only facts with known publication dates strictly before the decision date; unknown or stale facts remain excluded.",
    }
