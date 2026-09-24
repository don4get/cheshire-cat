"""Persist every Atlas trial; freeze selection before retrospective evaluation."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from functools import lru_cache
from threading import Lock
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select, text, update

from .challenger import (
    BATCH1_VERSION,
    BATCH2_VERSION,
    CHALLENGER_VERSION,
    AtlasFeatures,
    AtlasRule,
    ensemble_catalog,
    train_atlas,
)
from .database import ResearchChallenger, ResearchRun, get_engine
from .research import Candidate, load_market, metrics, simulate, targets, training_score
from .validation import rank_past, relative_interval, temporal_folds

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="atlas")
_pending: dict[tuple[str | None, str], Future] = {}
_lock = Lock()


def _where(run_id: str, version: str = CHALLENGER_VERSION):
    return (ResearchChallenger.run_id == run_id, ResearchChallenger.version == version)


def _queue_current(database_url: str | None, run_id: str) -> None:
    # Publish a durable queue row before expensive loading. Otherwise a fresh
    # browser can see "not_started" while the first batch is already running,
    # and a load failure has nowhere to persist its error.
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    engine = get_engine(database_url)
    insert = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    statement = insert(ResearchChallenger).values(
        run_id=run_id, version=CHALLENGER_VERSION, status="queued", progress="Atlas research queued", trials=[],
    ).on_conflict_do_nothing(index_elements=["run_id", "version"])
    with engine.begin() as connection:
        connection.execute(statement)


def challenger_status(database_url: str | None, run_id: str) -> dict[str, Any]:
    with get_engine(database_url).connect() as connection:
        rows = list(connection.execute(select(ResearchChallenger.__table__).where(
            ResearchChallenger.run_id == run_id,
        ).order_by(ResearchChallenger.created_at)).mappings())
        incumbent = connection.execute(select(ResearchRun.selection).where(ResearchRun.id == run_id)).scalar_one_or_none()
    current = next((row for row in rows if row["version"] == CHALLENGER_VERSION), None)
    batches = [{"version": row["version"], "status": row["status"], "trial_count": len(row["trials"]),
                "selection": row["selection"]} for row in rows]
    if current is None:
        return {"run_id": run_id, "status": "not_started", "progress": "Atlas research has not started", "batches": batches}
    report = current["report"]
    if report and incumbent:
        leaderboard = [{"id": row["id"], "score": row["score"], "source": "Original research"}
                       for row in incumbent["leaderboard"]]
        leaderboard.append({"id": "momentum-ensemble", "score": incumbent["ensemble_score"], "source": "Original research"})
        leaderboard.extend({"id": row["id"], "score": row["score"],
                            "source": "Atlas batch 3" if row["id"].startswith("atlas3-") else "Atlas batch 2" if row["id"].startswith("atlas2-") else "Atlas batch 1"}
                           for row in report["trials"])
        leaderboard.sort(key=lambda row: (-row["score"], row["id"]))
        report = {**report, "leaderboard": [dict(row, rank=i + 1) for i, row in enumerate(leaderboard)]}
    return {"run_id": run_id, "status": current["status"], "progress": current["progress"],
            "error": current["error"], "report": report, "batches": batches}


def evaluate_atlas(panel, start: int, original: dict[str, Any], selection: dict[str, Any],
                   trials: list[dict[str, Any]], *, progress=lambda _: None,
                   replicates: int = 1000) -> dict[str, Any]:
    if panel.fingerprint() != selection["data_fingerprint"] or panel.fingerprint() != original["data_fingerprint"]:
        raise ValueError("Atlas and incumbent must use the exact same price snapshot")
    split = start + original["split"]["training_periods"]
    if panel.through(split).fingerprint() != selection["training_fingerprint"]:
        raise ValueError("Atlas training snapshot changed since freezing")
    cost, capital = original["transaction_cost"], original["initial_cash"]
    features = AtlasFeatures(panel)
    frozen = AtlasRule(**selection["winner"]["parameters"])
    rows, returns = [], {}

    @lru_cache(maxsize=5)
    def weights(rule: AtlasRule, phase: int = 0):
        return features.targets(rule, phase=phase)

    selected_sim = None
    for i, trial in enumerate(trials):
        rule = AtlasRule(**trial["parameters"])
        sim = simulate(panel, weights(rule), start=start, cost=cost, rebalance=rule.rebalance,
                       attribution_end=split if rule.key == frozen.key else None)
        train = metrics(sim, capital, slice(0, split - start))
        if not np.isclose(train["total_return"], trial["training"]["total_return"], rtol=1e-8, atol=1e-8):
            raise ValueError(f"Atlas training replay changed: {rule.key}")
        rows.append({**trial, "validation": metrics(sim, capital, slice(split - start, None)),
                     "full": metrics(sim, capital)})
        returns[rule.key] = sim.returns
        if rule.key == frozen.key:
            selected_sim = sim
        if i % 8 == 0:
            progress(f"Replaying all registered Atlas trials {i + 1}/{len(trials)}")
    if selected_sim is None:
        raise ValueError("Frozen rule is absent from the registered trial history")
    chosen = next(row for row in rows if row["id"] == frozen.key)
    equity = capital * (1 + selected_sim.returns).cumprod()
    curve = [{"date": panel.close.index[start - 1].date().isoformat(), "value": capital}] + [
        {"date": date.date().isoformat(), "value": float(value)} for date, value in equity.items()]
    challenger = {**chosen, "name": "Cheshire Atlas", "is_benchmark": False, "curve": curve}
    comparison = [challenger, *original["strategies"]]
    ranks = {period: 1 + sum(row[period]["total_return"] > chosen[period]["total_return"]
                            for row in original["strategies"]) for period in ("training", "validation", "full")}
    incumbent_scores = [row["score"] for row in original["selection"]["leaderboard"]]
    incumbent_scores.append(original["selection"]["ensemble_score"])
    training_rank = 1 + sum(score > chosen["score"] + 1e-12 for score in incumbent_scores) + sum(
        row["score"] > chosen["score"] + 1e-12 for row in trials)
    benchmark = Candidate("benchmark", 500, False)
    reference = simulate(panel, targets(panel, benchmark), start=start, cost=cost, rebalance=4)
    evaluation = slice(split - start, None)
    intervals = [relative_interval(selected_sim.returns.iloc[evaluation], reference.returns.iloc[evaluation],
                                   block=block, replicates=replicates) for block in (4, 13, 26)]
    contributor = str(selected_sim.attribution.idxmax()) if selected_sim.attribution.max() > 0 else None
    stresses = []
    for label, multiplier, delay, phase, remove in (
        ("Original assumptions", 1, 1, 0, False), ("2× costs", 2, 1, 0, False),
        ("5× costs", 5, 1, 0, False), ("Extra week execution delay", 1, 2, 0, False),
        ("Rebalance calendar +1 week", 1, 1, 1, False), ("Top training contributor → cash", 1, 1, 0, True),
    ):
        desired = weights(frozen, phase)
        if remove and contributor:
            desired = desired.copy()
            desired[contributor] = 0.
        stressed = simulate(panel, desired, start=start, cost=cost * multiplier,
                            rebalance=frozen.rebalance, execution_delay=delay, rebalance_phase=phase)
        matched = simulate(panel, targets(panel, benchmark, phase=phase), start=start, cost=cost * multiplier,
                           rebalance=4, execution_delay=delay, rebalance_phase=phase)
        value, base = metrics(stressed, capital, evaluation), metrics(matched, capital, evaluation)
        stresses.append({"label": label, "metrics": value, "benchmark": base,
                         "excess_cagr": value["annualized_return"] - base["annualized_return"]})

    # Cost-aware temporal selection over ALL recorded Atlas configurations.
    matrix = pd.DataFrame(returns)
    catalog = {row["id"]: AtlasRule(**row["parameters"]) for row in trials}
    base_matrix = matrix[[key for key, rule in catalog.items() if not rule.sleeves]]
    walk_forward = []
    for rolling in (False, True):
        folds = temporal_folds(start, len(panel.close), rolling=rolling)
        desired = panel.close * 0.
        schedule = pd.Series(False, index=panel.close.index)
        fold_rows = []
        for i, fold in enumerate(folds):
            left, right = int(fold["test_start"]), int(fold["test_stop"])
            best = rank_past(base_matrix, left=int(fold["train_start"]) - start,
                             right=int(fold["train_stop"]) - start)[0]
            rule = catalog[best]
            if any(candidate.sleeves for candidate in catalog.values()):
                lo, hi = int(fold["train_start"]), int(fold["train_stop"])
                past_trials = [{"id": key, "parameters": asdict(catalog[key]),
                                "score": training_score(base_matrix[key].iloc[lo - start:hi - start])[0]}
                               for key in base_matrix]
                best_score = max(row["score"] for row in past_trials)
                prefix = panel.through(hi)
                for candidate in ensemble_catalog(past_trials):
                    preceding = simulate(prefix, weights(candidate), start=start, cost=cost, rebalance=1)
                    score = training_score(preceding.returns.iloc[lo - start:])[0]
                    if score > best_score:
                        rule, best_score = candidate, score
                best = rule.key
            desired.iloc[left - 1:right - 1] = weights(rule).iloc[left - 1:right - 1]
            schedule.iloc[left:right] = (np.arange(left, right) - 1) % rule.rebalance == 0
            schedule.iloc[left] = True
            fold_rows.append({"selected_id": best, "members": [row.key for row in rule.sleeves] or [best],
                              "train_end": panel.close.index[int(fold["train_stop"]) - 1].date().isoformat(),
                              "test_start": panel.close.index[left].date().isoformat(),
                              "test_end": panel.close.index[right - 1].date().isoformat(),
                              "partial": fold["partial"]})
            progress(f"Atlas {'rolling' if rolling else 'expanding'} walk-forward {i + 1}/{len(folds)}")
        if not folds:
            raise ValueError("Atlas validation requires more than five years of investment history")
        first = int(folds[0]["test_start"])
        executed = simulate(panel, desired, start=first, cost=cost, trade_schedule=schedule)
        matched = simulate(panel, targets(panel, benchmark), start=first, cost=cost, rebalance=4)
        for row, fold in zip(fold_rows, folds, strict=True):
            section = slice(int(fold["test_start"]) - first, int(fold["test_stop"]) - first)
            row.update(total_return=float((1 + executed.returns.iloc[section]).prod() - 1),
                       benchmark_return=float((1 + matched.returns.iloc[section]).prod() - 1))
        walk_forward.append({"name": "Rolling five-year selection" if rolling else "Expanding selection",
                             "metrics": metrics(executed, capital), "benchmark": metrics(matched, capital),
                             "folds": fold_rows,
                             "winning_folds": sum(row["total_return"] > row["benchmark_return"] for row in fold_rows)})
    report = {"version": CHALLENGER_VERSION, "name": "Cheshire Atlas", "market": original["market"],
              "currency": original["currency"], "initial_cash": capital, "transaction_cost": cost,
              "data_fingerprint": panel.fingerprint(), "selection": selection, "split": original["split"],
              "training_rank": training_rank, "training_competitors": len(incumbent_scores) + len(trials),
              "performance_ranks": ranks, "performance_competitors": len(comparison),
              "strategies": comparison, "trials": rows, "intervals": intervals,
              "stresses": stresses, "removed_contributor": contributor, "walk_forward": walk_forward,
              "holdings_date": panel.close.index[-1].date().isoformat(),
              "holdings": [{"symbol": str(symbol), "weight": float(weight)}
                           for symbol, weight in selected_sim.final_weights.sort_values(ascending=False).items() if weight > 1e-8],
              "cash_weight": float(max(0, 1 - selected_sim.final_weights.sum())),
              "completed_at": datetime.now(UTC).isoformat(),
              "limitations": [
                  "All research is retrospective on already-reviewed history; training rank is not proof of a future edge.",
                  "The cumulative search includes prior batches and the original 79 configurations; bootstrap intervals are not adjusted for this entire adaptive search.",
                  "Current listings omit delisted firms. Historical membership and point-in-time price revisions remain unavailable.",
                  "No leverage or shorts; no calibrated impact, taxes, FX or cash yield. Suggested holdings are simulated, not brokerage orders.",
                  "The rank-buffer and allocation improvements were proposed after inspecting batch-1 training results. This is not an independently predeclared multi-batch experiment.",
              ]}
    json.dumps(report, allow_nan=False)
    return report


def build_challenger(database_url: str | None, run_id: str, *, progress=lambda _: None) -> dict[str, Any]:
    engine = get_engine(database_url)
    with engine.connect() as lease:
        key = int.from_bytes(hashlib.sha256(f"atlas:{run_id}".encode()).digest()[:8], "big", signed=True)
        if engine.dialect.name == "postgresql":
            acquired = lease.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar()
            lease.commit()
            if not acquired:
                return challenger_status(database_url, run_id)
        try:
            if challenger_status(database_url, run_id)["status"] == "ready":
                return challenger_status(database_url, run_id)
            with engine.connect() as connection:
                run = connection.execute(select(ResearchRun.__table__).where(ResearchRun.id == run_id)).mappings().one()
            if run["status"] != "complete":
                raise ValueError("Complete the incumbent experiment first")
            _queue_current(database_url, run_id)
            with engine.begin() as connection:
                connection.execute(update(ResearchChallenger).where(*_where(run_id)).values(
                    status="training", progress="Loading the saved input snapshot", error=None))
            panel, start = load_market(database_url, run["market"], run["parameters"]["years"])
            if panel.fingerprint() != run["result"]["data_fingerprint"]:
                raise ValueError("Stored prices changed since the incumbent experiment")
            split = start + run["result"]["split"]["training_periods"]
            selections = []
            trials = []
            for version in (BATCH1_VERSION, BATCH2_VERSION, CHALLENGER_VERSION):
                with engine.begin() as connection:
                    saved = connection.execute(select(ResearchChallenger.__table__).where(*_where(run_id, version))).mappings().first()
                    if saved is None:
                        connection.execute(ResearchChallenger.__table__.insert().values(
                            run_id=run_id, version=version, status="training", progress="Loading training snapshot", trials=[]))
                if saved and saved["selection"]:
                    selections.append(saved["selection"])
                    trials.extend(saved["trials"])
                    continue
                attempt = []

                def save_trial(row, attempt=attempt, version=version):
                    attempt.append(row)
                    with engine.begin() as connection:
                        connection.execute(update(ResearchChallenger).where(*_where(run_id, version)).values(trials=attempt))
                        connection.execute(update(ResearchChallenger).where(*_where(run_id)).values(
                            status="training", progress=f"{version}: saved training trial {len(attempt)}"))

                rows = train_atlas(panel.through(split), start, cost=run["parameters"]["cost"],
                                   capital=run["parameters"]["initial_cash"], progress=progress,
                                   save_trial=save_trial, version=version,
                                   rules=ensemble_catalog(trials) if version == CHALLENGER_VERSION else None)
                frozen = {"winner": rows[0], "training_fingerprint": panel.through(split).fingerprint(),
                          "data_fingerprint": panel.fingerprint(), "frozen_at": datetime.now(UTC).isoformat()}
                with engine.begin() as connection:
                    connection.execute(update(ResearchChallenger).where(*_where(run_id, version)).values(
                        status="frozen", selection=frozen, progress="Winner frozen before evaluation"))
                selections.append(frozen)
                trials.extend(rows)
            selection = max(selections, key=lambda row: row["winner"]["score"])

            def on_progress(message):
                with engine.begin() as connection:
                    connection.execute(update(ResearchChallenger).where(*_where(run_id)).values(status="evaluating", progress=message))
                progress(message)

            report = evaluate_atlas(panel, start, run["result"], selection, trials, progress=on_progress)
            with engine.begin() as connection:
                connection.execute(update(ResearchChallenger).where(*_where(run_id)).values(
                    status="ready", report=report, error=None, progress="Atlas research and diagnostics saved"))
            return challenger_status(database_url, run_id)
        except Exception as exc:
            with engine.begin() as connection:
                connection.execute(update(ResearchChallenger).where(*_where(run_id)).values(status="failed", error=str(exc)))
            raise
        finally:
            if engine.dialect.name == "postgresql":
                lease.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                lease.commit()


def submit_challenger(database_url: str | None, run_id: str) -> dict[str, Any]:
    with _lock:
        status = challenger_status(database_url, run_id)
        if status["status"] == "ready":
            return status
        key = (database_url, run_id)
        pending = _pending.get(key)
        if pending is None or pending.done():
            _queue_current(database_url, run_id)
            _pending[key] = _executor.submit(build_challenger, database_url, run_id)
        return {"run_id": run_id, "status": "evaluating", "progress": "Atlas research queued"}
