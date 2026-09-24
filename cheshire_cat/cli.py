"""Command-line entry point for all repository workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from .backtest import StrategyConfig, backtest
from .config import settings
from .database import create_schema
from .database import FundamentalFact, TickerSymbol, get_engine
from .fundamental_coverage import audit_fundamental_coverage
from .fundamentals_asof import AsOfPolicy
from .external_fundamentals import ingest_yahoo_fundamentals, ingest_yahoo_profiles
from .market_data import DailyRequestBudget, ingest_history, ingest_universe_history
from .proxy import DEFAULT_PROXY_SOURCE, ProxyPool
from .reports import ingest_amf_reports, ingest_fundamentals, ingest_reports
from .universe import discover_universe


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cheshire-cat", description="Stock research toolkit")
    parser.add_argument("--database-url", default=settings.database_url)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init-db", help="Create the PostgreSQL schema")
    init.set_defaults(handler=_init_db)

    history = subparsers.add_parser("history", help="Download historical daily bars")
    _symbol_args(history)
    history.add_argument("--start")
    history.add_argument("--end")
    history.add_argument("--interval", default="1d")
    history.add_argument("--proxy-source", default=None, help="Proxy-list URL; enables rotating proxies")
    history.add_argument("--max-requests-per-day", type=int)
    history.add_argument("--request-delay", type=float, default=0.0)
    history.set_defaults(handler=_history)

    universe = subparsers.add_parser(
        "universe",
        help="Refresh Nasdaq/PEA symbols and ingest a small scheduled history slice",
    )
    universe.add_argument("--pea-csv", type=Path, help="Authoritative PEA eligibility CSV")
    universe.add_argument("--no-nasdaq", action="store_true")
    universe.add_argument("--no-french-pea", action="store_true")
    universe.add_argument("--max-symbols", type=int, default=25)
    universe.add_argument("--workers", type=int, default=1, help="Concurrent Yahoo history requests")
    universe.add_argument("--cadence-days", type=int, default=1)
    universe.add_argument("--interval", default="1wk", choices=("1d", "5d", "1wk", "1mo"))
    universe.add_argument("--start")
    universe.add_argument("--end")
    universe.add_argument("--proxy-source", default=DEFAULT_PROXY_SOURCE)
    universe.add_argument("--no-proxy-rotation", action="store_true")
    universe.add_argument("--max-requests-per-day", type=int, default=25)
    universe.add_argument("--request-delay", type=float, default=1.0)
    universe.add_argument("--dry-run", action="store_true")
    universe.set_defaults(handler=_universe)

    reports = subparsers.add_parser("reports", help="Archive SEC annual and quarterly reports")
    _symbol_args(reports)
    reports.add_argument("--year", type=int, default=2026)
    reports.add_argument("--form", action="append", dest="forms", default=None)
    reports.add_argument("--output-dir", type=Path)
    reports.set_defaults(handler=_reports)

    amf_reports = subparsers.add_parser(
        "amf-reports", help="Archive the latest official French AMF annual/ESEF reports by ISIN"
    )
    _symbol_args(amf_reports)
    amf_reports.add_argument("--output-dir", type=Path)
    amf_reports.add_argument("--workers", type=int, default=4)
    amf_reports.set_defaults(handler=_amf_reports)

    fundamentals = subparsers.add_parser("fundamentals", help="Import SEC XBRL balance-sheet and other facts")
    _symbol_args(fundamentals)
    fundamentals.add_argument("--filed-year", type=int, help="Restrict facts to a filing year")
    fundamentals.set_defaults(handler=_fundamentals)

    yahoo_fundamentals = subparsers.add_parser(
        "yahoo-fundamentals", help="Import source-labelled financial statements for non-SEC issuers"
    )
    _symbol_args(yahoo_fundamentals)
    yahoo_fundamentals.add_argument("--chunk-size", type=int, default=50)
    yahoo_fundamentals.set_defaults(handler=_yahoo_fundamentals)

    yahoo_profiles = subparsers.add_parser(
        "yahoo-profiles", help="Synchronize Yahoo sector classifications for tracked symbols"
    )
    _symbol_args(yahoo_profiles)
    yahoo_profiles.add_argument("--chunk-size", type=int, default=50)
    yahoo_profiles.set_defaults(handler=_yahoo_profiles)

    coverage = subparsers.add_parser(
        "fundamental-coverage",
        help="Audit point-in-time fundamental coverage before calculating returns",
    )
    coverage.add_argument(
        "--dates",
        required=True,
        help="Comma-separated decision dates, for example 2018-01-01,2020-01-01",
    )
    coverage.add_argument("--max-staleness-days", type=int, default=548)
    coverage.set_defaults(handler=_fundamental_coverage)

    run_backtest = subparsers.add_parser("backtest", help="Backtest the investment agent on a CSV")
    run_backtest.add_argument("csv", type=Path, help="CSV with date,symbol,close or adj_close columns")
    run_backtest.add_argument("--fast-window", type=int, default=50)
    run_backtest.add_argument("--slow-window", type=int, default=200)
    run_backtest.add_argument("--transaction-cost", type=float, default=0.001)
    run_backtest.set_defaults(handler=_backtest)

    research = subparsers.add_parser("research", help="Train on 80% of history and validate a frozen portfolio bot")
    research.add_argument("--market", choices=("NASDAQ", "EURONEXT_PARIS", "both"), default="both")
    research.add_argument("--years", type=int, default=20)
    research.add_argument("--initial-cash", type=float, default=100_000)
    research.add_argument("--transaction-cost", type=float, default=0.001)
    research.add_argument("--resume", help="Resume an interrupted research run by ID")
    research.set_defaults(handler=_research)

    audit = subparsers.add_parser("validate-research", help="Audit saved candidates without changing their selection")
    audit.add_argument("--market", choices=("NASDAQ", "EURONEXT_PARIS", "both"), default="both")
    audit.set_defaults(handler=_validate_research)

    challenger = subparsers.add_parser("challenger", help="Develop and evaluate Atlas alongside saved incumbent bots")
    challenger.add_argument("--market", choices=("NASDAQ", "EURONEXT_PARIS", "both"), default="both")
    challenger.set_defaults(handler=_challenger)

    dashboard = subparsers.add_parser("dashboard", help="Run the interactive Dash dashboard")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8050)
    dashboard.add_argument("--debug", action="store_true")
    dashboard.set_defaults(handler=_dashboard)

    api = subparsers.add_parser("api", help="Run the JSON API used by the Dioxus dashboard")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--reload", action="store_true")
    api.set_defaults(handler=_api)
    return parser


def _symbol_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--symbols", help="Comma-separated ticker symbols")
    group.add_argument("--symbols-file", type=Path, help="One ticker per line")


def _research(args: argparse.Namespace) -> None:
    from .research import RESEARCH_VERSION
    from .research_jobs import create_run, execute_run, latest_run

    create_schema(args.database_url)
    markets = ("NASDAQ", "EURONEXT_PARIS") if args.market == "both" else (args.market,)
    if args.resume:
        result = execute_run(args.database_url, args.resume)
        print(json.dumps({"run_id": args.resume, "verdict": result["validation_verdict"]}))
        return
    for market in markets:
        latest = latest_run(args.database_url, market)
        parameters = {"years": args.years, "initial_cash": args.initial_cash, "cost": args.transaction_cost}
        if latest and latest["parameters"] == parameters and latest["version"] == RESEARCH_VERSION:
            if latest["status"] == "complete":
                print(json.dumps({"market": market, "run_id": latest["id"], "status": "already complete"}), flush=True)
                continue
            run_id = latest["id"]
        else:
            run_id = create_run(args.database_url, market, args.years, args.initial_cash, args.transaction_cost)
        print(json.dumps({"market": market, "run_id": run_id, "status": "started"}), flush=True)
        result = execute_run(args.database_url, run_id)
        print(json.dumps({"market": market, "run_id": run_id, "split": result["split"],
                          "selected": result["selection"]["selected_id"],
                          "strategies": [{"name": row["name"], "training": row["training"],
                                          "validation": row["validation"], "full": row["full"]}
                                         for row in result["strategies"]]}), flush=True)


def _validate_research(args: argparse.Namespace) -> None:
    from .research_jobs import latest_run
    from .validation_jobs import build_audit

    create_schema(args.database_url)
    markets = ("NASDAQ", "EURONEXT_PARIS") if args.market == "both" else (args.market,)
    for market in markets:
        run = latest_run(args.database_url, market)
        if not run or run["status"] != "complete":
            raise ValueError(f"No completed research experiment for {market}")
        status = build_audit(args.database_url, run["id"], progress=lambda message: print(message, flush=True))
        print(json.dumps({"market": market, "run_id": run["id"], "status": status["status"]}), flush=True)


def _challenger(args: argparse.Namespace) -> None:
    from .challenger_jobs import build_challenger
    from .research_jobs import latest_run

    create_schema(args.database_url)
    markets = ("NASDAQ", "EURONEXT_PARIS") if args.market == "both" else (args.market,)
    for market in markets:
        run = latest_run(args.database_url, market)
        if not run or run["status"] != "complete":
            raise ValueError(f"No completed incumbent experiment for {market}")
        status = build_challenger(args.database_url, run["id"], progress=lambda message: print(message, flush=True))
        print(json.dumps({"market": market, "run_id": run["id"], "status": status["status"]}), flush=True)


def _symbols(args: argparse.Namespace) -> list[str]:
    if args.symbols:
        return [item for item in args.symbols.split(",") if item.strip()]
    return [line.strip() for line in args.symbols_file.read_text().splitlines() if line.strip()]


def _init_db(args: argparse.Namespace) -> None:
    create_schema(args.database_url)
    print(f"Database schema ready: {args.database_url}")


def _history(args: argparse.Namespace) -> None:
    create_schema(args.database_url)
    pool = ProxyPool.from_free_proxy_list(args.proxy_source) if args.proxy_source else None
    budget = DailyRequestBudget(args.max_requests_per_day, args.request_delay)
    print(
        json.dumps(
            ingest_history(
                _symbols(args),
                args.start,
                args.end,
                args.interval,
                args.database_url,
                proxy_pool=pool,
                request_budget=budget,
            )
        )
    )


def _universe(args: argparse.Namespace) -> None:
    if args.no_nasdaq and args.no_french_pea:
        raise SystemExit("At least one universe source must be enabled")
    records = discover_universe(
        include_nasdaq=not args.no_nasdaq,
        include_french_pea=not args.no_french_pea,
        pea_csv=args.pea_csv,
    )
    if args.dry_run:
        print(json.dumps({"symbols": len(records), "sample": [record.symbol for record in records[:20]]}))
        return
    pool = None if args.no_proxy_rotation else ProxyPool.from_free_proxy_list(args.proxy_source)
    summary = ingest_universe_history(
        records,
        include_nasdaq=not args.no_nasdaq,
        include_french_pea=not args.no_french_pea,
        pea_csv=str(args.pea_csv) if args.pea_csv else None,
        max_symbols_per_run=args.max_symbols,
        cadence_days=args.cadence_days,
        interval=args.interval,
        start=args.start,
        end=args.end,
        database_url=args.database_url,
        proxy_pool=pool,
        request_budget=DailyRequestBudget(args.max_requests_per_day, args.request_delay),
        workers=args.workers,
    )
    print(json.dumps({"universe": len(records), **summary}))


def _reports(args: argparse.Namespace) -> None:
    create_schema(args.database_url)
    print(json.dumps(ingest_reports(_symbols(args), args.year, args.forms or ("10-K", "10-Q", "20-F", "40-F"), args.database_url, output_dir=args.output_dir)))


def _amf_reports(args: argparse.Namespace) -> None:
    create_schema(args.database_url)
    print(json.dumps(ingest_amf_reports(_symbols(args), args.database_url, args.output_dir, workers=args.workers)))


def _fundamentals(args: argparse.Namespace) -> None:
    create_schema(args.database_url)
    print(json.dumps(ingest_fundamentals(_symbols(args), args.filed_year, database_url=args.database_url)))


def _yahoo_fundamentals(args: argparse.Namespace) -> None:
    create_schema(args.database_url)
    print(
        json.dumps(
            ingest_yahoo_fundamentals(
                _symbols(args), database_url=args.database_url, chunk_size=args.chunk_size
            )
        )
    )


def _yahoo_profiles(args: argparse.Namespace) -> None:
    create_schema(args.database_url)
    print(
        json.dumps(
            ingest_yahoo_profiles(
                _symbols(args), database_url=args.database_url, chunk_size=args.chunk_size
            )
        )
    )


def _fundamental_coverage(args: argparse.Namespace) -> None:
    create_schema(args.database_url)
    with get_engine(args.database_url).connect() as connection:
        facts = connection.execute(select(FundamentalFact)).scalars().all()
        universe = connection.execute(select(TickerSymbol.symbol, TickerSymbol.exchange)).mappings().all()
    report = audit_fundamental_coverage(
        facts,
        [item.strip() for item in args.dates.split(",") if item.strip()],
        universe=[{"symbol": row["symbol"], "market": row["exchange"]} for row in universe],
        policy=AsOfPolicy(max_staleness_days=args.max_staleness_days),
    )
    print(json.dumps(report, indent=2, default=str))


def _backtest(args: argparse.Namespace) -> None:
    prices = pd.read_csv(args.csv)
    config = StrategyConfig(args.fast_window, args.slow_window, args.transaction_cost)
    result = backtest(prices, config=config)
    print(json.dumps({"strategy": result.metrics, "benchmark": result.benchmark_metrics}, indent=2))


def _dashboard(args: argparse.Namespace) -> None:
    from .dashboard import run_dashboard

    run_dashboard(args.database_url, args.host, args.port, args.debug)


def _api(args: argparse.Namespace) -> None:
    from .api import run_api

    run_api(args.database_url, args.host, args.port, args.reload)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
