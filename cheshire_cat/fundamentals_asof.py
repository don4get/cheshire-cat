"""Point-in-time fundamental features with conservative provenance.

This module is intentionally independent from a live data provider.  It accepts
the rows already stored by the SEC/Yahoo importers and applies one rule at the
decision boundary: a fact is usable only when its public availability date is
known and strictly earlier than the decision date.  Provider retrieval dates or
fiscal period ends are never substituted for publication evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

import pandas as pd

from .fundamental_ratios import _ALIASES
from .database import FundamentalFeatureSnapshot, create_schema, get_engine
from sqlalchemy.orm import Session

ASOF_FEATURE_VERSION = "fundamentals-asof-v1"
VERIFIED_AVAILABILITY = frozenset({"verified", "date_only"})
FINANCIAL_SECTORS = frozenset(
    {
        "financial services",
        "financials",
        "banks - diversified",
        "banks - regional",
        "insurance",
    }
)


@dataclass(frozen=True)
class AsOfPolicy:
    """The reproducibility policy used when selecting historical facts."""

    max_staleness_days: int = 548
    strict_prior_day: bool = True
    allowed_availability: frozenset[str] = VERIFIED_AVAILABILITY
    exclude_financial_sectors: bool = True
    feature_version: str = ASOF_FEATURE_VERSION


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    formula: str
    inputs: tuple[str, ...]
    kind: str


def asof_snapshot_key(
    facts: pd.DataFrame | Iterable[dict[str, Any]] | Iterable[Any],
    decision_date: date | str,
    policy: AsOfPolicy | None = None,
    prices: pd.DataFrame | Iterable[dict[str, Any]] | None = None,
    dataset_version: str = "stored-fundamental-ledger-v1",
) -> str:
    """Return a stable cache key for an as-of feature snapshot."""

    policy = policy or AsOfPolicy()
    frame = normalize_facts(facts)
    if not frame.empty:
        frame = frame.sort_values(list(frame.columns)).reset_index(drop=True)
        payload = pd.util.hash_pandas_object(frame, index=False).values.tobytes()
    else:
        payload = b"empty"
    digest = hashlib.sha256()
    digest.update((policy.feature_version or ASOF_FEATURE_VERSION).encode())
    digest.update(dataset_version.encode())
    digest.update(str(pd.Timestamp(decision_date).date()).encode())
    digest.update(str(policy).encode())
    digest.update(payload)
    if prices is not None:
        price_frame = _normalize_prices(prices)
        digest.update(
            pd.util.hash_pandas_object(price_frame.sort_values(list(price_frame.columns)), index=False)
            .values.tobytes()
        )
    return digest.hexdigest()


def store_asof_snapshot(
    features: pd.DataFrame,
    *,
    key: str,
    dataset_version: str = "stored-fundamental-ledger-v1",
    decision_date: date | str,
    feature_version: str = ASOF_FEATURE_VERSION,
    database_url: str | None = None,
) -> str:
    """Persist an immutable feature snapshot keyed by data, cutoff and version."""

    create_schema(database_url)
    records = json.loads(json.dumps(features.to_dict("records"), default=str))
    engine = get_engine(database_url)
    with Session(engine) as session:
        existing = session.get(FundamentalFeatureSnapshot, key)
        if existing is not None:
            return existing.key
        session.add(
            FundamentalFeatureSnapshot(
                key=key,
                dataset_version=dataset_version,
                as_of=pd.Timestamp(decision_date).date(),
                feature_version=feature_version,
                payload=records,
            )
        )
        session.commit()
    return key


def load_asof_snapshot(
    key: str, database_url: str | None = None
) -> pd.DataFrame | None:
    """Load a cached snapshot without recalculating or selecting new facts."""

    create_schema(database_url)
    with Session(get_engine(database_url)) as session:
        snapshot = session.get(FundamentalFeatureSnapshot, key)
        if snapshot is None:
            return None
        return pd.DataFrame(snapshot.payload)


FEATURE_DEFINITIONS: tuple[FeatureDefinition, ...] = (
    FeatureDefinition("earnings_yield", "net_income / market_cap", ("net_income", "market_cap"), "value"),
    FeatureDefinition("fcf_yield", "free_cash_flow / market_cap", ("free_cash_flow", "market_cap"), "value"),
    FeatureDefinition("book_to_price", "equity / market_cap", ("equity", "market_cap"), "value"),
    FeatureDefinition("sales_to_price", "revenue / market_cap", ("revenue", "market_cap"), "value"),
    FeatureDefinition("gross_margin", "gross_profit / revenue", ("gross_profit", "revenue"), "quality"),
    FeatureDefinition("operating_margin", "operating_income / revenue", ("operating_income", "revenue"), "quality"),
    FeatureDefinition("net_margin", "net_income / revenue", ("net_income", "revenue"), "quality"),
    FeatureDefinition("cash_conversion", "operating_cash_flow / net_income", ("operating_cash_flow", "net_income"), "quality"),
    FeatureDefinition("debt_to_equity", "debt / equity", ("debt", "equity"), "balance_sheet"),
)

_FLOW_KEYS = frozenset(
    {
        "revenue",
        "net_income",
        "operating_income",
        "ebitda",
        "gross_profit",
        "free_cash_flow",
        "operating_cash_flow",
        "eps",
    }
)


def normalize_facts(facts: pd.DataFrame | Iterable[dict[str, Any]] | Iterable[Any]) -> pd.DataFrame:
    """Return fact rows with stable date and provenance columns.

    SQLAlchemy model instances, dictionaries, and DataFrames are accepted so
    the same selection logic can be used by jobs, API handlers, and tests.
    Missing columns are added rather than inferred from fiscal dates.
    """

    if isinstance(facts, pd.DataFrame):
        frame = facts.copy()
    else:
        rows: list[dict[str, Any]] = []
        for item in facts:
            if isinstance(item, dict):
                rows.append(dict(item))
            else:
                rows.append(
                    {
                        key: getattr(item, key)
                        for key in (
                            "symbol",
                            "taxonomy",
                            "concept",
                            "unit",
                            "currency",
                            "period_start",
                            "period_end",
                            "filed",
                            "form",
                            "frame",
                            "value",
                            "source_url",
                            "source_document_id",
                            "source_version",
                            "context_ref",
                            "available_on",
                            "available_at",
                            "availability_status",
                            "statement_kind",
                            "duration_days",
                        )
                        if hasattr(item, key)
                    }
                )
        frame = pd.DataFrame(rows)
    required = {
        "symbol": None,
        "taxonomy": None,
        "concept": None,
        "unit": None,
        "currency": None,
        "period_start": None,
        "period_end": None,
        "filed": None,
        "form": "",
        "value": None,
        "source_url": None,
        "source_document_id": None,
        "source_version": None,
        "context_ref": None,
        "available_on": None,
        "available_at": None,
        "availability_status": "unknown",
        "statement_kind": "unknown",
        "duration_days": None,
    }
    for column, default in required.items():
        if column not in frame.columns:
            frame[column] = default
    for column in ("period_start", "period_end", "filed", "available_on", "available_at"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["concept"] = frame["concept"].astype(str)
    frame["form"] = frame["form"].astype(str)
    frame["currency"] = frame.apply(
        lambda row: _currency_for_row(row.to_dict()), axis=1
    )
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["duration_days"] = pd.to_numeric(frame["duration_days"], errors="coerce")
    return frame


def select_asof_facts(
    facts: pd.DataFrame | Iterable[dict[str, Any]] | Iterable[Any],
    decision_date: date | str,
    policy: AsOfPolicy | None = None,
) -> pd.DataFrame:
    """Select the latest known version of each period at a decision date.

    The returned frame includes ``excluded_reason`` for every supplied row.
    Rows with ``selected=True`` are the observations the feature builder may
    use.  Keeping rejected rows makes coverage audits explainable.
    """

    policy = policy or AsOfPolicy()
    frame = normalize_facts(facts)
    cutoff = pd.Timestamp(decision_date).normalize()
    if frame.empty:
        frame["selected"] = pd.Series(dtype=bool)
        frame["excluded_reason"] = pd.Series(dtype=object)
        frame["freshness_days"] = pd.Series(dtype="float64")
        return frame

    frame["freshness_days"] = (cutoff - frame["available_on"]).dt.days
    frame["selected"] = False
    frame["excluded_reason"] = ""
    frame.loc[frame["available_on"].isna(), "excluded_reason"] = "unknown_publication_date"
    frame.loc[
        frame["available_on"].notna()
        & ~frame["availability_status"].isin(policy.allowed_availability),
        "excluded_reason",
    ] = "unverified_publication_date"
    boundary = frame["available_on"] < cutoff if policy.strict_prior_day else frame["available_on"] <= cutoff
    frame.loc[
        (frame["excluded_reason"] == "") & ~boundary,
        "excluded_reason",
    ] = "published_on_or_after_decision"
    frame.loc[
        (frame["excluded_reason"] == "")
        & (frame["freshness_days"] > policy.max_staleness_days),
        "excluded_reason",
    ] = "stale_at_decision"
    frame.loc[
        (frame["excluded_reason"] == "")
        & (frame["period_end"].notna())
        & (frame["period_end"] > cutoff),
        "excluded_reason",
    ] = "period_not_ended"
    frame.loc[
        (frame["excluded_reason"] == "") & frame["value"].isna(),
        "excluded_reason",
    ] = "non_numeric_value"

    eligible = frame["excluded_reason"] == ""
    # First preserve every known revision, then select the latest version of a
    # fiscal observation. A filing amended before the cutoff therefore wins;
    # an amendment filed later cannot rewrite an earlier backtest.
    identity = [
        "symbol",
        "taxonomy",
        "concept",
        "unit",
        "period_start",
        "period_end",
        "form",
        "context_ref",
    ]
    order = frame.assign(
        _available_sort=frame["available_on"].fillna(pd.Timestamp.min),
        _timestamp_sort=frame["available_at"].fillna(pd.Timestamp.min),
        _version_sort=frame["source_version"].fillna(""),
    ).sort_values(identity + ["_available_sort", "_timestamp_sort", "_version_sort"])
    selected_indices = order[eligible.loc[order.index]].groupby(identity, dropna=False).tail(1).index
    frame.loc[selected_indices, "selected"] = True
    duplicate_mask = eligible & ~frame.index.isin(selected_indices)
    frame.loc[duplicate_mask, "excluded_reason"] = "superseded_version_at_decision"
    return frame


def compute_asof_features(
    facts: pd.DataFrame | Iterable[dict[str, Any]] | Iterable[Any],
    prices: pd.DataFrame | Iterable[dict[str, Any]] | None,
    decision_date: date | str,
    policy: AsOfPolicy | None = None,
    symbols: Iterable[str] | None = None,
    sector_by_symbol: dict[str, str | None] | None = None,
) -> pd.DataFrame:
    """Build value/quality features and provenance rows for one decision date."""

    policy = policy or AsOfPolicy()
    selected = select_asof_facts(facts, decision_date, policy)
    requested = {str(symbol).upper() for symbol in symbols} if symbols is not None else None
    if requested is not None:
        selected = selected[selected["symbol"].isin(requested)].copy()
    prices_frame = _normalize_prices(prices)
    rows: list[dict[str, Any]] = []
    for symbol in sorted(selected["symbol"].dropna().unique()):
        symbol_facts = selected[(selected["symbol"] == symbol) & selected["selected"]]
        financial_sector = (
            policy.exclude_financial_sectors
            and str((sector_by_symbol or {}).get(symbol) or "").strip().lower() in FINANCIAL_SECTORS
        )
        inputs = {
            key: _latest_metric(symbol_facts, aliases, key in _FLOW_KEYS)
            for key, aliases in _ALIASES.items()
        }
        price_row = prices_frame[prices_frame["symbol"] == symbol]
        selected_price = _price_at_or_before(price_row, decision_date)
        price = selected_price["price"] if selected_price is not None else None
        if price is not None:
            inputs["price"] = _Input(value=price, row=selected_price)
        shares = inputs.get("shares")
        market_cap = (
            _Input(value=price * shares.value, row=_merge_rows(price, selected_price, shares.row))
            if price is not None and shares is not None and shares.value > 0
            else None
        )
        inputs["market_cap"] = market_cap
        for definition in FEATURE_DEFINITIONS:
            missing = [name for name in definition.inputs if inputs.get(name) is None]
            denominator = inputs.get(definition.inputs[-1])
            zero_denominator = denominator is not None and denominator.value == 0
            source_rows = [inputs[name].row for name in definition.inputs if inputs.get(name)]
            provenance = _provenance(source_rows)
            input_provenance = {
                name: _input_provenance(inputs.get(name)) for name in definition.inputs
            }
            currencies = {
                _currency_for_row(inputs[name].row)
                for name in definition.inputs
                if inputs.get(name) and _currency_for_row(inputs[name].row)
            }
            if financial_sector:
                value = None
                reason = "financial_sector_policy"
            elif len(currencies) > 1:
                value = None
                reason = "currency_mismatch"
            elif missing:
                value = None
                reason = "missing_input:" + ",".join(missing)
            elif zero_denominator:
                value = None
                reason = "zero_denominator"
            else:
                value = float(inputs[definition.inputs[0]].value / denominator.value)
                reason = None
            rows.append(
                {
                    "symbol": symbol,
                    "decision_date": pd.Timestamp(decision_date).date(),
                    "feature": definition.name,
                    "kind": definition.kind,
                    "formula": definition.formula,
                    "value": value,
                    "status": "usable" if value is not None else "excluded",
                    "excluded_reason": reason,
                    "currency": next(iter(currencies), None) if len(currencies) == 1 else None,
                    "price_basis": (selected_price or {}).get("price_basis"),
                    "price_date": (selected_price or {}).get("price_date"),
                    "input_provenance": input_provenance,
                    "available_on": provenance.get("available_on"),
                    "freshness_days": provenance.get("freshness_days"),
                    "source_document_id": provenance.get("source_document_id"),
                    "source_version": provenance.get("source_version"),
                    "source_url": provenance.get("source_url"),
                    "period_start": provenance.get("period_start"),
                    "period_end": provenance.get("period_end"),
                    "feature_version": policy.feature_version,
                }
            )
    return pd.DataFrame(rows, columns=[
        "symbol", "decision_date", "feature", "kind", "formula", "value", "status",
        "excluded_reason", "available_on", "freshness_days", "source_document_id",
        "source_version", "period_start", "period_end", "feature_version",
        "source_url", "currency", "price_basis", "price_date", "input_provenance",
    ])


def compute_asof_fundamental_ratios(
    facts: pd.DataFrame | Iterable[dict[str, Any]] | Iterable[Any],
    prices: pd.DataFrame | Iterable[dict[str, Any]] | None,
    decision_date: date | str,
    policy: AsOfPolicy | None = None,
    symbols: Iterable[str] | None = None,
    sector_by_symbol: dict[str, str | None] | None = None,
) -> pd.DataFrame:
    """Return familiar ratios from the same leakage-safe feature snapshot.

    Valuation multiples are the reciprocal of their corresponding yield. A
    non-positive yield is left excluded rather than presenting a misleading
    negative or infinite multiple.
    """

    features = compute_asof_features(
        facts,
        prices,
        decision_date,
        policy=policy,
        symbols=symbols,
        sector_by_symbol=sector_by_symbol,
    )
    names = {
        "earnings_yield": "pe",
        "sales_to_price": "ps",
        "book_to_price": "pb",
        "fcf_yield": "fcf_yield",
        "gross_margin": "gross_margin",
        "operating_margin": "operating_margin",
        "net_margin": "net_margin",
        "debt_to_equity": "debt_equity",
    }
    rows: list[dict[str, Any]] = []
    for row in features.to_dict("records"):
        ratio = names.get(row["feature"])
        if ratio is None:
            continue
        output = dict(row)
        output["ratio"] = ratio
        if ratio in {"pe", "ps", "pb"} and row["value"] is not None:
            if row["value"] <= 0:
                output["value"] = None
                output["status"] = "excluded"
                output["excluded_reason"] = "non_positive_yield"
            else:
                output["value"] = 1.0 / row["value"]
        rows.append(output)
    return pd.DataFrame(rows)


# Short name for callers that already use the term “as-of ratios”.
compute_asof_ratios = compute_asof_fundamental_ratios


@dataclass(frozen=True)
class _Input:
    value: float
    row: dict[str, Any] | None


def _latest_metric(frame: pd.DataFrame, aliases: Iterable[str], flow: bool) -> _Input | None:
    candidate = frame[frame["concept"].isin(tuple(aliases))].copy()
    if candidate.empty:
        return None
    annual = candidate[candidate["form"].str.contains("10-K|20-F|40-F|YAHOO-12M", regex=True)]
    if flow and not annual.empty:
        candidate = annual
    elif flow:
        candidate = _annual_or_ttm(candidate)
    if candidate.empty:
        return None
    candidate["period_sort"] = candidate["period_end"].fillna(pd.Timestamp.min)
    candidate["alias_rank"] = candidate["concept"].map(
        {name: index for index, name in enumerate(tuple(aliases))}
    ).fillna(999)
    candidate = candidate.sort_values(
        ["period_sort", "available_on", "alias_rank"], ascending=[False, False, True]
    )
    row = candidate.iloc[0].to_dict()
    return _Input(value=float(row["value"]), row=row)


def _annual_or_ttm(candidate: pd.DataFrame) -> pd.DataFrame:
    annual = candidate[candidate["duration_days"].between(300, 400, inclusive="both")]
    if not annual.empty:
        return annual
    # Do not add YTD observations together. Four distinct quarter-like
    # durations are the only fallback that is safe enough for a compact engine.
    quarters = candidate[candidate["duration_days"].between(70, 110, inclusive="both")].copy()
    # A source can expose multiple contexts or revisions for one quarter. The
    # as-of selector keeps them for auditability; TTM construction must count
    # each fiscal end once, choosing the latest available observation.
    quarters = (
        quarters.sort_values(["period_end", "available_on", "available_at"])
        .drop_duplicates(["period_end"], keep="last")
    )
    if len(quarters) < 4:
        return candidate.iloc[0:0]
    latest_end = quarters["period_end"].max()
    recent = quarters[quarters["period_end"] >= latest_end - pd.Timedelta(days=370)]
    recent = recent.sort_values("period_end").tail(4)
    if len(recent) < 4 or (
        recent["period_end"].diff().dropna().dt.days > 130
    ).any():
        return candidate.iloc[0:0]
    row = recent.iloc[-1].copy()
    row["value"] = recent["value"].sum()
    row["period_start"] = recent["period_start"].min()
    row["duration_days"] = int((row["period_end"] - row["period_start"]).days + 1)
    row["source_document_id"] = ";".join(str(item) for item in recent["source_document_id"].dropna())
    row["source_version"] = ";".join(str(item) for item in recent["source_version"].dropna())
    return pd.DataFrame([row])


def _provenance(rows: list[dict[str, Any] | None]) -> dict[str, Any]:
    actual = [row for row in rows if row]
    if not actual:
        return {}
    latest = max(actual, key=lambda row: row.get("available_on") or pd.Timestamp.min)
    return {
        key: latest.get(key)
        for key in (
            "available_on",
            "freshness_days",
            "source_document_id",
            "source_version",
            "source_url",
            "period_start",
            "period_end",
        )
    }


def _normalize_prices(prices: pd.DataFrame | Iterable[dict[str, Any]] | None) -> pd.DataFrame:
    if prices is None:
        return pd.DataFrame(columns=["symbol", "date", "price", "currency", "price_basis"])
    frame = prices.copy() if isinstance(prices, pd.DataFrame) else pd.DataFrame(list(prices))
    if frame.empty:
        return pd.DataFrame(columns=["symbol", "date", "price", "currency", "price_basis"])
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    price_column = "adj_close" if "adj_close" in frame.columns else "close"
    frame["price"] = pd.to_numeric(frame[price_column], errors="coerce")
    if "currency" not in frame.columns:
        frame["currency"] = None
    if "price_basis" not in frame.columns:
        frame["price_basis"] = "adjusted_close" if price_column == "adj_close" else "close"
    frame["price_date"] = frame["date"].dt.date
    return frame[["symbol", "date", "price", "currency", "price_basis", "price_date"]].dropna(
        subset=["date", "price"]
    )


def _price_at_or_before(frame: pd.DataFrame, decision_date: date | str) -> dict[str, Any] | None:
    if frame.empty:
        return None
    candidate = frame[frame["date"] <= pd.Timestamp(decision_date)]
    if candidate.empty:
        return None
    row = candidate.sort_values("date").iloc[-1]
    return row.to_dict()


def _merge_rows(
    price: float,
    price_row: dict[str, Any] | None,
    row: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        **row,
        "price_at_decision": price,
        "price_date": (price_row or {}).get("price_date"),
        "price_basis": (price_row or {}).get("price_basis"),
        "price_currency": (price_row or {}).get("currency"),
    }


def _currency_for_row(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    explicit = row.get("currency")
    if explicit is None or pd.isna(explicit) or str(explicit).lower() in {"reported", "unknown", "nan"}:
        explicit = row.get("price_currency")
    if explicit is not None and not pd.isna(explicit) and str(explicit).lower() not in {"reported", "unknown", "nan"}:
        return str(explicit).upper()
    unit = str(row.get("unit") or "").strip()
    token = unit.split("/", 1)[0].upper()
    if token in {"SHARES", "SHARE", "RATIO", "PURE", "PERCENT", "%", ""}:
        return None
    return token


def _input_provenance(value: _Input | None) -> dict[str, Any] | None:
    if value is None or value.row is None:
        return None
    row = value.row
    return {
        key: row.get(key)
        for key in (
            "source_document_id", "source_version", "source_url", "available_on",
            "period_start", "period_end", "currency", "price_date", "price_basis",
        )
        if row.get(key) is not None
    }
