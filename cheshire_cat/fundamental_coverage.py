"""Auditable point-in-time fundamentals coverage checks.

Coverage is measured before any return calculation.  The report keeps the
denominator, publication-date failures, staleness, and missing concepts
visible so a sparse feed cannot look like a complete backtest.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any, Iterable

import pandas as pd

from .fundamentals_asof import ASOF_FEATURE_VERSION, AsOfPolicy, normalize_facts, select_asof_facts

COVERAGE_VERSION = "fundamental-coverage-v1"
PILOT_VERSION = "fundamental-pilot-v1"


def build_pilot_manifest(
    issuers: Iterable[str],
    periods: Iterable[date | str],
    sources: Iterable[str],
    *,
    publication_policy: str,
    source_evidence: Iterable[dict[str, Any]] = (),
    reconciliation: Iterable[dict[str, Any]] = (),
    decision: str = "pilot-only",
) -> dict[str, Any]:
    """Build the bounded source-pilot record used before return calculations.

    Evidence is admitted only when it has a source identity, durable URL,
    checksum, and verified or date-only publication status. Missing or
    ambiguous rows remain in the manifest with an explicit quarantine reason;
    they are never converted into a synthetic filing date.
    """

    if decision not in {"go", "no-go", "pilot-only"}:
        raise ValueError("decision must be go, no-go, or pilot-only")
    issuer_list = sorted({str(issuer).upper() for issuer in issuers if str(issuer).strip()})
    period_list = sorted({pd.Timestamp(period).date().isoformat() for period in periods})
    source_list = sorted({str(source) for source in sources if str(source).strip()})
    if not issuer_list or not period_list or not source_list:
        raise ValueError("a pilot requires issuers, periods, and sources")

    expected = {(issuer, period) for issuer in issuer_list for period in period_list}
    evidence_rows: list[dict[str, Any]] = []
    observed: set[tuple[str, str]] = set()
    for raw in source_evidence:
        row = dict(raw)
        issuer = str(row.get("issuer") or row.get("symbol") or "").upper()
        period = _pilot_date(row.get("period"), row.get("period_end"))
        source = str(row.get("source") or "")
        status = str(row.get("publication_status") or row.get("availability_status") or "unknown")
        reason = None
        if (issuer, period) not in expected:
            reason = "outside_selected_pilot"
        elif source not in source_list:
            reason = "source_not_declared"
        elif status not in {"verified", "date_only"}:
            reason = "publication_timing_unknown"
        elif not row.get("source_document_id") and not row.get("accession"):
            reason = "missing_source_identity"
        elif not row.get("source_url"):
            reason = "missing_source_url"
        elif not row.get("checksum"):
            reason = "missing_source_checksum"
        if reason is None:
            observed.add((issuer, period))
        evidence_rows.append(
            {
                **row,
                "issuer": issuer,
                "period": period,
                "source": source,
                "publication_status": status,
                "admitted": reason is None,
                "quarantine_reason": reason,
            }
        )

    reconciliation_rows = [dict(row) for row in reconciliation]
    reconciliation_failures = sum(
        str(row.get("status") or "unknown").lower()
        not in {"pass", "passed", "ok", "reconciled"}
        for row in reconciliation_rows
    )
    missing = sorted(expected - observed)
    unknown_or_quarantined = len(missing) + sum(not row["admitted"] for row in evidence_rows)
    go_ready = bool(expected) and not missing and not unknown_or_quarantined and not reconciliation_failures
    return {
        "version": PILOT_VERSION,
        "issuers": issuer_list,
        "periods": period_list,
        "sources": source_list,
        "publication_policy": publication_policy,
        "source_evidence": evidence_rows,
        "reconciliation": reconciliation_rows,
        "expected_records": len(expected),
        "admitted_records": sum(row["admitted"] for row in evidence_rows),
        "missing_records": [
            {"issuer": issuer, "period": period} for issuer, period in missing
        ],
        "unknown_or_quarantined_records": unknown_or_quarantined,
        "reconciliation_failures": reconciliation_failures,
        "decision": decision,
        "go_no_go": {
            "ready_for_scale": go_ready,
            "criteria": [
                "Every selected issuer-period has traceable source evidence.",
                "Publication timing is verified or explicitly date-only under the stated policy.",
                "Reported values, units, periods, and amendments reconcile before scale-up.",
            ],
        },
    }


def audit_fundamental_coverage(
    facts: pd.DataFrame | Iterable[dict[str, Any]] | Iterable[Any],
    decision_dates: Iterable[date | str],
    universe: pd.DataFrame | Iterable[dict[str, Any]] | None = None,
    required_concepts: Iterable[str] | None = None,
    policy: AsOfPolicy | None = None,
    reports: pd.DataFrame | Iterable[dict[str, Any]] | None = None,
    ingestion_states: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return coverage tables for each requested decision date.

    ``universe`` may contain ``symbol`` and optional ``market`` columns.  If it
    is omitted, the observed fact symbols are used as an explicitly labelled
    fact universe, not as evidence that the investable universe was complete.
    """

    policy = policy or AsOfPolicy()
    source = normalize_facts(facts)
    universe_frame = _normalize_universe(universe, source)
    state_rows = list(ingestion_states) if ingestion_states is not None else None
    required = {str(item) for item in (required_concepts or ())}
    dates = sorted({pd.Timestamp(item).date() for item in decision_dates})
    snapshots: list[dict[str, Any]] = []
    for decision_date in dates:
        selected = select_asof_facts(source, decision_date, policy)
        for market, cohort in universe_frame.groupby("market", dropna=False):
            symbols = set(cohort["symbol"])
            observed = selected[selected["symbol"].isin(symbols)]
            usable = observed[observed["selected"]]
            by_symbol = {
                symbol: set(rows["concept"])
                for symbol, rows in usable.groupby("symbol")
            }
            if required:
                ready_symbols = {
                    symbol for symbol, concepts in by_symbol.items() if required.issubset(concepts)
                }
            else:
                ready_symbols = set(by_symbol)
            reason_counts = Counter(
                str(reason)
                for reason in observed.loc[~observed["selected"], "excluded_reason"]
                if reason
            )
            snapshots.append(
                {
                    "decision_date": decision_date.isoformat(),
                    "market": str(market),
                    "universe_symbols": len(symbols),
                    "symbols_with_any_observation": len(by_symbol),
                    "symbols_ready_for_required_concepts": len(ready_symbols),
                    "usable_fact_rows": int(len(usable)),
                    "coverage_rate": _rate(len(ready_symbols), len(symbols)),
                    "fact_coverage_rate": _rate(len(by_symbol), len(symbols)),
                    "exclusion_reasons": dict(sorted(reason_counts.items())),
                    "missing_symbols": sorted(symbols - set(by_symbol)),
                    "ingestion_progress": _ingestion_progress(state_rows, symbols),
                }
            )
    return {
        "version": COVERAGE_VERSION,
        "feature_version": policy.feature_version or ASOF_FEATURE_VERSION,
        "policy": {
            "max_staleness_days": policy.max_staleness_days,
            "strict_prior_day": policy.strict_prior_day,
            "allowed_availability": sorted(policy.allowed_availability),
            "exclude_financial_sectors": policy.exclude_financial_sectors,
        },
        "required_concepts": sorted(required),
        "observed_fact_inventory": _inventory(source),
        "report_inventory": _report_inventory(reports),
        "ingestion_progress": _ingestion_inventory(state_rows),
        "snapshots": snapshots,
        "recommended_windows": recommend_coverage_windows(snapshots),
        "source_assessment": {
            "SEC-XBRL": {
                "accessibility": "public",
                "publication_evidence": "filing date only unless a timestamped artifact is separately archived",
                "operational_note": "respect SEC user-agent and request-rate requirements",
            },
            "AMF": {
                "accessibility": "public official issuer-report endpoint",
                "publication_evidence": "deposit date is retained; report artifact checksum is stored",
                "operational_note": "availability and schema should be rechecked per issuer",
            },
            "YahooFinance": {
                "accessibility": "provider endpoint",
                "publication_evidence": "unknown in this importer",
                "operational_note": "not eligible for historical as-of features without independent evidence",
            },
        },
        "limitations": [
            "Coverage describes stored observations, not proof that the source universe was complete.",
            "Facts with unknown or unverified public availability are excluded from point-in-time use.",
            "No return or portfolio result is calculated by this audit.",
        ],
    }


