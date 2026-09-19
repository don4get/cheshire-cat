"""JSON API consumed by the Dioxus dashboard.

The API is optional because the research and ingestion workflows do not need a
web server. Start it with ``uv run cheshire-cat api`` when serving the Rust UI.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import select

from .dashboard import dashboard_data, fundamental_metrics, latest_fundamentals, portfolio_valuation
from .database import PortfolioTransaction, TickerSymbol, create_schema, get_engine


def create_app(database_url: str | None = None):
    try:
        from fastapi import FastAPI, HTTPException
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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/dashboard")
    def get_dashboard(symbol: str | None = None) -> dict[str, Any]:
        data = dashboard_data(database_url, symbol)
        prices = data["prices"]
        facts = latest_fundamentals(data["fundamentals"])
        valuation = portfolio_valuation(data)
        with get_engine(database_url).connect() as connection:
            symbols = connection.execute(select(TickerSymbol.symbol).order_by(TickerSymbol.symbol)).scalars().all()
        symbols = sorted(set(symbols) | set(prices.get("symbol", pd.Series(dtype=str)).dropna()))
        return {
            "symbols": symbols,
            "selected_symbol": symbol.upper() if symbol else None,
            "prices": _records(prices),
            "metrics": _records(fundamental_metrics(prices)),
            "fundamentals": _records(facts),
            "reports": _records(data["reports"]),
            "portfolio": _records(valuation.reset_index()) if not valuation.empty else [],
        }

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
