"""Historical holdings for frozen research candidates, without model selection."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from threading import Lock
from typing import Any

import numpy as np
from sqlalchemy import select, text, update

from .database import (
    ResearchPortfolioSnapshot,
    ResearchPortfolioTimeline,
    ResearchRun,
    get_engine,
)
from .research import Candidate, MarketPanel, load_market, simulate, targets

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="portfolio-timeline")
_pending: dict[str, Future] = {}
_lock = Lock()


def ranked_candidates(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Rank the already evaluated candidates, including the stored ensemble."""
    selection = result["selection"]
    rows = [
        {"id": row["id"], "name": _candidate_name(row["parameters"]),
         "score": row["score"], "members": [row["parameters"]]}
        for row in selection["leaderboard"]
    ]
    if "ensemble_score" in selection:
        rows.append({
            "id": "momentum-ensemble", "name": "Momentum ensemble",
            "score": selection["ensemble_score"],
            "members": [row["parameters"] for row in selection["leaderboard"][:3]],
        })
    # Preserve the stored single-rule ordering on equal scores. The original
    # selection also favors the single rule when the ensemble ties its score.
    rows.sort(key=lambda row: -row["score"])
    return [dict(row, rank=rank, selected=row["id"] == selection["selected_id"])
            for rank, row in enumerate(rows[:3], start=1)]


def _candidate_name(parameters: dict[str, Any]) -> str:
    signal = {
        "6m": "6-month momentum", "12m": "12-month momentum", "blend": "Blended momentum",
        "benchmark": "Liquid equal weight", "classic": "Classic trend",
        "low_volatility": "Low volatility", "reversal": "Reversal",
    }.get(parameters["signal"], parameters["signal"])
    return f"{signal} · {parameters['holdings']} holdings"


