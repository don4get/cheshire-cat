"""Historical market data ingestion backed by Yahoo Finance by default."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

import pandas as pd
from sqlalchemy.orm import Session

from .database import create_schema, get_engine, upsert_prices


class HistoryProvider(Protocol):
    def history(self, symbol: str, start: str | None, end: str | None, interval: str) -> pd.DataFrame:
        ...


class YFinanceProvider:
    """Lazy yfinance adapter; importing the package does not require yfinance."""

    def history(self, symbol: str, start: str | None, end: str | None, interval: str) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Install market-data support with `uv sync --extra market-data`.") from exc
        return yf.Ticker(symbol).history(start=start, end=end, interval=interval, auto_adjust=False)


def normalize_history(frame: pd.DataFrame, symbol: str) -> list[dict[str, Any]]:
    """Normalize provider output into rows accepted by :func:`upsert_prices`."""

    if frame is None or frame.empty:
        return []
    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [column[0] for column in data.columns]
    data.columns = [str(column).lower().replace(" ", "_") for column in data.columns]
    if "adj_close" not in data and "close" in data:
        data["adj_close"] = data["close"]
    if "date" in data.columns:
        date_values = pd.to_datetime(data.pop("date"), utc=True).dt.tz_localize(None).dt.normalize()
    else:
        date_values = pd.Series(
            pd.to_datetime(data.index, utc=True).tz_localize(None).normalize(), index=data.index
        )
    data["date"] = date_values.to_numpy()
    rows: list[dict[str, Any]] = []
    for record in data.to_dict("records"):
        if pd.isna(record.get("date")):
            continue
        rows.append(
            {
                "symbol": symbol.upper(),
                "date": record["date"].date(),
                "open": _number(record.get("open")),
                "high": _number(record.get("high")),
                "low": _number(record.get("low")),
                "close": _number(record.get("close")),
                "adj_close": _number(record.get("adj_close")),
                "volume": _integer(record.get("volume")),
                "source": "yfinance",
            }
        )
    return rows


def _number(value: Any) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def _integer(value: Any) -> int | None:
    return None if value is None or pd.isna(value) else int(value)


def ingest_history(
    symbols: list[str],
    start: str | date | None = None,
    end: str | date | None = None,
    interval: str = "1d",
    database_url: str | None = None,
    provider: HistoryProvider | None = None,
) -> dict[str, int]:
    """Download and idempotently persist historical bars for each symbol."""

    provider = provider or YFinanceProvider()
    create_schema(database_url)
    engine = get_engine(database_url)
    results: dict[str, int] = {}
    with Session(engine) as session:
        for symbol in dict.fromkeys(s.strip().upper() for s in symbols if s.strip()):
            frame = provider.history(symbol, _date_string(start), _date_string(end), interval)
            results[symbol] = upsert_prices(session, normalize_history(frame, symbol))
    return results


def _date_string(value: str | date | None) -> str | None:
    return value.isoformat() if isinstance(value, date) else value
