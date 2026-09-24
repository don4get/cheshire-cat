"""Fundamental statements for issuers that are not covered by SEC XBRL.

Yahoo Finance is used here as a real, source-labelled fallback for the
Euronext universe. Values are kept as reported by the provider; the dashboard
never presents them as SEC facts.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from .database import TickerSymbol, create_schema, get_engine
from .reports import _set_fundamental_ingestion_state, _upsert_fundamentals

YAHOO_FINANCIALS_URL = "https://finance.yahoo.com/quote/{symbol}/financials"
_METADATA_COLUMNS = {"symbol", "asOfDate", "periodType", "currencyCode"}


def ingest_yahoo_fundamentals(
    symbols: Iterable[str],
    database_url: str | None = None,
    chunk_size: int = 50,
) -> dict[str, int]:
    """Load annual and trailing financial statement observations in batches.

    ``yahooquery`` supports batched requests, which is substantially faster
    than creating one HTTP client per company. A batch failure is retried one
    symbol at a time so one unavailable issuer does not abort the run.
    """

    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    normalized = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
    if not normalized:
        return {}
    try:
        from yahooquery import Ticker
    except ImportError as exc:
        raise RuntimeError("Install Yahoo fundamentals support with `uv sync --extra all`.") from exc

    create_schema(database_url)
    result: dict[str, int] = {}
    engine = get_engine(database_url)
    with Session(engine) as session:
        for offset in range(0, len(normalized), chunk_size):
            batch = normalized[offset : offset + chunk_size]
            for symbol in batch:
                _set_fundamental_ingestion_state(
                    session, "YAHOO-FUNDAMENTALS", symbol, "in_progress"
                )
            session.commit()
            try:
                frame = Ticker(batch).all_financial_data(frequency="a")
                rows = yahoo_frame_to_facts(frame)
                _save_rows(session, rows, result)
            except Exception:  # noqa: BLE001 - retry a failed provider batch below
                for symbol in batch:
                    try:
                        frame = Ticker(symbol).all_financial_data(frequency="a")
                        rows = yahoo_frame_to_facts(frame)
                        _save_rows(session, rows, result)
                    except Exception:  # noqa: BLE001 - one issuer may have no statements
                        result.setdefault(symbol, 0)
                        _set_fundamental_ingestion_state(
                            session, "YAHOO-FUNDAMENTALS", symbol, "failed",
                            error="Provider returned no usable annual statement",
                        )
                    else:
                        _set_fundamental_ingestion_state(
                            session, "YAHOO-FUNDAMENTALS", symbol,
                            "complete" if result.get(symbol, 0) else "empty",
                            rows_ingested=result.get(symbol, 0),
                            metadata={"frequency": "a"},
                        )
            else:
                counts = {symbol: result.get(symbol, 0) for symbol in batch}
                for symbol, count in counts.items():
                    _set_fundamental_ingestion_state(
                        session, "YAHOO-FUNDAMENTALS", symbol,
                        "complete" if count else "empty", rows_ingested=count,
                        metadata={"frequency": "a"},
                    )
            for symbol in batch:
                result.setdefault(symbol, 0)
            session.commit()
    return result


def ingest_yahoo_profiles(
    symbols: Iterable[str],
    database_url: str | None = None,
    chunk_size: int = 50,
) -> dict[str, int]:
    """Synchronize real Yahoo sector classifications into the tracked universe."""

    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    normalized = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
    if not normalized:
        return {}
    try:
        from yahooquery import Ticker
    except ImportError as exc:
        raise RuntimeError("Install Yahoo fundamentals support with `uv sync --extra all`.") from exc

    create_schema(database_url)
    result = {symbol: 0 for symbol in normalized}
    with Session(get_engine(database_url)) as session:
        for offset in range(0, len(normalized), chunk_size):
            batch = normalized[offset : offset + chunk_size]
            try:
                profiles = Ticker(batch).asset_profile
            except Exception:  # noqa: BLE001 - retry individual symbols below
                profiles = {}
                for symbol in batch:
                    try:
                        profiles[symbol] = Ticker(symbol).asset_profile.get(symbol)
                    except Exception:  # noqa: BLE001 - unavailable profiles remain unclassified
                        profiles[symbol] = None
            for symbol in batch:
                profile = profiles.get(symbol) if isinstance(profiles, dict) else None
                if not isinstance(profile, dict):
                    continue
                sector = profile.get("sectorDisp") or profile.get("sector")
                if not sector:
                    continue
                ticker = session.get(TickerSymbol, symbol)
                if ticker is None:
                    continue
                ticker.sector = str(sector)
                result[symbol] = 1
            session.commit()
    return result


def yahoo_frame_to_facts(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Normalize a yahooquery ``all_financial_data`` frame to stored facts."""

    if frame is None or frame.empty:
        return []
    frame = frame.reset_index() if "symbol" not in frame.columns else frame.copy()
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict("records"):
        symbol = str(record.get("symbol") or "").upper()
        period_end = _as_date(record.get("asOfDate"))
        if not symbol or period_end is None:
            continue
        period_type = str(record.get("periodType") or "12M")
        form = f"YAHOO-{period_type}"
        currency = str(record.get("currencyCode") or "reported")
        for concept, value in record.items():
            if concept in _METADATA_COLUMNS or not _is_number(value):
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "cik": None,
                    "taxonomy": "YahooFinance",
                    "concept": str(concept),
                    "unit": _unit_for(concept, currency),
                    "currency": currency if currency not in {"reported", "ratio", "shares"} else None,
                    "period_start": None,
                    "period_end": period_end,
                    # Yahoo's statement endpoint exposes the statement date,
                    # not a filing/publication date. Keep availability
                    # unknown instead of turning the accounting date into a
                    # historical decision-time fact.
                    "filed": None,
                    "form": form,
                    "frame": period_type,
                    "value": float(value),
                    "source_url": YAHOO_FINANCIALS_URL.format(symbol=symbol),
                    "source_document_id": YAHOO_FINANCIALS_URL.format(symbol=symbol),
                    "source_version": f"{period_type}:{period_end.isoformat()}",
                    "context_ref": period_type,
                    "available_on": None,
                    "available_at": None,
                    "availability_status": "unknown",
                    "statement_kind": "unknown",
                    "duration_days": None,
                }
            )
    return rows


def _save_rows(session: Session, rows: list[dict[str, Any]], result: dict[str, int]) -> None:
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_symbol.setdefault(row["symbol"], []).append(row)
    for symbol, symbol_rows in by_symbol.items():
        result[symbol] = _upsert_fundamentals(session, symbol_rows)


def _as_date(value: Any) -> date | None:
    if value is None or pd.isna(value):
        return None
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError):
        return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and pd.notna(value)


def _unit_for(concept: str, currency: str) -> str:
    lowered = concept.lower()
    if "eps" in lowered or "per share" in lowered:
        return f"{currency}/share"
    if (
        "share" in lowered
        and not any(token in lowered for token in ("stockholder", "stockholders", "commonstockequity"))
    ) or "sharesnumber" in lowered or lowered.endswith("shares"):
        return "shares"
    if any(token in lowered for token in ("margin", "rate", "ratio", "yield")):
        return "ratio"
    return currency if currency not in {"ratio", "shares"} else "reported"
