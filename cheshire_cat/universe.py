"""Discover the tracked Nasdaq and French PEA equity universe.

The universe is refreshed independently from price ingestion. Nasdaq's public
screener supplies US symbols; Euronext's Paris product directory supplies the
French listed-equity candidate set, while an optional CSV can provide an
authoritative broker/issuer PEA eligibility flag.
"""

from __future__ import annotations

import csv
import html
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import TickerSymbol, create_schema, get_engine

NASDAQ_SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks"
EURONEXT_PARIS_URL = (
    "https://live.euronext.com/en/product_directory/data/"
    "stocks-paris-euronext-regulated-?mics=XPAR"
)
DEFAULT_PEA_SOURCE_URL = os.getenv("CHESHIRE_CAT_PEA_SOURCE_URL", EURONEXT_PARIS_URL)
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TickerRecord:
    symbol: str
    exchange: str
    name: str | None = None
    isin: str | None = None
    currency: str | None = None
    sector: str | None = None
    pea_eligible: bool | None = None
    source: str = "unknown"


class NasdaqUniverseSource:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "cheshire-cat/0.1 research client",
                "Accept": "application/json, text/plain, */*",
            }
        )

    def fetch(self) -> list[TickerRecord]:
        response = self.session.get(
            NASDAQ_SCREENER_URL,
            params={"letter": "0", "exchange": "nasdaq", "download": "true", "limit": "5000"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json().get("data") or {}
        rows = payload.get("rows") or []
        headers = [str(header).lower() for header in payload.get("headers") or []]
        records = []
        for row in rows:
            values = _row_values(row, headers)
            symbol = _clean(values.get("symbol"))
            if not symbol or "." in symbol or "^" in symbol:
                continue
            records.append(
                TickerRecord(
                    symbol=symbol.upper(),
                    exchange="NASDAQ",
                    name=_clean(values.get("name") or values.get("companyname")),
                    currency="USD",
                    sector=_clean(values.get("sector")),
                    source="nasdaq-screener",
                )
            )
        return _deduplicate(records)


class FrenchPeaUniverseSource:
    """Fetch Paris listings, optionally using an eligibility CSV as authority."""

    def __init__(
        self,
        source_url: str | None = None,
        csv_path: str | Path | None = None,
        session: requests.Session | None = None,
    ):
        self.source_url = source_url or DEFAULT_PEA_SOURCE_URL
        self.csv_path = Path(csv_path) if csv_path else None
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", "cheshire-cat/0.1 research client")

    def fetch(self) -> list[TickerRecord]:
        if self.csv_path:
            return _read_pea_csv(self.csv_path)
        response = self.session.get(self.source_url, timeout=30)
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("aaData") or []
        total = _integer(payload.get("iTotalRecords"))
        if total > len(rows) and hasattr(self.session, "post"):
            response = self.session.post(
                self.source_url,
                data={
                    "draw": "1",
                    "start": "0",
                    "length": str(total),
                    "iDisplayStart": "0",
                    "iDisplayLength": str(total),
                    "args[display_datapoints]": (
                        "name,isin,symbol,market,lastPrice,"
                        "precentDayChange,lastTradeTime"
                    ),
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        return self._parse_euronext(payload)

    @staticmethod
    def _parse_euronext(payload: dict[str, Any]) -> list[TickerRecord]:
        # The public Euronext product-directory endpoint returns aaData rows
        # containing HTML fragments rather than JSON objects.
        records: list[TickerRecord] = []
        for row in payload.get("aaData") or []:
            values = [_clean_html(value) for value in row]
            if len(values) < 3:
                continue
            name, isin, symbol = values[:3]
            if _is_non_equity_instrument(name):
                continue
            currency = values[4].split()[0] if len(values) > 4 and values[4] else "EUR"
            if not symbol or not isin:
                continue
            market_code = _primary_market_code(row)
            records.append(
                TickerRecord(
                    symbol=_yahoo_symbol(symbol, market_code),
                    exchange="EURONEXT_PARIS",
                    name=name,
                    isin=isin,
                    currency=currency,
                    sector=None,
                    # The public directory has no eligibility column. Keep
                    # this unknown rather than inventing a PEA classification;
                    # pass --pea-csv for an authoritative eligibility flag.
                    pea_eligible=None,
                    source="euronext-paris-regulated",
                )
            )
        return _deduplicate(records)


def discover_universe(
    include_nasdaq: bool = True,
    include_french_pea: bool = True,
    pea_csv: str | Path | None = None,
    session: requests.Session | None = None,
) -> list[TickerRecord]:
    """Fetch and merge both issue #7 symbol sources."""

    records: list[TickerRecord] = []
    errors: list[requests.RequestException] = []
    if include_nasdaq:
        try:
            records.extend(NasdaqUniverseSource(session).fetch())
        except requests.RequestException as exc:
            LOGGER.warning("Nasdaq universe discovery failed: %s", exc)
            errors.append(exc)
    if include_french_pea:
        try:
            records.extend(FrenchPeaUniverseSource(csv_path=pea_csv, session=session).fetch())
        except requests.RequestException as exc:
            LOGGER.warning("French PEA universe discovery failed: %s", exc)
            errors.append(exc)
    if not records and errors:
        raise RuntimeError("All requested universe sources failed") from errors[-1]
    return _deduplicate(records)


def store_universe(records: list[TickerRecord], database_url: str | None = None) -> int:
    """Idempotently persist the discovered universe in PostgreSQL."""

    create_schema(database_url)
    with Session(get_engine(database_url)) as session:
        incoming_symbols = {record.symbol for record in records}
        if any("euronext-paris-regulated" in record.source for record in records):
            stale_paris = session.scalars(
                select(TickerSymbol).where(TickerSymbol.source.like("%euronext-paris-regulated%"))
            ).all()
            for current in stale_paris:
                if current.symbol not in incoming_symbols:
                    session.delete(current)
        for record in records:
            current = session.get(TickerSymbol, record.symbol)
            values = {
                "exchange": record.exchange,
                "name": record.name,
                "isin": record.isin,
                "currency": record.currency,
                "sector": record.sector,
                "pea_eligible": record.pea_eligible,
                "source": record.source,
            }
            if current is None:
                session.add(TickerSymbol(symbol=record.symbol, **values))
            else:
                for key, value in values.items():
                    setattr(current, key, value)
        session.commit()
    return len(records)


def database_universe(database_url: str | None = None) -> list[TickerRecord]:
    create_schema(database_url)
    with Session(get_engine(database_url)) as session:
        rows = session.scalars(select(TickerSymbol).order_by(TickerSymbol.symbol)).all()
    return [
        TickerRecord(
            symbol=row.symbol,
            exchange=row.exchange,
            name=row.name,
            isin=row.isin,
            currency=row.currency,
            sector=row.sector,
            pea_eligible=row.pea_eligible,
            source=row.source,
        )
        for row in rows
    ]


def _read_pea_csv(path: Path) -> list[TickerRecord]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        records = []
        for row in rows:
            symbol = _clean(row.get("yahoo_symbol") or row.get("symbol"))
            if not symbol:
                continue
            exchange = _clean(row.get("exchange")) or "EURONEXT_PARIS"
            if exchange.upper() in {"PARIS", "XPAR", "EURONEXT_PARIS"}:
                symbol = _yahoo_paris_symbol(symbol)
            records.append(
                TickerRecord(
                    symbol=symbol,
                    exchange=exchange.upper(),
                    name=_clean(row.get("name")),
                    isin=_clean(row.get("isin")),
                    currency=_clean(row.get("currency")) or "EUR",
                    pea_eligible=_parse_bool(row.get("pea_eligible") or row.get("pea")),
                    source=str(path),
                )
            )
    return _deduplicate(records)


def _row_values(row: Any, headers: list[str]) -> dict[str, Any]:
    if isinstance(row, dict):
        return {str(key).lower(): value for key, value in row.items()}
    return dict(zip(headers, row, strict=False))


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_html(value: Any) -> str:
    text = html.unescape(str(value or ""))
    return re.sub(r"<[^>]+>", "", text).strip()


def _yahoo_paris_symbol(symbol: str) -> str:
    return _yahoo_symbol(symbol, "XPAR")


def _yahoo_symbol(symbol: str, market_code: str | None) -> str:
    symbol = symbol.strip().upper()
    if "." in symbol:
        return symbol
    suffix = {
        "XAMS": ".AS",
        "XBRU": ".BR",
        "XLIS": ".LS",
        "XPAR": ".PA",
    }.get(market_code or "XPAR", ".PA")
    return f"{symbol}{suffix}"


def _primary_market_code(row: Any) -> str | None:
    first_cell = str(row[0]) if row else ""
    match = re.search(r"-([A-Z]{4})[\"/]", first_cell)
    if match:
        return match.group(1)
    market_cell = str(row[3]) if len(row) > 3 else ""
    match = re.search(r"\b(X[A-Z]{3})\b", market_cell)
    return match.group(1) if match else None


def _parse_bool(value: Any) -> bool | None:
    if value is None or not str(value).strip():
        return None
    return str(value).strip().lower() in {"1", "true", "yes", "y", "oui", "eligible"}


def _is_non_equity_instrument(name: str) -> bool:
    return bool(re.search(r"\b(?:BSA\d*|WARR(?:ANT)?S?)\b", name.upper()))


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _deduplicate(records: list[TickerRecord]) -> list[TickerRecord]:
    merged: dict[str, TickerRecord] = {}
    for record in records:
        previous = merged.get(record.symbol)
        if previous is None:
            merged[record.symbol] = record
            continue
        merged[record.symbol] = TickerRecord(
            symbol=record.symbol,
            exchange=previous.exchange,
            name=previous.name or record.name,
            isin=previous.isin or record.isin,
            currency=previous.currency or record.currency,
            sector=previous.sector or record.sector,
            pea_eligible=(
                record.pea_eligible
                if record.pea_eligible is not None
                else previous.pea_eligible
            ),
            source=f"{previous.source},{record.source}",
        )
    return sorted(merged.values(), key=lambda record: record.symbol)