def recommend_coverage_windows(
    snapshots: list[dict[str, Any]],
    minimum_coverage: float = 0.8,
    max_gap_days: int = 31,
) -> list[dict[str, Any]]:
    """Find contiguous date runs where every market meets a threshold.

    Dates are supplied by the caller, so a run is considered contiguous when
    adjacent observations are no more than ``max_gap_days`` apart. The exact
    qualifying dates are retained; a missing middle observation never gets
    silently filled.
    """

    if max_gap_days < 1:
        raise ValueError("max_gap_days must be positive")

    qualifying = [
        row for row in snapshots if row["coverage_rate"] is not None and row["coverage_rate"] >= minimum_coverage
    ]
    grouped: dict[str, list[str]] = {}
    for row in qualifying:
        grouped.setdefault(row["market"], []).append(row["decision_date"])
    windows = []
    for market, dates in sorted(grouped.items()):
        ordered = sorted(dates)
        run = [ordered[0]]
        for current in ordered[1:]:
            if (date.fromisoformat(current) - date.fromisoformat(run[-1])).days <= max_gap_days:
                run.append(current)
            else:
                windows.append(_coverage_window(market, run, minimum_coverage, max_gap_days))
                run = [current]
        windows.append(_coverage_window(market, run, minimum_coverage, max_gap_days))
    return windows


