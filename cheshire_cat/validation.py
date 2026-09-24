"""Retrospective, cost-aware diagnostics of an immutable research experiment.

Protocol: docs/validation-protocol.md. Nothing here changes a saved selection.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from functools import lru_cache
from itertools import pairwise
from typing import Any

import numpy as np
import pandas as pd

from .portfolio_timeline import ranked_candidates
from .research import Candidate, MarketPanel, metrics, simulate, targets, training_score

AUDIT_VERSION = "robustness-audit-v1"
BOOTSTRAPS = 1000
SEED = 20260920


def temporal_folds(start: int, stop: int, *, window: int = 260, gap: int = 4,
                   test: int = 52, rolling: bool = False) -> list[dict[str, int | bool]]:
    if min(window, test) < 1 or gap < 0:
        raise ValueError("Invalid temporal protocol")
    return [{"train_start": max(start, left - gap - window) if rolling else start,
             "train_stop": left - gap, "test_start": left,
             "test_stop": min(left + test, stop), "partial": left + test > stop}
            for left in range(start + window + gap, stop, test)]


def block_indices(n: int, block: int, replicates: int, seed: int) -> np.ndarray:
    if n < 2 or not 1 <= block <= n or replicates < 1:
        raise ValueError("Insufficient observations or invalid bootstrap settings")
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(replicates, (n + block - 1) // block))
    return ((starts[..., None] + np.arange(block)) % n).reshape(replicates, -1)[:, :n]


def relative_interval(returns: pd.Series, benchmark: pd.Series, *, block: int,
                      replicates: int = BOOTSTRAPS) -> dict[str, float | int]:
    paired = pd.concat([returns, benchmark], axis=1).dropna()
    logs = np.log1p(paired.clip(lower=-0.999999)).to_numpy()
    excess = logs[:, 0] - logs[:, 1]
    indices = block_indices(len(excess), block, replicates, SEED)
    boot = np.expm1(excess[indices].mean(axis=1) * 52)
    return {"block_weeks": block, "observations": len(excess),
            "estimate": float(np.expm1(excess.mean() * 52)),
            "lower": float(np.quantile(boot, 0.025)), "upper": float(np.quantile(boot, 0.975))}


def family_test(returns: pd.DataFrame, benchmark: pd.Series, *,
                replicates: int = BOOTSTRAPS, block: int = 13) -> dict[str, Any]:
    """Joint centered circular-block maximum-mean null, not DSR or PBO."""
    logs = np.log1p(returns.clip(lower=-0.999999)).sub(
        np.log1p(benchmark.clip(lower=-0.999999)), axis=0,
    ).to_numpy()
    if not np.isfinite(logs).all():
        raise ValueError("Family test requires aligned finite weekly returns")
    means = logs.mean(axis=0)
    centered = logs - means
    observed = float(means.max())
    indices = block_indices(len(logs), block, replicates, SEED)
    # Count sampled weeks to avoid allocating replicas × weeks × candidates.
    counts = np.stack([np.bincount(row, minlength=len(logs)) for row in indices])
    maxima = (counts @ centered / len(logs)).max(axis=1)
    return {"candidate_count": returns.shape[1], "replicates": replicates,
            "block_weeks": block, "p_value": float((1 + (maxima >= observed).sum()) / (replicates + 1)),
            "best_annualized_relative_growth": float(np.expm1(observed * 52)),
            "scope": "78 stored base rules only; excludes adaptive ensembles and unrecorded research"}


def rank_past(returns: pd.DataFrame, *, left: int, right: int) -> list[str]:
    """The scoring function receives only the eligible past selection window."""
    past = returns.iloc[left:right]
    return sorted(past.columns, key=lambda key: (-training_score(past[key])[0], key))


def rolling_summary(returns: pd.Series, benchmark: pd.Series) -> dict[str, float]:
    log = np.log1p(returns.clip(lower=-0.999999)).rolling(52).sum().dropna()
    reference = np.log1p(benchmark.clip(lower=-0.999999)).rolling(52).sum().reindex(log.index)
    return {"worst": float(np.expm1(log.min())), "median": float(np.expm1(log.median())),
            "positive_fraction": float((log > 0).mean()),
            "benchmark_win_fraction": float((log > reference).mean())}


def _return(series: pd.Series) -> float:
    return float((1 + series).prod() - 1)


def audit_research(panel: MarketPanel, start: int, result: dict[str, Any], *,
                   progress: Callable[[str], None] = lambda _: None,
                   replicates: int = BOOTSTRAPS) -> dict[str, Any]:
    if panel.fingerprint() != result["data_fingerprint"]:
        raise ValueError("Stored prices changed. Cannot audit this experiment using a different snapshot.")
    if panel.close.index[start].date().isoformat() != result["split"]["training_start"]:
        raise ValueError("Audit window does not match the saved experiment")
    split = start + result["split"]["training_periods"]
    cost, capital = result["transaction_cost"], result["initial_cash"]
    if cost * 5 >= 0.1:
        raise ValueError("Five-times-cost stress must remain below 10% per side")
    stored = result["selection"]["leaderboard"]
    catalog = {row["id"]: Candidate(**row["parameters"]) for row in stored}
    benchmark = Candidate("benchmark", 500, False)

    @lru_cache(maxsize=6)
    def weights(candidate: Candidate, phase: int = 0) -> pd.DataFrame:
        return targets(panel, candidate, phase=phase)

    def blended(members: list[Candidate], phase: int = 0) -> pd.DataFrame:
        return sum(weights(member, phase) for member in members) / len(members)

    returns = {}
    diagnostics = []
    reference = simulate(panel, weights(benchmark), start=start, cost=cost, rebalance=4)
    for i, row in enumerate(stored):
        candidate = catalog[row["id"]]
        sim = simulate(panel, weights(candidate), start=start, cost=cost, rebalance=candidate.rebalance)
        train = sim.returns.iloc[:split - start]
        if not np.isclose(_return(train), row["training"]["total_return"], atol=1e-8, rtol=1e-8):
            raise ValueError(f"Replay disagrees with frozen training result: {candidate.key}")
        returns[candidate.key] = sim.returns
        diagnostics.append({"id": candidate.key, "rank": i + 1, "score": row["score"],
                            "training_cagr": row["training"]["annualized_return"],
                            "evaluation_cagr": metrics(sim, capital, slice(split - start, None))["annualized_return"],
                            "max_drawdown": metrics(sim, capital)["max_drawdown"],
                            **rolling_summary(sim.returns, reference.returns)})
        if i % 8 == 0 or i == len(stored) - 1:
            progress(f"Reconciling frozen base rules {i + 1}/{len(stored)}")
    matrix = pd.DataFrame(returns)

    protocols = []
    for rolling in (False, True):
        name = "Rolling five-year selection" if rolling else "Expanding selection"
        folds = temporal_folds(start, len(panel.close), rolling=rolling)
        if not folds:
            raise ValueError("Audit requires more than five years plus a four-week selection gap")
        desired = pd.DataFrame(0.0, index=panel.close.index, columns=panel.close.columns)
        schedule = pd.Series(False, index=panel.close.index)
        rows = []
        for i, fold in enumerate(folds):
            lo, hi = int(fold["train_start"]), int(fold["train_stop"])
            left, right = int(fold["test_start"]), int(fold["test_stop"])
            ranked = rank_past(matrix, left=lo - start, right=hi - start)
            members = [catalog[key] for key in ranked[:3]]
            prefix = panel.through(hi)
            ensemble = simulate(prefix, blended(members), start=start, cost=cost, rebalance=1)
            ensemble_score = training_score(ensemble.returns.iloc[lo - start:])[0]
            single_score = training_score(matrix[ranked[0]].iloc[lo - start:hi - start])[0]
            if ensemble_score <= single_score:
                members = members[:1]
            frequency = members[0].rebalance if len(members) == 1 else 1
            desired.iloc[left - 1:right - 1] = blended(members).iloc[left - 1:right - 1]
            schedule.iloc[left:right] = (np.arange(left, right) - 1) % frequency == 0
            schedule.iloc[left] = True  # Charge the actual allocation change at the boundary.
            def day(index: int) -> str:
                return panel.close.index[index].date().isoformat()
            rows.append({"train_start": day(lo), "train_end": day(hi - 1),
                         "test_start": day(left), "test_end": day(right - 1),
                         "gap_weeks": 4, "test_weeks": right - left, "partial": fold["partial"],
                         "members": [member.key for member in members],
                         "selection_score": max(ensemble_score, single_score)})
            progress(f"{name}: selecting fold {i + 1}/{len(folds)} using preceding data")
        first = int(folds[0]["test_start"])
        executed = simulate(panel, desired, start=first, cost=cost, rebalance=1, trade_schedule=schedule)
        matched = simulate(panel, weights(benchmark), start=first, cost=cost, rebalance=4)
        for row, fold in zip(rows, folds, strict=True):
            segment = slice(int(fold["test_start"]) - first, int(fold["test_stop"]) - first)
            row.update(total_return=_return(executed.returns.iloc[segment]),
                       benchmark_return=_return(matched.returns.iloc[segment]),
                       turnover=float(executed.turnover.iloc[segment].sum()),
                       fees=float(executed.costs.iloc[segment].sum() * capital))
        equity, baseline = capital * (1 + executed.returns).cumprod(), capital * (1 + matched.returns).cumprod()
        protocols.append({"name": name, "folds": rows, "metrics": metrics(executed, capital),
                          "benchmark": metrics(matched, capital),
                          "winning_folds": sum(row["total_return"] > row["benchmark_return"] for row in rows),
                          "switches": sum(a["members"] != b["members"] for a, b in pairwise(rows)),
                          "fees": float(executed.costs.sum() * capital),
                          "curve": [{"date": panel.close.index[first - 1].date().isoformat(),
                                     "value": capital, "benchmark": capital}] +
                          [{"date": day.date().isoformat(), "value": float(value), "benchmark": float(baseline.loc[day])}
                           for day, value in equity.items()]})
    progress("Estimating joint multiple-comparison diagnostic")
    family = family_test(matrix.iloc[:split - start], reference.returns.iloc[:split - start], replicates=replicates)
    family["scope"] = f"{len(catalog)} stored base rules only; excludes adaptive ensembles and unrecorded research"
    finalists = []
    for finalist in ranked_candidates(result):
        progress(f"Stress tests and uncertainty: frozen rank {finalist['rank']}/3")
        members = [Candidate(**member) for member in finalist["members"]]
        frequency = members[0].rebalance if len(members) == 1 else 1
        desired = blended(members)
        original = simulate(panel, desired, start=start, cost=cost, rebalance=frequency, attribution_end=split)
        contributor = str(original.attribution.idxmax()) if original.attribution.max() > 0 else None
        evaluation = slice(split - start, None)
        intervals = [relative_interval(original.returns.iloc[evaluation], reference.returns.iloc[evaluation],
                                       block=block, replicates=replicates) for block in (4, 13, 26)]
        stresses = []
        for label, factor, delay, phase, remove in (
            ("Original assumptions", 1, 1, 0, False), ("2× trading costs", 2, 1, 0, False),
            ("5× trading costs", 5, 1, 0, False), ("Extra week execution delay", 1, 2, 0, False),
            ("Rebalance calendar +1 week", 1, 1, 1, False), ("Top training contributor → cash", 1, 1, 0, True),
        ):
            stressed_weights = blended(members, phase)
            if remove and contributor:
                stressed_weights = stressed_weights.copy()
                stressed_weights[contributor] = 0.0
            sim = simulate(panel, stressed_weights, start=start, cost=cost * factor,
                           rebalance=frequency, execution_delay=delay,
                           rebalance_phase=phase if len(members) == 1 else 0)
            matched = simulate(panel, weights(benchmark, phase), start=start, cost=cost * factor,
                               rebalance=4, execution_delay=delay, rebalance_phase=phase)
            value, base = metrics(sim, capital, evaluation), metrics(matched, capital, evaluation)
            stresses.append({"label": label, "metrics": value, "benchmark": base,
                             "excess_cagr": value["annualized_return"] - base["annualized_return"],
                             "applicable": not remove or contributor is not None})
        neighbors = []
        for member in members:
            nearby = [row for row in stored if sum(asdict(member)[key] != row["parameters"][key]
                                                  for key in asdict(member)) == 1]
            if nearby:
                values = [row["training"]["annualized_return"] for row in nearby]
                neighbors.append({"member": member.key, "count": len(nearby),
                                  "minimum": float(min(values)), "median": float(np.median(values)),
                                  "maximum": float(max(values)),
                                  "own": next(row["training"]["annualized_return"] for row in stored if row["id"] == member.key)})
        crises = []
        for name, left, right in (("Financial crisis", "2007-10-01", "2009-03-31"),
                                  ("COVID shock", "2020-02-01", "2020-06-30"),
                                  ("2022 inflation shock", "2022-01-01", "2022-12-31")):
            selected = original.returns.loc[left:right]
            if len(selected):
                crises.append({"name": name, "start": selected.index[0].date().isoformat(),
                               "end": selected.index[-1].date().isoformat(), "weeks": len(selected),
                               "total_return": _return(selected),
                               "benchmark_return": _return(reference.returns.reindex(selected.index))})
        finalists.append({**finalist, "removed_contributor": contributor,
                          "intervals": intervals, "stresses": stresses, "neighbors": neighbors,
                          "crises": crises, "rolling": rolling_summary(original.returns, reference.returns)})
    report = {"version": AUDIT_VERSION, "data_fingerprint": panel.fingerprint(),
              "completed_at": datetime.now(UTC).isoformat(), "market": result["market"],
              "currency": result["currency"], "initial_cash": capital,
              "evaluation_start": result["split"]["validation_start"],
              "evaluation_end": result["split"]["validation_end"],
              "protocol": {"initial_train_weeks": 260, "selection_gap_weeks": 4,
                           "test_weeks": 52, "replicates": replicates, "seed": SEED},
              "walk_forward": protocols, "family_test": family, "finalists": finalists,
              "candidates": diagnostics,
              "limitations": [
                  "The original evaluation has already been reviewed. All new diagnostics are retrospective, not a new untouched holdout.",
                  "Today's tracked symbols omit delisted firms and historical membership. Survivorship bias remains unresolved.",
                  "Adjusted prices are current revisions. Historical point-in-time corporate actions are unavailable.",
                  "Flat costs and weekly volume screens do not model calibrated market impact, taxes, FX or cash interest.",
                  "The family-wise test covers stored base rules, not adaptive ensembles or all prior human experimentation.",
                  "Bootstrap intervals are conditional on the sample and serial-dependence model. Rolling windows overlap; they are not independent trials.",
                  "Genuine prospective validation requires freezing a strategy and collecting observations after the last stored bar.",
              ]}
    json.dumps(report, allow_nan=False)
    weights.cache_clear()
    return report