def replay_top_portfolios(
    panel: MarketPanel, start: int, result: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Reconstruct held positions from the exact saved input snapshot.

    No training, scoring, or validation-based ranking occurs here. The optional
    simulation observer leaves the execution/accounting path unchanged.
    """
    if panel.fingerprint() != result["data_fingerprint"]:
        raise ValueError("Stored prices changed since this experiment. Its portfolio history cannot be reconstructed from a different snapshot.")
    dates = panel.close.index[start - 1:]
    if (dates[1].date().isoformat() != result["split"]["training_start"]
            or dates[-1].date().isoformat() != result["split"]["validation_end"]):
        raise ValueError("Portfolio dates do not match the saved research window")
    capital = result["initial_cash"]
    candidates = ranked_candidates(result)
    rows = [{"date": timestamp.date(), "portfolios": []} for timestamp in dates]
    for candidate in candidates:
        members = [Candidate(**parameters) for parameters in candidate["members"]]
        desired = sum(targets(panel, member) for member in members) / len(members)
        history = [{"date": dates[0].date().isoformat(), "value": 1.0, "cash": 1.0,
                    "traded": False, "turnover": 0.0, "cost": 0.0, "holdings": []}]
        sim = simulate(panel, desired, start=start, cost=result["transaction_cost"],
                       rebalance=members[0].rebalance if len(members) == 1 else 1,
                       snapshot=history.append)
        # Reconcile the replay to the original training performance; this
        # catches an accidental execution change without fitting anything.
        train_count = result["split"]["training_periods"]
        original = next((row for row in result["selection"]["leaderboard"]
                         if row["id"] == candidate["id"]), None)
        if original is not None and not np.isclose(
            (1 + sim.returns.iloc[:train_count]).prod() - 1,
            original["training"]["total_return"], rtol=1e-10, atol=1e-10,
        ):
            raise ValueError("Portfolio replay differs from the saved training result")
        last_rebalance = None
        for offset, (row, point) in enumerate(zip(rows, history, strict=True)):
            if point["traded"]:
                last_rebalance = point["date"]
            holdings = [dict(holding, value=holding["value"] * capital)
                        for holding in point["holdings"]]
            holdings.sort(key=lambda holding: (-holding["weight"], holding["symbol"]))
            panel_index = start - 1 + offset
            decision_index = panel_index - 1 if panel_index >= start else None
            decision = _decision_explanation(
                candidate["members"], desired, panel, decision_index
            )
            row["portfolios"].append({
                "id": candidate["id"], "value": point["value"] * capital,
                "total_return": point["value"] - 1,
                "cash": point["cash"] * capital,
                "cash_weight": point["cash"] / point["value"] if point["value"] > 0 else 0.0,
                "traded": point["traded"], "turnover": point["turnover"],
                "cost": point["cost"] * capital, "last_rebalance": last_rebalance,
                "holdings": holdings,
                **decision,
            })
    metadata = {
        "currency": result["currency"], "market": result["market"],
        "initial_cash": capital, "frequency": "weekly",
        "ranking": "Frozen training score, including the ensemble",
        "validation_start": result["split"]["validation_start"],
        "dates": [timestamp.date().isoformat() for timestamp in dates],
        "candidates": candidates,
    }
    json.dumps(metadata, allow_nan=False)
    json.dumps([row["portfolios"] for row in rows], allow_nan=False)
    return metadata, rows


def _decision_explanation(
    members: list[dict[str, Any]], desired, panel: MarketPanel, decision_index: int | None
) -> dict[str, Any]:
    """Describe the information used for a historical target, never today's ratios."""

    parameters = members[0] if members else {}
    signal = str(parameters.get("signal", "unknown"))
    lookbacks = {
        "6m": [26], "12m": [52], "blend": [13, 26, 52],
        "low_volatility": [26], "reversal": [4], "benchmark": [], "classic": [10, 40],
    }.get(signal, [])
    if decision_index is None:
        return {
            "strategy_family": "price_only",
            "decision_date": None,
            "information_cutoff": None,
            "execution_date": panel.close.index[0].date().isoformat(),
            "selection_explanation": "No decision was executed before the first recorded portfolio date.",
            "decision_inputs": {
                "fundamentals_used": False,
                "price_source": "stored adjusted close and historical liquidity",
                "lookback_periods": lookbacks,
                "target_holdings": [],
            },
        }
    decision_date = panel.close.index[decision_index].date().isoformat()
    target = desired.iloc[decision_index]
    target_holdings = [
        {"symbol": str(symbol), "target_weight": float(weight)}
        for symbol, weight in target.items() if float(weight) > 1e-8
    ]
    return {
        "strategy_family": "price_only",
        "decision_date": decision_date,
        "information_cutoff": decision_date,
        "execution_date": panel.close.index[decision_index + 1].date().isoformat(),
        "selection_explanation": (
            f"{signal} price signal; target selected from observations available through "
            f"{decision_date}. Fundamentals and later ratios were not used."
        ),
        "decision_inputs": {
            "fundamentals_used": False,
            "price_source": "stored adjusted close and historical liquidity",
            "lookback_periods": lookbacks,
            "target_holdings": target_holdings,
        },
    }


def timeline_status(database_url: str | None, run_id: str) -> dict[str, Any]:
    with get_engine(database_url).connect() as connection:
        row = connection.execute(select(ResearchPortfolioTimeline.__table__).where(
            ResearchPortfolioTimeline.run_id == run_id,
        )).mappings().first()
    if row is None:
        return {"run_id": run_id, "status": "not_started"}
    return {"run_id": run_id, "status": row["status"],
            "error": row["error"], "timeline": row["metadata_json"]}


def portfolio_snapshot(database_url: str | None, run_id: str, on_date: date) -> dict[str, Any] | None:
    with get_engine(database_url).connect() as connection:
        portfolios = connection.execute(select(ResearchPortfolioSnapshot.portfolios).where(
            ResearchPortfolioSnapshot.run_id == run_id,
            ResearchPortfolioSnapshot.date == on_date,
        )).scalar_one_or_none()
    return {"run_id": run_id, "date": on_date.isoformat(), "portfolios": portfolios} if portfolios is not None else None


def build_timeline(database_url: str | None, run_id: str) -> dict[str, Any]:
    engine = get_engine(database_url)
    with engine.connect() as lease:
        lock_key = int.from_bytes(hashlib.sha256(f"timeline:{run_id}".encode()).digest()[:8], "big", signed=True)
        if engine.dialect.name == "postgresql":
            acquired = lease.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}).scalar()
            lease.commit()
            if not acquired:
                return timeline_status(database_url, run_id)
        try:
            if timeline_status(database_url, run_id)["status"] == "ready":
                return timeline_status(database_url, run_id)
            with engine.begin() as connection:
                run = connection.execute(select(ResearchRun.__table__).where(ResearchRun.id == run_id)).mappings().one_or_none()
                if run is None or run["status"] != "complete":
                    raise ValueError("A completed research run is required")
                exists = connection.execute(select(ResearchPortfolioTimeline.run_id).where(
                    ResearchPortfolioTimeline.run_id == run_id,
                )).scalar_one_or_none()
                if exists is None:
                    connection.execute(ResearchPortfolioTimeline.__table__.insert().values(run_id=run_id, status="building"))
                else:
                    connection.execute(update(ResearchPortfolioTimeline).where(
                        ResearchPortfolioTimeline.run_id == run_id,
                    ).values(status="building", error=None))
            panel, start = load_market(database_url, run["market"], run["parameters"]["years"])
            metadata, rows = replay_top_portfolios(panel, start, run["result"])
            # Atomic publication: readers never see partially prepared dates.
            with engine.begin() as connection:
                for offset in range(0, len(rows), 64):
                    connection.execute(ResearchPortfolioSnapshot.__table__.insert(),
                                       [dict(row, run_id=run_id) for row in rows[offset:offset + 64]])
                connection.execute(update(ResearchPortfolioTimeline).where(
                    ResearchPortfolioTimeline.run_id == run_id,
                ).values(status="ready", metadata_json=metadata, error=None))
            return timeline_status(database_url, run_id)
        except Exception as exc:
            with engine.begin() as connection:
                connection.execute(update(ResearchPortfolioTimeline).where(
                    ResearchPortfolioTimeline.run_id == run_id,
                ).values(status="failed", error=str(exc)))
            raise
        finally:
            if engine.dialect.name == "postgresql":
                lease.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
                lease.commit()


def submit_timeline(database_url: str | None, run_id: str) -> dict[str, Any]:
    with _lock:
        status = timeline_status(database_url, run_id)
        if status["status"] == "ready":
            return status
        pending = _pending.get(run_id)
        if pending is None or pending.done():
            if status["status"] == "failed":
                with get_engine(database_url).begin() as connection:
                    connection.execute(update(ResearchPortfolioTimeline).where(
                        ResearchPortfolioTimeline.run_id == run_id,
                    ).values(status="building", error=None))
            _pending[run_id] = _executor.submit(build_timeline, database_url, run_id)
        return {"run_id": run_id, "status": "building"}
