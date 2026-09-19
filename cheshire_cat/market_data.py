"""Historical market data ingestion backed by Yahoo Finance by default."""

from __future__ import annotations

import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from threading import Lock
from typing import Any, Protocol

import pandas as pd
import requests
from sqlalchemy.orm import Session

from .database import IngestionState, create_schema, get_engine, upsert_prices
from .proxy import ProxyPool
from .universe import TickerRecord, discover_universe, store_universe

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


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


class YahooChartProvider:
    """Fetch historical bars directly from Yahoo's chart endpoint.

    This endpoint returns the complete requested range in one response and is
    substantially lighter than constructing a yfinance ticker for every
    symbol. It also accepts ordinary HTTP proxies, which keeps proxy rotation
    available for the large-universe job.
    """

    def __init__(
        self,
        proxy: str | None = None,
        session: requests.Session | None = None,
        timeout: int = 30,
    ):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.session.headers.update(
            {"User-Agent": "cheshire-cat/0.1 research client", "Accept": "application/json"}
        )
        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})

    def history(
        self, symbol: str, start: str | None, end: str | None, interval: str
    ) -> pd.DataFrame:
        params = {
            "period1": _timestamp(start, default=0),
            "period2": _timestamp(end, default=int(time.time())),
            "interval": interval,
            "events": "div,splits",
            "includeAdjustedClose": "true",
        }
        response = self.session.get(
            YAHOO_CHART_URL.format(symbol=symbol), params=params, timeout=self.timeout
        )
        response.raise_for_status()
        payload = response.json()
        chart = payload.get("chart") or {}
        if chart.get("error"):
            raise RuntimeError(f"Yahoo rejected {symbol}: {chart['error']}")
        result = (chart.get("result") or [None])[0]
        if not result:
            return pd.DataFrame()
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        frame = pd.DataFrame(
            {
                "Open": quote.get("open", []),
                "High": quote.get("high", []),
                "Low": quote.get("low", []),
                "Close": quote.get("close", []),
                "Volume": quote.get("volume", []),
            },
            index=pd.to_datetime(timestamps, unit="s", utc=True),
        )
        adjusted = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get(
            "adjclose", []
        )
        if adjusted:
            frame["Adj Close"] = adjusted
        return frame


class RotatingYFinanceProvider:
    """Retry Yahoo chart requests through successive proxy endpoints."""

    def __init__(self, pool: ProxyPool, retries: int = 6, timeout: int = 8):
        self.pool = pool
        self.retries = max(1, retries)
        self.timeout = timeout

    def history(self, symbol: str, start: str | None, end: str | None, interval: str) -> pd.DataFrame:
        last_error: Exception | None = None
        for _ in range(self.retries):
            proxy = self.pool.next()
            try:
                frame = YahooChartProvider(proxy, timeout=self.timeout).history(
                    symbol, start, end, interval
                )
                self.pool.mark_success(proxy)
                return frame
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code != 429:
                    self.pool.mark_success(proxy)
                    raise
                last_error = exc
                self.pool.mark_failure(proxy)
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
        self._lock = Lock()

    def acquire(self) -> None:
        with self._lock:
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
        if record["date"].date() < date(1970, 1, 2):
            continue
        if all(
            pd.isna(record.get(column))
            for column in ("open", "high", "low", "close", "adj_close", "volume")
        ):
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
        RotatingYFinanceProvider(proxy_pool) if proxy_pool else YahooChartProvider()
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
    workers: int = 1,
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
    if workers < 1:
        raise ValueError("workers must be positive")
    records = records or discover_universe(
        include_nasdaq=include_nasdaq,
        include_french_pea=include_french_pea,
        pea_csv=pea_csv,
    )
    store_universe(records, database_url)
    request_budget = request_budget or DailyRequestBudget()
    provider = provider or (
        RotatingYFinanceProvider(proxy_pool) if proxy_pool else YahooChartProvider()
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
        def fetch(record: TickerRecord) -> tuple[TickerRecord, list[dict[str, Any]], str | None]:
            try:
                request_budget.acquire()
                frame = provider.history(
                    record.symbol, _date_string(start), _date_string(end), interval
                )
                normalized = normalize_history(frame, record.symbol)
                if not normalized:
                    raise RuntimeError("Yahoo returned no historical rows")
                return record, normalized, None
            except Exception as exc:  # noqa: BLE001 - isolate one bad ticker
                return record, [], str(exc)[:1000]

        fetch_results = (
            (fetch(record) for record in due)
            if workers == 1
            else _parallel_fetch(fetch, due, workers)
        )
        for record, normalized, error in fetch_results:
            state = states.get(record.symbol) or IngestionState(symbol=record.symbol)
            if state not in session:
                session.add(state)
            state.last_requested_at = datetime.now(UTC).replace(tzinfo=None)
            if error:
                if "budget exhausted" in error:
                    continue
                state.consecutive_failures = (state.consecutive_failures or 0) + 1
                state.last_error = error
                state.next_due_on = today + timedelta(days=1)
                summary["failed"] += 1
                continue
            rows = upsert_prices(session, normalized)
            state.last_price_date = max((row["date"] for row in normalized), default=None)
            state.next_due_on = today + timedelta(days=cadence_days)
            state.consecutive_failures = 0
            state.last_error = None
            summary["succeeded"] += 1
            summary["rows"] += rows
        session.commit()
    return summary


def _date_string(value: str | date | None) -> str | None:
    return value.isoformat() if isinstance(value, date) else value


def _timestamp(value: str | None, default: int) -> int:
    if value is None:
        return default
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return int(timestamp.timestamp())


def _parallel_fetch(fetch, records: list[TickerRecord], workers: int):
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch, record) for record in records]
        for future in as_completed(futures):
            yield future.result()
