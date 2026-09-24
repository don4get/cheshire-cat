"""Cheshire Atlas: registered momentum/defensive challengers, no brokerage access."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import cached_property
from itertools import product
from typing import Any

import numpy as np
import pandas as pd

from .research import MarketPanel, metrics, simulate, training_score

BATCH1_VERSION = "atlas-batch1-v1"
BATCH2_VERSION = "atlas-batch2-v1"
CHALLENGER_VERSION = "atlas-batch3-v1"


@dataclass(frozen=True)
class AtlasRule:
    signal: str = "consensus"
    holdings: int = 20
    defensive: bool = True
    rebalance: int = 4
    construction: str = "clipped"
    weighting: str = "inverse_volatility"
    sleeves: tuple[AtlasRule, ...] = ()

    def __post_init__(self) -> None:
        if self.signal not in {"6m", "12m", "risk_adjusted", "continuous", "near_high", "consensus", "top3_ensemble", "signal_ensemble"}:
            raise ValueError("Unknown Atlas signal")
        if self.holdings < 1 or self.rebalance < 1:
            raise ValueError("Holdings and rebalance interval must be positive")
        if self.construction not in {"clipped", "bounded", "ensemble"} or self.weighting not in {"equal", "inverse_volatility", "equal_sleeves"}:
            raise ValueError("Unknown Atlas portfolio construction")
        object.__setattr__(self, "sleeves", tuple(AtlasRule(**row) if isinstance(row, dict) else row for row in self.sleeves))
        if self.construction == "ensemble" and (not self.sleeves or any(row.sleeves for row in self.sleeves)):
            raise ValueError("An Atlas ensemble requires non-nested component rules")

    @property
    def key(self) -> str:
        if self.construction == "ensemble":
            return f"atlas3-{self.signal}"
        if self.construction == "bounded":
            return f"atlas2-{self.signal}-{self.holdings}-{self.weighting}-{self.rebalance}w"
        return f"atlas-{self.signal}-{self.holdings}-{'defensive' if self.defensive else 'trend'}-{self.rebalance}w"


def atlas_catalog(version: str = BATCH2_VERSION) -> tuple[AtlasRule, ...]:
    if version == BATCH1_VERSION:
        return tuple(AtlasRule(*values) for values in product(
            ("risk_adjusted", "continuous", "near_high", "consensus"),
            (10, 20, 40), (False, True),
        ))
    if version == BATCH2_VERSION:
        return tuple(AtlasRule(signal, holdings, False, frequency, "bounded", weighting)
                     for signal, holdings, frequency, weighting in product(
                         ("6m", "12m", "risk_adjusted", "continuous"), (10, 20, 40),
                         (4, 13), ("equal", "inverse_volatility")))
    raise ValueError("Unknown registered Atlas batch")


def ensemble_catalog(trials: list[dict[str, Any]]) -> tuple[AtlasRule, ...]:
    """Two training-adaptive compositions; no validation scores are accepted."""
    ranked = sorted((row for row in trials if row["id"].startswith("atlas2-")),
                    key=lambda row: (-row["score"], row["id"]))
    unique, signals, seen = [], [], set()
    signal_seen = set()
    for row in ranked:
        member = AtlasRule(**row["parameters"])
        # With <=10 active slots and a 10% name cap, both weighting choices
        # always produce the same allocation. Do not duplicate those sleeves.
        signature = (member.signal, member.holdings, member.rebalance,
                     "equal" if member.holdings == 10 else member.weighting)
        if signature not in seen:
            unique.append(member)
            seen.add(signature)
        if member.signal not in signal_seen:
            signals.append(member)
            signal_seen.add(member.signal)
    if len(unique) < 2:
        raise ValueError("At least two structurally distinct trained rules are needed")
    return tuple(AtlasRule(name, sum(rule.holdings for rule in members), False, 1,
                           "ensemble", "equal_sleeves", tuple(members))
                 for name, members in (("top3_ensemble", unique[:3]), ("signal_ensemble", signals)))


def bounded_allocation(raw: np.ndarray, cap: float) -> np.ndarray:
    """Redistribute capped allocations without exceeding cash or name limits."""
    if raw.ndim != 1 or not np.isfinite(raw).all() or (raw < 0).any() or not 0 < cap <= 1:
        raise ValueError("Allocation inputs must be finite, nonnegative and capped in (0, 1]")
    weights = np.zeros_like(raw, dtype=float)
    remaining = raw > 0
    budget = min(1., float(remaining.sum()) * cap)
    while remaining.any() and budget > 1e-12:
        proposed = raw[remaining] / raw[remaining].sum() * budget
        overflow = proposed > cap
        if not overflow.any():
            weights[remaining] = proposed
            break
        fixed = np.flatnonzero(remaining)[overflow]
        weights[fixed] = cap
        budget -= len(fixed) * cap
        remaining[fixed] = False
    return weights


@dataclass
class AtlasFeatures:
    panel: MarketPanel

    @cached_property
    def eligible(self) -> pd.DataFrame:
        return self.panel.eligible & self.panel.above_trend & (self.panel.scores["12m"] > 0)

    @cached_property
    def signals(self) -> dict[str, pd.DataFrame]:
        def ranked(frame: pd.DataFrame) -> pd.DataFrame:
            return frame.where(self.eligible).rank(axis=1, pct=True)

        vol = self.panel.volatility.clip(lower=.10)
        momentum = ranked(self.panel.scores["12m"])
        positive = (self.panel.close.pct_change(fill_method=None) > 0).astype(float).shift(4).rolling(48, min_periods=48).mean()
        risk_adjusted = (ranked(self.panel.scores["6m"] / vol) + ranked(self.panel.scores["12m"] / vol)) / 2
        continuous = (momentum + ranked(positive)) / 2
        high = self.panel.close.shift(4) / self.panel.close.rolling(52, min_periods=48).max().shift(4)
        near_high = (momentum + ranked(high)) / 2
        return {"risk_adjusted": risk_adjusted, "continuous": continuous,
                "near_high": near_high, "consensus": (risk_adjusted + continuous + near_high) / 3,
                "6m": ranked(self.panel.scores["6m"]), "12m": momentum}

    @cached_property
    def market_risk(self) -> pd.Series:
        # Historical eligible universe, held with the same two-bar separation.
        eligible = self.panel.eligible.astype(float)
        basket = eligible.div(eligible.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
        returns = (basket.shift(2).fillna(0) * self.panel.returns).sum(axis=1)
        index = (1 + returns).cumprod()
        return pd.Series(np.where(index >= index.rolling(40, min_periods=40).mean(), 1., .5), index=index.index)

    def targets(self, rule: AtlasRule, *, phase: int = 0) -> pd.DataFrame:
        if rule.construction == "ensemble":
            return sum(self.targets(member, phase=phase) for member in rule.sleeves) / len(rule.sleeves)
        rank = self.signals[rule.signal].where(self.eligible).rank(axis=1, ascending=False, method="first")
        if rule.construction == "bounded":
            return self._buffered_targets(rule, rank, phase)
        selected = (rank <= rule.holdings).astype(float).div(self.panel.volatility.clip(lower=.10)).fillna(0)
        desired = selected.div(selected.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
        desired = desired.clip(upper=min(.10, 1 / rule.holdings))
        schedule = (np.arange(len(desired)) - phase) % rule.rebalance == 0
        desired.loc[~schedule] = np.nan
        desired = desired.ffill().fillna(0)
        # Trailing risk of executable lagged target portfolios; no use of a
        # future return or of today's weights against today's price move.
        shadow = (desired.shift(2).fillna(0) * self.panel.returns).sum(axis=1)
        volatility = shadow.rolling(26, min_periods=20).std() * np.sqrt(52)
        exposure = (.20 / volatility.replace(0, np.nan)).clip(upper=1).fillna(.5)
        if rule.defensive:
            exposure *= self.market_risk
        desired = desired.mul(exposure, axis=0)
        desired.loc[~schedule] = np.nan
        return desired.ffill().fillna(0)

    def _buffered_targets(self, rule: AtlasRule, ranks: pd.DataFrame, phase: int) -> pd.DataFrame:
        ranking = ranks.to_numpy()
        volatility = self.panel.volatility.clip(lower=.10).to_numpy()
        desired = np.zeros(ranking.shape)
        held = np.zeros(ranking.shape[1], dtype=bool)
        previous = np.zeros(ranking.shape[1])
        for t in range(len(ranking)):
            if (t - phase) % rule.rebalance == 0:
                # Keep qualifying names until they fall below twice the target
                # rank, then fill vacancies. Explicitly avoids chasing tiny
                # changes in rank at every rebalance.
                held &= ranking[t] <= 2 * rule.holdings
                vacancies = rule.holdings - int(held.sum())
                available = np.where(~held & np.isfinite(ranking[t]), ranking[t], np.inf)
                entrants = np.argsort(available, kind="stable")[:vacancies]
                held[entrants[np.isfinite(available[entrants])]] = True
                raw = held.astype(float)
                if rule.weighting == "inverse_volatility":
                    raw = np.divide(raw, volatility[t], out=np.zeros_like(raw), where=np.isfinite(volatility[t]))
                previous = bounded_allocation(raw, min(.10, 2 / rule.holdings))
            desired[t] = previous
        return pd.DataFrame(desired, index=ranks.index, columns=ranks.columns)


def train_atlas(panel: MarketPanel, start: int, *, cost: float = .001,
                capital: float = 100_000, progress: Callable[[str], None] = lambda _: None,
                save_trial: Callable[[dict[str, Any]], None] = lambda _: None,
                version: str = BATCH2_VERSION,
                rules: tuple[AtlasRule, ...] | None = None) -> list[dict[str, Any]]:
    """Accept a training-only panel; persist every attempted parameterization."""
    features = AtlasFeatures(panel)
    rows = []
    catalog = rules if rules is not None else atlas_catalog(version)
    for i, rule in enumerate(catalog):
        progress(f"Atlas training candidate {i + 1}/{len(catalog)}: {rule.key}")
        sim = simulate(panel, features.targets(rule), start=start, cost=cost, rebalance=rule.rebalance)
        score, folds = training_score(sim.returns)
        row = {"id": rule.key, "parameters": asdict(rule), "score": score,
               "training": metrics(sim, capital), "folds": folds}
        save_trial(row)
        rows.append(row)
    return sorted(rows, key=lambda row: (-row["score"], row["id"]))
