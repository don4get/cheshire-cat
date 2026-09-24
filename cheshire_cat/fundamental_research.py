"""Matched fundamental, price, hybrid, and benchmark research candidates.

The experiment is deliberately small and predeclared. Every candidate consumes
the same dates, prices, universe eligibility mask, transaction cost, and
execution delay. Fundamentals are supplied as point-in-time feature snapshots;
this module does not fill missing facts with current values.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .fundamentals_asof import ASOF_FEATURE_VERSION
from .research import Candidate, MarketPanel, Simulation, metrics, simulate, targets, training_score

FUNDAMENTAL_RESEARCH_VERSION = "matched-fundamental-research-v1"


@dataclass(frozen=True)
class FundamentalCandidate:
    family: str
    features: tuple[str, ...]
    holdings: int = 20
    rebalance: int = 4
    uses_momentum: bool = False

    @property
    def key(self) -> str:
        return f"{self.family}-{self.holdings}-{self.rebalance}w-{'momentum' if self.uses_momentum else 'fundamental'}"


def fundamental_candidate_catalog() -> tuple[FundamentalCandidate, ...]:
    """Candidate family and search budget fixed before evaluation."""

    return (
        FundamentalCandidate("value", ("earnings_yield", "fcf_yield", "book_to_price")),
        FundamentalCandidate("value-sales", ("earnings_yield", "sales_to_price")),
        FundamentalCandidate("profitability", ("gross_margin", "operating_margin", "net_margin")),
        FundamentalCandidate("balance-sheet", ("debt_to_equity",)),
        FundamentalCandidate("quality-value", ("earnings_yield", "fcf_yield", "operating_margin", "debt_to_equity")),
        FundamentalCandidate("hybrid", ("earnings_yield", "operating_margin", "debt_to_equity"), uses_momentum=True),
        FundamentalCandidate("price-momentum", (), uses_momentum=True),
        FundamentalCandidate("benchmark", (), holdings=500),
    )


def build_fundamental_targets(
    panel: MarketPanel,
    candidate: FundamentalCandidate,
    features: pd.DataFrame,
) -> pd.DataFrame:
    """Convert point-in-time feature rows into executable weekly weights."""

    if features.empty:
        return pd.DataFrame(0.0, index=panel.close.index, columns=panel.close.columns)
    values = _feature_matrices(features, panel.close.index, panel.close.columns)
    eligible = panel.eligible.copy()
    scores: list[pd.DataFrame] = []
    for feature in candidate.features:
        matrix = values.get(feature)
        if matrix is None:
            return pd.DataFrame(0.0, index=panel.close.index, columns=panel.close.columns)
        if feature == "debt_to_equity":
            matrix = -matrix
        # All component values must be present on the same decision date.
        eligible &= matrix.notna()
        scores.append(matrix.rank(axis=1, pct=True, method="first"))
    if candidate.uses_momentum:
        momentum = panel.close.shift(4) / panel.close.shift(26) - 1
        eligible &= momentum.notna()
        scores.append(momentum.rank(axis=1, pct=True, method="first"))
    if not scores:
        selected = eligible.astype(float)
    else:
        score = sum(scores) / len(scores)
        selected = (score.where(eligible).rank(axis=1, ascending=False, method="first") <= candidate.holdings).astype(float)
    weights = selected.div(selected.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    if candidate.family not in {"benchmark", "price-momentum"}:
        weights = weights.clip(upper=1 / candidate.holdings)
    schedule = np.arange(len(weights)) % candidate.rebalance == 0
    weights.loc[~schedule] = np.nan
    return weights.ffill().fillna(0.0)


def run_fundamental_experiment(
    panel: MarketPanel,
    features: pd.DataFrame,
    start: int,
    *,
    initial_cash: float = 100_000.0,
    transaction_cost: float = 0.001,
    universe_snapshot_id: str | None = None,
    sector_by_symbol: dict[str, str | None] | None = None,
    candidate_catalog: tuple[FundamentalCandidate, ...] | None = None,
    search_budget: int | None = None,
) -> dict[str, Any]:
    """Run a matched 80/20 experiment and return a versioned manifest/report."""

    if not 1 <= start < len(panel.close):
        raise ValueError("start must leave at least one investment period")
    candidates = tuple(candidate_catalog or fundamental_candidate_catalog())
    if search_budget is not None:
        if search_budget < 1:
            raise ValueError("search_budget must be positive")
        candidates = candidates[:search_budget]
    periods = len(panel.close) - start
    if periods < 20:
        raise ValueError("At least 20 matched periods are required")
    split = start + max(1, int(np.floor(periods * 0.8)))
    train_count = split - start
    manifest = experiment_manifest(
        panel,
        features,
        start=start,
        split=split,
        initial_cash=initial_cash,
        transaction_cost=transaction_cost,
        universe_snapshot_id=universe_snapshot_id,
        sector_by_symbol=sector_by_symbol,
        candidates=candidates,
    )
    trials: list[dict[str, Any]] = []
    simulations: dict[str, Any] = {}
    for candidate in candidates:
        weights = _candidate_targets(panel, candidate, features)
        simulation = simulate(
            panel,
            weights,
            start=start,
            cost=transaction_cost,
            rebalance=candidate.rebalance,
        )
        simulations[candidate.key] = simulation
        training_score_value, folds = training_score(simulation.returns.iloc[:train_count])
        train_metrics = metrics(simulation, initial_cash, slice(0, train_count))
        validation_metrics = metrics(simulation, initial_cash, slice(train_count, None))
        trials.append(
            {
                "id": candidate.key,
                "candidate": asdict(candidate),
                "score": training_score_value,
                "training": train_metrics,
                "validation": validation_metrics,
                "folds": folds,
                "matched_dates": len(simulation.returns),
                "average_exposure": train_metrics["exposure"],
                "concentration_hhi": _weight_hhi(simulation.final_weights),
                "feature_coverage": _feature_coverage(features, panel.close.index[:split]),
            }
        )
    trials.sort(key=lambda row: (-row["score"], row["id"]))
    selected = trials[0]
    selected_candidate = next(candidate for candidate in candidates if candidate.key == selected["id"])
    selected_simulation = simulations[selected["id"]]
    ablations = _ablations(panel, features, selected_candidate, start, split, transaction_cost, initial_cash)
    stress_cost = min(transaction_cost * 2, 0.099)
    stress_weights = _candidate_targets(panel, selected_candidate, features)
    stress = simulate(panel, stress_weights, start=start, cost=stress_cost, rebalance=selected_candidate.rebalance)
    delay_stress = simulate(
        panel,
        stress_weights,
        start=start,
        cost=transaction_cost,
        rebalance=selected_candidate.rebalance,
        execution_delay=2,
    )
    walk_forward = _walk_forward_diagnostics(
        panel,
        features,
        candidates,
        start=start,
        initial_cash=initial_cash,
        transaction_cost=transaction_cost,
    )
    report = {
        "version": FUNDAMENTAL_RESEARCH_VERSION,
        "manifest": manifest,
        "selection": {"id": selected["id"], "candidate": asdict(selected_candidate), "score": selected["score"]},
        "trials": trials,
        "benchmark": next((row for row in trials if row["candidate"]["family"] == "benchmark"), None),
        "strategies": [
            {
                "id": row["id"],
                "candidate": row["candidate"],
                "training": row["training"],
                "validation": row["validation"],
            }
            for row in trials
        ],
        "ablations": ablations,
        "stress": {
            "transaction_cost": stress_cost,
            "validation": metrics(stress, initial_cash, slice(train_count, None)),
            "variants": {
                "double_cost": metrics(stress, initial_cash, slice(train_count, None)),
                "extra_week_execution_delay": metrics(delay_stress, initial_cash, slice(train_count, None)),
            },
        },
        "walk_forward": walk_forward,
        "concentration": {
            "final_weight_hhi": _weight_hhi(selected_simulation.final_weights),
            "final_active_positions": int((selected_simulation.final_weights > 1e-8).sum()),
            "sector_exposure": _sector_exposure(selected_simulation.final_weights, sector_by_symbol),
        },
        "uncertainty": _bootstrap_uncertainty(selected_simulation.returns.iloc[train_count:], seed=17),
        "conclusion": _conclusion(selected, next((row for row in trials if row["candidate"]["family"] == "benchmark"), None)),
        "limitations": [
            "Selection uses training dates only; the 80/20 validation is a single frozen replay, while the separate walk-forward diagnostic is retrospective.",
            "Missing or stale fundamentals make a symbol ineligible; no provider fallback is used.",
            "Currency mismatches and missing FX are excluded; no historical FX conversion is inferred.",
            "A result is not evidence of live tradability, capacity, tax treatment, or a broker order.",
        ],
        "completed_at": datetime.now(UTC).isoformat(),
    }
    json.dumps(report, allow_nan=False)
    return report


def experiment_manifest(
    panel: MarketPanel,
    features: pd.DataFrame,
    *,
    start: int,
    split: int,
    initial_cash: float,
    transaction_cost: float,
    candidates: Iterable[FundamentalCandidate],
    universe_snapshot_id: str | None = None,
    sector_by_symbol: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    dates = panel.close.index
    return {
        "version": FUNDAMENTAL_RESEARCH_VERSION,
        "feature_version": ASOF_FEATURE_VERSION,
        "universe_snapshot_id": universe_snapshot_id,
        "market": panel.metadata.get("market", "custom"),
        "currency": panel.metadata.get("currency", "units"),
        "decision_dates": {
            "start": dates[start].date().isoformat(),
            "training_end": dates[split - 1].date().isoformat(),
            "validation_start": dates[split].date().isoformat() if split < len(dates) else None,
            "end": dates[-1].date().isoformat(),
            "matched_periods": len(dates) - start,
        },
        "initial_cash": initial_cash,
        "transaction_cost": transaction_cost,
        "execution": {"decision_delay_periods": 1, "rebalance_at_close": True},
        "selection_protocol": {
            "walk_forward": "expanding and rolling five-year training windows",
            "initial_train_weeks": 260,
            "selection_gap_weeks": 4,
            "test_weeks": 52,
        },
        "missing_data_policy": "exclude symbol from candidate on that decision date",
        "staleness_policy": "facts are filtered before this experiment by the as-of feature engine",
        "currency_policy": "all price and accounting inputs must agree; missing FX is excluded rather than converted silently",
        "sector_policy": "financial sectors are excluded when sector evidence is available; sector-agnostic runs are labelled in the manifest",
        "sector_by_symbol": sector_by_symbol or {},
        "constraints": {
            "long_only": True,
            "unlevered": True,
            "cash_allowed": True,
            "maximum_position_weight": "1 / holdings for fundamental candidates",
            "execution_delay_periods": 1,
        },
        "objective": "training annualized log growth minus 0.25 times variation across training blocks",
        "search_budget": len(candidates),
        "candidate_families": [asdict(candidate) for candidate in candidates],
        "same_universe_and_cost_for_all": True,
        "data_fingerprint": _feature_fingerprint(panel, features),
    }


def _walk_forward_diagnostics(
    panel: MarketPanel,
    features: pd.DataFrame,
    candidates: tuple[FundamentalCandidate, ...],
    *,
    start: int,
    initial_cash: float,
    transaction_cost: float,
) -> list[dict[str, Any]]:
    """Select a candidate inside each chronological fold and replay its test block."""

    # Import locally to keep the research and audit modules independently usable.
    from .validation import temporal_folds

    target_map = {
        candidate.key: _candidate_targets(panel, candidate, features)
        for candidate in candidates
    }
    benchmark = next(
        (candidate for candidate in candidates if candidate.family == "benchmark"),
        None,
    )
    protocols: list[dict[str, Any]] = []
    for rolling in (False, True):
        name = "Rolling five-year selection" if rolling else "Expanding selection"
        folds = temporal_folds(
            start,
            len(panel.close),
            window=260,
            gap=4,
            test=52,
            rolling=rolling,
        )
        base = {
            "name": name,
            "status": "complete" if folds else "insufficient_history",
            "protocol": {
                "initial_train_weeks": 260,
                "selection_gap_weeks": 4,
                "test_weeks": 52,
                "rolling": rolling,
            },
            "folds": [],
        }
        if not folds:
            base["limitation"] = "At least five years plus the selection gap are required."
            protocols.append(base)
            continue

        strategy_segments: list[Simulation] = []
        benchmark_segments: list[Simulation] = []
        for fold in folds:
            train_start = int(fold["train_start"])
            train_stop = int(fold["train_stop"])
            test_start = int(fold["test_start"])
            test_stop = int(fold["test_stop"])
            scores: list[tuple[float, str, FundamentalCandidate]] = []
            score_log: list[dict[str, Any]] = []
            for candidate in candidates:
                training_simulation = simulate(
                    panel,
                    target_map[candidate.key],
                    start=train_start,
                    cost=transaction_cost,
                    rebalance=candidate.rebalance,
                )
                train_index = panel.close.index[train_start:train_stop]
                train_returns = training_simulation.returns.reindex(train_index).dropna()
                score, _ = training_score(train_returns)
                scores.append((score, candidate.key, candidate))
                score_log.append({"id": candidate.key, "score": score})
            _, selected_key, selected_candidate = sorted(
                scores, key=lambda item: (-item[0], item[1])
            )[0]
            selected_simulation = simulate(
                panel,
                target_map[selected_key],
                start=test_start,
                cost=transaction_cost,
                rebalance=selected_candidate.rebalance,
            )
            test_index = panel.close.index[test_start:test_stop]
            selected_segment = _slice_simulation(selected_simulation, test_index)
            strategy_segments.append(selected_segment)
            benchmark_segment = None
            if benchmark is not None:
                benchmark_simulation = simulate(
                    panel,
                    target_map[benchmark.key],
                    start=test_start,
                    cost=transaction_cost,
                    rebalance=benchmark.rebalance,
                )
                benchmark_segment = _slice_simulation(benchmark_simulation, test_index)
                benchmark_segments.append(benchmark_segment)
            selected_metrics = metrics(selected_segment, initial_cash)
            benchmark_metrics = metrics(benchmark_segment, initial_cash) if benchmark_segment else None
            base["folds"].append(
                {
                    "train_start": panel.close.index[train_start].date().isoformat(),
                    "train_end": panel.close.index[train_stop - 1].date().isoformat(),
                    "test_start": panel.close.index[test_start].date().isoformat(),
                    "test_end": panel.close.index[test_stop - 1].date().isoformat(),
                    "selected_id": selected_key,
                    "selection_scores": sorted(score_log, key=lambda row: row["id"]),
                    "test": selected_metrics,
                    "benchmark": benchmark_metrics,
                    "excess_annualized_return": (
                        selected_metrics["annualized_return"] - benchmark_metrics["annualized_return"]
                        if benchmark_metrics is not None else None
                    ),
                    "partial": bool(fold["partial"]),
                }
            )
        combined = _combine_simulations(strategy_segments)
        combined_benchmark = _combine_simulations(benchmark_segments) if benchmark_segments else None
        base["metrics"] = metrics(combined, initial_cash)
        base["benchmark"] = metrics(combined_benchmark, initial_cash) if combined_benchmark else None
        base["matched_periods"] = len(combined.returns)
        base["winning_folds"] = sum(
            row["excess_annualized_return"] is not None and row["excess_annualized_return"] > 0
            for row in base["folds"]
        )
        protocols.append(base)
    return protocols


def _slice_simulation(simulation: Simulation, index: pd.Index) -> Simulation:
    selected = simulation.returns.reindex(index).dropna().index
    return Simulation(
        simulation.returns.reindex(selected),
        simulation.turnover.reindex(selected),
        simulation.exposure.reindex(selected),
        simulation.costs.reindex(selected),
        simulation.final_weights,
        simulation.stale_losses,
    )


def _combine_simulations(simulations: list[Simulation]) -> Simulation:
    if not simulations:
        raise ValueError("At least one simulation segment is required")
    return Simulation(
        pd.concat([simulation.returns for simulation in simulations]),
        pd.concat([simulation.turnover for simulation in simulations]),
        pd.concat([simulation.exposure for simulation in simulations]),
        pd.concat([simulation.costs for simulation in simulations]),
        simulations[-1].final_weights,
        sum(simulation.stale_losses for simulation in simulations),
    )


def _feature_matrices(features: pd.DataFrame, dates: pd.Index, symbols: pd.Index) -> dict[str, pd.DataFrame]:
    frame = features.copy()
    frame["decision_date"] = pd.to_datetime(frame["decision_date"])
    usable = frame[frame["status"].eq("usable") & frame["value"].notna()]
    result: dict[str, pd.DataFrame] = {}
    for name, group in usable.groupby("feature"):
        pivot = group.pivot_table(index="decision_date", columns="symbol", values="value", aggfunc="last")
        pivot = pivot.reindex(columns=symbols).sort_index()
        result[str(name)] = pivot.reindex(dates, method="ffill")
    return result


def _feature_coverage(features: pd.DataFrame, dates: pd.Index) -> dict[str, Any]:
    if features.empty:
        return {"rows": 0, "symbols": 0, "usable_rows": 0, "rate": 0.0}
    frame = features.copy()
    frame["decision_date"] = pd.to_datetime(frame["decision_date"])
    in_window = frame[frame["decision_date"].isin(dates)]
    usable = in_window[in_window["status"].eq("usable")]
    return {
        "rows": int(len(in_window)),
        "symbols": int(in_window["symbol"].nunique()),
        "usable_rows": int(len(usable)),
        "rate": round(len(usable) / len(in_window), 6) if len(in_window) else 0.0,
    }


def _ablations(
    panel: MarketPanel,
    features: pd.DataFrame,
    candidate: FundamentalCandidate,
    start: int,
    split: int,
    cost: float,
    initial_cash: float,
) -> list[dict[str, Any]]:
    result = []
    for excluded in candidate.features:
        reduced = FundamentalCandidate(
            candidate.family + f"-without-{excluded}",
            tuple(feature for feature in candidate.features if feature != excluded),
            candidate.holdings,
            candidate.rebalance,
            candidate.uses_momentum,
        )
        simulation = simulate(
            panel,
            build_fundamental_targets(panel, reduced, features),
            start=start,
            cost=cost,
            rebalance=reduced.rebalance,
        )
        result.append({"excluded_feature": excluded, "training": metrics(simulation, initial_cash, slice(0, split - start))})
    return result


def _bootstrap_uncertainty(returns: pd.Series, seed: int, replicates: int = 200) -> dict[str, float | int]:
    if returns.empty:
        return {"replicates": 0, "annualized_return_low": 0.0, "annualized_return_high": 0.0}
    rng = np.random.default_rng(seed)
    block = max(1, min(8, len(returns) // 4))
    estimates = []
    for _ in range(replicates):
        starts = rng.integers(0, len(returns), size=max(1, len(returns) // block))
        sampled = np.concatenate([returns.iloc[start : start + block].to_numpy() for start in starts])[: len(returns)]
        estimates.append(float(np.expm1(np.log1p(np.clip(sampled, -0.999999, None)).mean() * 52)))
    low, high = np.percentile(estimates, [2.5, 97.5])
    return {"replicates": replicates, "annualized_return_low": float(low), "annualized_return_high": float(high)}


def _weight_hhi(weights: pd.Series) -> float:
    values = weights[weights > 0].to_numpy(dtype=float)
    return float((values**2).sum()) if len(values) else 0.0


def _sector_exposure(
    weights: pd.Series, sector_by_symbol: dict[str, str | None] | None
) -> dict[str, float]:
    if not sector_by_symbol:
        return {"unknown": float(weights[weights > 0].sum())}
    exposure: dict[str, float] = {}
    for symbol, weight in weights.items():
        if weight <= 0:
            continue
        sector = str(sector_by_symbol.get(str(symbol)) or "unknown")
        exposure[sector] = exposure.get(sector, 0.0) + float(weight)
    return dict(sorted(exposure.items()))


def _feature_fingerprint(panel: MarketPanel, features: pd.DataFrame) -> str:
    digest = hashlib.sha256(panel.fingerprint().encode())
    if not features.empty:
        digest.update(pd.util.hash_pandas_object(features.sort_index(axis=1), index=True).values.tobytes())
    return digest.hexdigest()


def _candidate_targets(
    panel: MarketPanel,
    candidate: FundamentalCandidate,
    features: pd.DataFrame,
) -> pd.DataFrame:
    """Build one candidate's targets, including a real benchmark replay."""

    if candidate.family == "benchmark":
        return targets(
            panel,
            Candidate("benchmark", candidate.holdings, False, rebalance=candidate.rebalance),
        )
    return build_fundamental_targets(panel, candidate, features)


def _conclusion(selected: dict[str, Any], benchmark: dict[str, Any] | None) -> dict[str, Any]:
    if benchmark is None:
        return {
            "status": "incomplete",
            "text": "No benchmark was included in the bounded search budget; no relative conclusion is available.",
        }
    excess = selected["validation"]["annualized_return"] - benchmark["validation"]["annualized_return"]
    return {
        "status": "above_benchmark" if excess > 0 else "not_above_benchmark",
        "validation_annualized_excess": excess,
        "text": (
            "The frozen selection exceeded the matched benchmark in this validation replay."
            if excess > 0
            else "The frozen selection did not exceed the matched benchmark in this validation replay."
        ),
    }
