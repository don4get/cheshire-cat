"""Historical market data ingestion backed by Yahoo Finance by default."""

from __future__ import annotations

import time
from collections import deque
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

import pandas as pd
from sqlalchemy.orm import Session

from .database import IngestionState, create_schema, get_engine, upsert_prices
from .proxy import ProxyPool
from .universe import TickerRecord, discover_universe, store_universe


class HistoryProvider(Protocol):
    def history(self, symbol: str, start: str | None, end: str | None, interval: str) -> pd.DataFrame:
        ...


class YFinanceProvider:
    """Lazy yfinance adapter; importing the package does not require yfinance."""

    def __init__(self, proxy: str | None = None):
        self.proxy = proxy

    def history(self, symbol: str, start: str | None, end: str | None, interval: str) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Install market-data support with `uv sync --extra market-data`.") from exc
        session = None
        if self.proxy:
            try:
                from curl_cffi import requests as curl_requests

                session = curl_requests.Session(
                    impersonate="chrome", proxies={"http": self.proxy, "https": self.proxy}
                )
            except ImportError as exc:
                raise RuntimeError("Proxy rotation requires the market-data extra.") from exc
        return yf.Ticker(symbol, session=session).history(
            start=start, end=end, interval=interval, auto_adjust=False
        )


class RotatingYFinanceProvider:
    """Retry Yahoo requests through successive proxy endpoints."""

    def __init__(self, pool: ProxyPool, retries: int = 3):
        self.pool = pool
        self.retries = max(1, retries)

    def history(self, symbol: str, start: str | None, end: str | None, interval: str) -> pd.DataFrame:
        last_error: Exception | None = None
        for _ in range(self.retries):
            proxy = self.pool.next()
            try:
                frame = YFinanceProvider(proxy).history(symbol, start, end, interval)
                self.pool.mark_success(proxy)
                return frame
            except Exception as exc:  # noqa: BLE001 - retrying transient proxy/Yahoo failures
                last_error = exc
                self.pool.mark_failure(proxy)
        raise RuntimeError(f"Yahoo request failed for {symbol} through all proxy attempts") from last_error


class DailyRequestBudget:
    """Limit request frequency and total calls for a process run."""

    def __init__(self, max_calls: int | None = None, min_interval_seconds: float = 0.0):
        self.max_calls = max_calls
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self._calls: deque[datetime] = deque()
        self._last_call = 0.0

    def acquire(self) -> None:
        now = datetime.now(UTC)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        while self._calls and self._calls[0] < day_start:
            self._calls.popleft()
        if self.max_calls is not None and len(self._calls) >= self.max_calls:
            raise RuntimeError("Daily Yahoo request budget exhausted; run again tomorrow")
        delay = self.min_interval_seconds - (time.monotonic() - self._last_call)
        if delay > 0:
            time.sleep(delay)
        self._last_call = time.monotonic()
        self._calls.append(datetime.now(UTC))


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
    proxy_pool: ProxyPool | None = None,
    request_budget: DailyRequestBudget | None = None,
) -> dict[str, int]:
    """Download and idempotently persist historical bars for each symbol."""

    provider = provider or (
        RotatingYFinanceProvider(proxy_pool) if proxy_pool else YFinanceProvider()
    )
    request_budget = request_budget or DailyRequestBudget()
    create_schema(database_url)
    engine = get_engine(database_url)
    results: dict[str, int] = {}
    with Session(engine) as session:
        for symbol in dict.fromkeys(s.strip().upper() for s in symbols if s.strip()):
            request_budget.acquire()
            frame = provider.history(symbol, _date_string(start), _date_string(end), interval)
            results[symbol] = upsert_prices(session, normalize_history(frame, symbol))
    return results


def ingest_universe_history(
    records: list[TickerRecord] | None = None,
    *,
    include_nasdaq: bool = True,
    include_french_pea: bool = True,
    pea_csv: str | None = None,
    max_symbols_per_run: int = 25,
    cadence_days: int = 1,
    interval: str = "1wk",
    start: str | date | None = None,
    end: str | date | None = None,
    database_url: str | None = None,
    provider: HistoryProvider | None = None,
    proxy_pool: ProxyPool | None = None,
    request_budget: DailyRequestBudget | None = None,
) -> dict[str, int]:
    """Ingest a small rotating slice of a large universe.

    New symbols are selected first and become due again after ``cadence_days``.
    The default is 25 weekly observations per run, so a scheduled daily job
    does not flood Yahoo or create an unnecessarily large daily-bar table.
    """

    if max_symbols_per_run < 1:
        raise ValueError("max_symbols_per_run must be positive")
    if cadence_days < 1:
        raise ValueError("cadence_days must be positive")
    records = records or discover_universe(
        include_nasdaq=include_nasdaq,
        include_french_pea=include_french_pea,
        pea_csv=pea_csv,
    )
    store_universe(records, database_url)
    request_budget = request_budget or DailyRequestBudget()
    provider = provider or (
        RotatingYFinanceProvider(proxy_pool) if proxy_pool else YFinanceProvider()
    )
    today = datetime.now(UTC).date()
    engine = get_engine(database_url)
    summary = {"selected": 0, "succeeded": 0, "rows": 0, "failed": 0}
    with Session(engine) as session:
        symbols = [record.symbol for record in records]
        states = {
            state.symbol: state
            for state in session.query(IngestionState).filter(IngestionState.symbol.in_(symbols)).all()
        }
        due = [
            record
            for record in records
            if states.get(record.symbol) is None
            or states[record.symbol].next_due_on is None
            or states[record.symbol].next_due_on <= today
        ][:max_symbols_per_run]
        summary["selected"] = len(due)
        for record in due:
            state = states.get(record.symbol) or IngestionState(symbol=record.symbol)
            if state not in session:
                session.add(state)
            state.last_requested_at = datetime.now(UTC).replace(tzinfo=None)
            try:
                request_budget.acquire()
                frame = provider.history(
                    record.symbol, _date_string(start), _date_string(end), interval
                )
                normalized = normalize_history(frame, record.symbol)
                rows = upsert_prices(session, normalized)
                state.last_price_date = max((row["date"] for row in normalized), default=None)
                state.next_due_on = today + timedelta(days=cadence_days)
                state.consecutive_failures = 0
                state.last_error = None
                summary["succeeded"] += 1
                summary["rows"] += rows
            except RuntimeError as exc:
                if "budget exhausted" in str(exc):
                    break
                state.consecutive_failures += 1
                state.last_error = str(exc)[:1000]
                state.next_due_on = today + timedelta(days=1)
                summary["failed"] += 1
            except Exception as exc:  # noqa: BLE001 - isolate one bad ticker
                state.consecutive_failures += 1
                state.last_error = str(exc)[:1000]
                state.next_due_on = today + timedelta(days=1)
                summary["failed"] += 1
        session.commit()
    return summary


def _date_string(value: str | date | None) -> str | None:
    return value.isoformat() if isinstance(value, date) else value
