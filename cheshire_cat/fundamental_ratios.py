"""Transparent ratio calculations over stored source observations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": (
        "Revenue",
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "OperatingRevenue",
        "TotalRevenue",
    ),
    "net_income": (
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncome",
        "NetIncomeCommonStockholders",
        "NetIncomeFromContinuingOperationNetMinorityInterest",
        "NetIncomeFromContinuingOperations",
    ),
    "operating_income": (
        "OperatingIncomeLoss",
        "OperatingIncome",
        "OperatingIncomeFromContinuingOperations",
        "TotalOperatingIncomeAsReported",
    ),
    "ebitda": ("EBITDA", "Ebitda", "NormalizedEBITDA"),
    "gross_profit": ("GrossProfit",),
    "equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "CommonStockholdersEquity",
        "CommonStockEquity",
        "TotalEquityGrossMinorityInterest",
    ),
    "assets": ("Assets", "TotalAssets"),
    "debt": (
        "LongTermDebtAndCapitalLeaseObligation",
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
        "LongTermDebt",
        "TotalDebt",
        "TotalDebtAndCapitalLeaseObligation",
    ),
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
        "CashAndCashEquivalents",
        "CashFinancial",
    ),
    "free_cash_flow": ("FreeCashFlow",),
    "operating_cash_flow": (
        "NetCashProvidedByUsedInOperatingActivities",
        "OperatingCashFlow",
        "TotalCashFromOperatingActivities",
    ),
    "eps": (
        "EarningsPerShareDiluted",
        "EarningsPerShareBasic",
        "DilutedEPS",
        "BasicEPS",
    ),
    "shares": (
        "EntityCommonStockSharesOutstanding",
        "CommonStockSharesOutstanding",
        "OrdinarySharesNumber",
        "DilutedAverageShares",
        "BasicAverageShares",
    ),
}

_RATIO_LABELS = (
    ("pe", "P/E", "multiple"),
    ("ps", "P/S", "multiple"),
    ("pb", "P/B", "multiple"),
    ("ev_ebitda", "EV/EBITDA", "multiple"),
    ("gross_margin", "Gross margin", "percent"),
    ("operating_margin", "Operating margin", "percent"),
    ("net_margin", "Net margin", "percent"),
    ("roe", "ROE", "percent"),
    ("roa", "ROA", "percent"),
    ("debt_equity", "Debt / equity", "multiple"),
    ("fcf_margin", "FCF margin", "percent"),
)


def compute_fundamental_ratios(
    facts: pd.DataFrame,
    price: float | None,
) -> list[dict[str, Any]]:
    """Compute major ratios from the latest compatible stored observations."""

    values: dict[str, float | None] = {}
    sources: dict[str, str | None] = {}
    periods: list[str] = []
    for key, aliases in _ALIASES.items():
        observation = _latest_observation(facts, aliases)
        if observation is None:
            values[key] = None
            sources[key] = None
            continue
        values[key] = observation["value"]
        sources[key] = "SEC XBRL" if observation["taxonomy"] != "YahooFinance" else "Yahoo Finance"
        periods.append(str(observation["period_end"]))

    shares = values["shares"]
    market_cap = price * shares if price is not None and shares and shares > 0 else None
    enterprise_value = (
        market_cap + values["debt"] - values["cash"]
        if market_cap is not None and values["debt"] is not None and values["cash"] is not None
        else None
    )
    raw: dict[str, float | None] = {
        "pe": _divide(price, values["eps"]),
        "ps": _divide(market_cap, values["revenue"]),
        "pb": _divide(market_cap, values["equity"]),
        "ev_ebitda": _divide(enterprise_value, values["ebitda"]),
        "gross_margin": _divide(values["gross_profit"], values["revenue"]),
        "operating_margin": _divide(values["operating_income"], values["revenue"]),
        "net_margin": _divide(values["net_income"], values["revenue"]),
        "roe": _divide(values["net_income"], values["equity"]),
        "roa": _divide(values["net_income"], values["assets"]),
        "debt_equity": _divide(values["debt"], values["equity"]),
        "fcf_margin": _divide(values["free_cash_flow"], values["revenue"]),
    }
    source = next((value for value in sources.values() if value), None)
    period_end = max(periods) if periods else None
    return [
        {
            "key": key,
            "label": label,
            "value": raw[key],
            "kind": kind,
            "source": source,
            "period_end": period_end,
        }
        for key, label, kind in _RATIO_LABELS
    ]


def relevant_concepts() -> set[str]:
    """Return aliases useful for a lightweight peer-comparison query."""

    return {concept for concepts in _ALIASES.values() for concept in concepts}


def _latest_observation(facts: pd.DataFrame, aliases: Iterable[str]) -> dict[str, Any] | None:
    if facts.empty or "concept" not in facts.columns:
        return None
    aliases = tuple(aliases)
    candidate = facts[facts["concept"].isin(aliases)].copy()
    if candidate.empty:
        return None
    candidate["period_sort"] = pd.to_datetime(candidate["period_end"], errors="coerce")
    candidate["filed_sort"] = pd.to_datetime(candidate["filed"], errors="coerce")
    annual = candidate[candidate["form"].astype(str).str.contains("10-K|20-F|40-F|YAHOO-12M", regex=True)]
    if not annual.empty:
        candidate = annual
    candidate["alias_rank"] = candidate["concept"].map({name: index for index, name in enumerate(aliases)})
    candidate["unit_rank"] = candidate["unit"].astype(str).str.lower().map(
        lambda value: 1 if value in {"shares", "ratio"} else 0
    )
    candidate = candidate.sort_values(
        ["period_sort", "filed_sort", "alias_rank", "unit_rank"],
        ascending=[False, False, True, True],
    )
    row = candidate.iloc[0]
    return row.to_dict()


def _divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return float(numerator / denominator)
