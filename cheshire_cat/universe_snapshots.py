"""Versioned historical universe snapshots and effective-dated events."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import UniverseMembership, UniverseSnapshot, create_schema, get_engine
from .universe import TickerRecord

UNIVERSE_SNAPSHOT_VERSION = "universe-snapshot-v1"


@dataclass(frozen=True)
class UniverseEvent:
    symbol: str
    effective_on: date
    event_type: str
    new_symbol: str | None = None
    sector: str | None = None
    previous_sector: str | None = None
    exchange: str | None = None
    name: str | None = None
    isin: str | None = None


def resolve_membership(
    records: Iterable[TickerRecord],
    events: Iterable[UniverseEvent | dict[str, Any]] = (),
    as_of: date | str | None = None,
) -> list[TickerRecord]:
    """Apply only events effective on or before ``as_of``.

    A caller that has no historical listing feed can still create a snapshot,
    but should label it ``current_snapshot_only`` rather than implying that the
    current source reconstructed old membership.
    """

    cutoff = date.max if as_of is None else _date(as_of)
    by_symbol = {record.symbol.upper(): record for record in records}
    normalized_events = sorted((_event(item) for item in events), key=lambda item: item.effective_on)
    for event in normalized_events:
        symbol = event.symbol.upper()
        current = by_symbol.get(symbol)
        if event.event_type.lower() in {"delist", "delisted", "remove"}:
            if event.effective_on <= cutoff:
                by_symbol.pop(symbol, None)
            elif current is None:
                by_symbol[symbol] = TickerRecord(
                    symbol=symbol,
                    exchange=event.exchange or "unknown",
                    name=event.name,
                    isin=event.isin,
                    sector=event.sector,
                    source="effective-dated-event",
                )
            continue
        if event.event_type.lower() in {"rename", "ticker_change", "symbol_change"}:
            if event.effective_on <= cutoff and event.new_symbol and current is not None:
                by_symbol.pop(symbol, None)
                by_symbol[event.new_symbol.upper()] = replace(current, symbol=event.new_symbol.upper())
            elif event.new_symbol and event.new_symbol.upper() in by_symbol and event.effective_on > cutoff:
                # ``records`` is often today's universe, so a current ticker
                # may need to be reversed for a pre-rename snapshot.
                current = by_symbol.pop(event.new_symbol.upper())
                by_symbol[symbol] = replace(current, symbol=symbol)
            continue
        if event.event_type.lower() in {"sector_change", "sector"} and current is not None:
            if event.effective_on <= cutoff:
                by_symbol[symbol] = replace(current, sector=event.sector)
            elif event.previous_sector is not None:
                by_symbol[symbol] = replace(current, sector=event.previous_sector)
            continue
        if event.event_type.lower() in {"list", "listed", "ipo"}:
            if event.effective_on <= cutoff and current is None:
                by_symbol[symbol] = TickerRecord(
                    symbol=symbol,
                    exchange=event.exchange or "unknown",
                    name=event.name,
                    isin=event.isin,
                    sector=event.sector,
                    source="effective-dated-event",
                )
            elif event.effective_on > cutoff:
                # Current-source rows can include an IPO that was not yet
                # listed at the historical decision date.
                by_symbol.pop(symbol, None)
            continue
    return sorted(by_symbol.values(), key=lambda record: record.symbol)


def build_universe_snapshot(
    records: Iterable[TickerRecord],
    as_of: date | str,
    market: str,
    events: Iterable[UniverseEvent | dict[str, Any]] = (),
    source: str = "current-universe-source",
    historical_status: str | None = None,
    min_price: float | None = None,
    price_by_symbol: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Create a deterministic, serializable universe snapshot manifest."""

    snapshot_date = _date(as_of)
    events = list(events)
    resolved = resolve_membership(records, events, snapshot_date)
    status = historical_status or ("event_reconstructed" if events else "current_snapshot_only")
    memberships = []
    for record in resolved:
        price = (price_by_symbol or {}).get(record.symbol)
        price_eligible = None if min_price is None else price is not None and price >= min_price
        memberships.append(
            {
                "symbol": record.symbol,
                "exchange": record.exchange,
                "name": record.name,
                "isin": record.isin,
                "currency": record.currency,
                "sector": record.sector,
                "pea_eligible": record.pea_eligible,
                "membership_status": "active",
                "historical_status": status,
                "price_eligible": price_eligible,
                "liquidity_eligible": None,
                "completeness_status": "unknown",
                "price_observation_date": None,
                "price_freshness_days": None,
                "median_dollar_volume": None,
                "fundamental_coverage": None,
                "exclusion_reason": None if price_eligible is not False else "price_below_threshold",
                "source": record.source,
            }
        )
    payload = {
        "as_of": snapshot_date.isoformat(),
        "market": market,
        "version": UNIVERSE_SNAPSHOT_VERSION,
        "source": source,
        "historical_status": status,
        "memberships": memberships,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode()
    payload["id"] = f"{market.lower()}-{snapshot_date.isoformat()}-{hashlib.sha256(encoded).hexdigest()[:16]}"
    payload["metadata"] = {
        "event_count": len(events),
        "limitations": [
            "Current-source snapshots do not establish historical listing membership.",
            "Delisting outcomes, historical sector classifications, and FX observations are unknown unless supplied by an effective-dated source.",
            "Price and liquidity eligibility are unknown unless explicit as-of inputs are supplied.",
            "Sector is as-of only when supplied by an effective-dated source/event.",
        ],
    }
    return payload


def annotate_eligibility(
    snapshot: dict[str, Any],
    evidence_by_symbol: dict[str, dict[str, Any]],
    *,
    min_price: float = 0.0,
    min_median_dollar_volume: float = 0.0,
    max_price_freshness_days: int = 7,
    min_fundamental_coverage: float = 0.0,
) -> dict[str, Any]:
    """Attach rebalance-date price, liquidity, freshness, and completeness evidence."""

    output = {**snapshot, "memberships": []}
    for membership in snapshot["memberships"]:
        row = dict(membership)
        evidence = evidence_by_symbol.get(row["symbol"], {})
        price = evidence.get("price")
        volume = evidence.get("median_dollar_volume")
        freshness = evidence.get("price_freshness_days")
        coverage = evidence.get("fundamental_coverage")
        row.update(
            {
                "price_eligible": price is not None and float(price) >= min_price,
                "liquidity_eligible": volume is not None and float(volume) >= min_median_dollar_volume,
                "price_observation_date": evidence.get("price_observation_date"),
                "price_freshness_days": freshness,
                "median_dollar_volume": volume,
                "fundamental_coverage": coverage,
                "completeness_status": "complete" if coverage is not None and coverage >= min_fundamental_coverage else "incomplete",
            }
        )
        reasons = []
        if not row["price_eligible"]:
            reasons.append("price_below_threshold_or_missing")
        if not row["liquidity_eligible"]:
            reasons.append("liquidity_below_threshold_or_missing")
        if freshness is None or freshness > max_price_freshness_days:
            reasons.append("stale_or_missing_price")
        if row["completeness_status"] != "complete":
            reasons.append("fundamental_coverage_below_threshold")
        row["exclusion_reason"] = ";".join(reasons) or None
        output["memberships"].append(row)
    output["metadata"] = {
        **(snapshot.get("metadata") or {}),
        "eligibility_thresholds": {
            "min_price": min_price,
            "min_median_dollar_volume": min_median_dollar_volume,
            "max_price_freshness_days": max_price_freshness_days,
            "min_fundamental_coverage": min_fundamental_coverage,
        },
    }
    return output


def store_universe_snapshot(
    snapshot: dict[str, Any], database_url: str | None = None
) -> str:
    """Persist an append-only snapshot and its memberships idempotently."""

    create_schema(database_url)
    engine = get_engine(database_url)
    with Session(engine) as session:
        existing = session.get(UniverseSnapshot, snapshot["id"])
        if existing is not None:
            return existing.id
        session.add(
            UniverseSnapshot(
                id=snapshot["id"],
                market=snapshot["market"],
                as_of=_date(snapshot["as_of"]),
                version=snapshot["version"],
                source=snapshot["source"],
                historical_status=snapshot["historical_status"],
                metadata_json=snapshot.get("metadata"),
            )
        )
        session.flush()
        session.add_all(
            UniverseMembership(
                snapshot_id=snapshot["id"],
                as_of=_date(snapshot["as_of"]),
                **membership,
            )
            for membership in snapshot["memberships"]
        )
        session.commit()
    return snapshot["id"]


def load_universe_snapshot(snapshot_id: str, database_url: str | None = None) -> dict[str, Any] | None:
    create_schema(database_url)
    with Session(get_engine(database_url)) as session:
        snapshot = session.get(UniverseSnapshot, snapshot_id)
        if snapshot is None:
            return None
        memberships = session.scalars(
            select(UniverseMembership).where(UniverseMembership.snapshot_id == snapshot_id)
        ).all()
        return {
            "id": snapshot.id,
            "market": snapshot.market,
            "as_of": snapshot.as_of.isoformat(),
            "version": snapshot.version,
            "source": snapshot.source,
            "historical_status": snapshot.historical_status,
            "metadata": snapshot.metadata_json,
            "memberships": [
                {
                    key: getattr(row, key)
                    for key in (
                        "symbol", "exchange", "name", "isin", "currency", "sector",
                        "pea_eligible", "membership_status", "historical_status",
                        "price_eligible", "liquidity_eligible", "completeness_status",
                        "price_observation_date", "price_freshness_days", "median_dollar_volume",
                        "fundamental_coverage",
                        "exclusion_reason", "source",
                    )
                }
                for row in memberships
            ],
        }


def _event(item: UniverseEvent | dict[str, Any]) -> UniverseEvent:
    if isinstance(item, UniverseEvent):
        return item
    return UniverseEvent(
        symbol=str(item["symbol"]),
        effective_on=_date(item["effective_on"]),
        event_type=str(item["event_type"]),
        new_symbol=item.get("new_symbol"),
        sector=item.get("sector"),
        previous_sector=item.get("previous_sector"),
        exchange=item.get("exchange"),
        name=item.get("name"),
        isin=item.get("isin"),
    )


def _date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))