def _coverage_window(
    market: str, dates: list[str], minimum_coverage: float, max_gap_days: int
) -> dict[str, Any]:
    return {
        "market": market,
        "start": dates[0],
        "end": dates[-1],
        "decision_dates": len(dates),
        "decision_dates_exact": dates,
        "maximum_gap_days": max_gap_days,
        "minimum_coverage": minimum_coverage,
    }


def _ingestion_progress(
    states: Iterable[dict[str, Any]] | None, symbols: set[str]
) -> dict[str, int]:
    if states is None:
        return {"not_started": len(symbols), "in_progress": 0, "complete": 0,
                "empty": 0, "unavailable": 0, "failed": 0, "error": 0}
    counts = Counter(str(row.get("status") or "not_started") for row in states if row.get("symbol") in symbols)
    result = {status: int(counts.get(status, 0)) for status in (
        "not_started", "in_progress", "complete", "empty", "unavailable", "failed", "error"
    )}
    represented = sum(result.values())
    result["not_started"] += max(0, len(symbols) - represented)
    return result


def _ingestion_inventory(states: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if states is None:
        return []
    return [dict(row) for row in states]


def _normalize_universe(
    universe: pd.DataFrame | Iterable[dict[str, Any]] | None,
    facts: pd.DataFrame,
) -> pd.DataFrame:
    if universe is None:
        frame = pd.DataFrame({"symbol": sorted(facts["symbol"].dropna().unique())})
        frame["market"] = "observed-facts"
        return frame
    frame = universe.copy() if isinstance(universe, pd.DataFrame) else pd.DataFrame(list(universe))
    if "symbol" not in frame.columns:
        raise ValueError("universe must contain a symbol column")
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    if "market" not in frame.columns:
        frame["market"] = "unspecified"
    frame["market"] = frame["market"].fillna("unspecified").astype(str)
    return frame[["symbol", "market"]].drop_duplicates()


def _inventory(facts: pd.DataFrame) -> list[dict[str, Any]]:
    if facts.empty:
        return []
    group_columns = [
        "symbol",
        "taxonomy",
        "concept",
        "unit",
        "form",
        "availability_status",
        "period_end",
        "available_on",
    ]
    counts = facts.groupby(group_columns, dropna=False).size().reset_index(name="rows")
    result: list[dict[str, Any]] = []
    for row in counts.to_dict("records"):
        normalized = {}
        for key, value in row.items():
            if pd.isna(value):
                normalized[key] = None
            elif isinstance(value, (pd.Timestamp, date)):
                normalized[key] = value.isoformat()
            else:
                normalized[key] = value
        result.append(normalized)
    return result


def _report_inventory(reports: pd.DataFrame | Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if reports is None:
        return []
    frame = reports.copy() if isinstance(reports, pd.DataFrame) else pd.DataFrame(list(reports))
    if frame.empty:
        return []
    for column in ("filing_date", "period_end"):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    group_columns = [
        column for column in ("symbol", "form", "filing_date", "period_end", "source_url")
        if column in frame.columns
    ]
    if not group_columns:
        return []
    counts = frame.groupby(group_columns, dropna=False).size().reset_index(name="rows")
    result = []
    for row in counts.to_dict("records"):
        result.append(
            {
                key: None if pd.isna(value) else value.isoformat() if isinstance(value, pd.Timestamp) else value
                for key, value in row.items()
            }
        )
    return result


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _pilot_date(value: Any, fallback: Any = None) -> str:
    candidate = value if value is not None else fallback
    if candidate is None:
        return ""
    try:
        return pd.Timestamp(candidate).date().isoformat()
    except (TypeError, ValueError):
        return ""
