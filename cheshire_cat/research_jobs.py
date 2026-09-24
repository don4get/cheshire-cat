"""Persist research results so the dashboard never reruns tuning on page load."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update

from .database import ResearchRun, get_engine
from .research import RESEARCH_VERSION, evaluate_selection, load_market, run_research

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="portfolio-research")
_lock = Lock()


def latest_run(database_url: str | None, market: str, run_id: str | None = None) -> dict[str, Any] | None:
    statement = select(ResearchRun.__table__).where(ResearchRun.market == market)
    if run_id:
        statement = statement.where(ResearchRun.id == run_id)
    with get_engine(database_url).connect() as connection:
        row = connection.execute(statement.order_by(ResearchRun.created_at.desc()).limit(1)).mappings().first()
    if row is None:
        return None
    result = dict(row)
    for key in ("created_at", "updated_at"):
        result[key] = result[key].isoformat()
    # The selection is already included in a completed result. Avoid sending it twice.
    result.pop("selection", None)
    return result


def create_run(database_url: str | None, market: str, years: int, initial_cash: float, cost: float) -> str:
    run_id = str(uuid4())
    with get_engine(database_url).begin() as connection:
        connection.execute(ResearchRun.__table__.insert().values(
            id=run_id, market=market, version=RESEARCH_VERSION, status="queued",
            progress="Waiting to load stored market history",
            parameters={"years": years, "initial_cash": initial_cash, "cost": cost},
        ))
    return run_id


def _update(database_url: str | None, run_id: str, **values: Any) -> None:
    with get_engine(database_url).begin() as connection:
        connection.execute(update(ResearchRun).where(ResearchRun.id == run_id).values(
            **values, updated_at=datetime.now(UTC).replace(tzinfo=None),
        ))


def execute_run(database_url: str | None, run_id: str) -> dict[str, Any]:
    # A per-run PostgreSQL advisory lock survives all progress commits and is
    # released automatically if the process exits. Resume cannot duplicate a
    # still-running experiment, including a CLI worker in another process.
    from sqlalchemy import text

    engine = get_engine(database_url)
    with engine.connect() as lease:
        if engine.dialect.name == "postgresql":
            from hashlib import sha256

            lock_key = int.from_bytes(sha256(run_id.encode()).digest()[:8], "big", signed=True)
            acquired = lease.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}).scalar()
            lease.commit()
            if not acquired:
                raise RuntimeError("This research run is already executing in another worker")
        try:
            return _execute_locked(database_url, run_id)
        finally:
            if engine.dialect.name == "postgresql":
                lease.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
                lease.commit()


def _execute_locked(database_url: str | None, run_id: str) -> dict[str, Any]:
    with get_engine(database_url).connect() as connection:
        row = dict(connection.execute(select(ResearchRun.__table__).where(ResearchRun.id == run_id)).mappings().one())
    if row["status"] == "complete":
        return row["result"]
    try:
        _update(database_url, run_id, status="running", progress="Loading stored history")
        parameters = row["parameters"]
        panel, start = load_market(database_url, row["market"], parameters["years"])
        if row["selection"]:
            # A restart resumes the frozen rule, never silently trains a new one.
            _update(database_url, run_id, progress="Resuming the frozen selection")
            split = start + int((len(panel.close) - start) * 0.8)
            result = evaluate_selection(panel, start, split, row["selection"],
                                        initial_cash=parameters["initial_cash"], cost=parameters["cost"])
        else:
            result = run_research(
                panel, start, initial_cash=parameters["initial_cash"], cost=parameters["cost"],
                progress=lambda message: _update(database_url, run_id, progress=message),
                freeze=lambda selection: _update(database_url, run_id, selection=selection,
                                                  progress="Selection frozen; opening holdout"),
            )
        _update(database_url, run_id, status="complete", progress="Training and validation complete", result=result, error=None)
        return result
    except Exception as exc:
        _update(database_url, run_id, status="failed", progress="Research stopped", error=str(exc))
        raise


def submit_run(database_url: str | None, market: str, years: int = 20,
               initial_cash: float = 100_000, cost: float = 0.001) -> str:
    """Idempotent launch: the same configured research is reused, not retuned."""
    with _lock:
        latest = latest_run(database_url, market)
        parameters = {"years": years, "initial_cash": initial_cash, "cost": cost}
        if (latest and latest["version"] == RESEARCH_VERSION
                and latest["parameters"] == parameters):
            if latest["status"] != "complete":
                # The database lease is the authority on whether another
                # process is live. Queued, interrupted and failed runs reuse
                # their original frozen selection instead of tuning again.
                _executor.submit(execute_run, database_url, latest["id"])
            return latest["id"]
        run_id = create_run(database_url, market, years, initial_cash, cost)
        _executor.submit(execute_run, database_url, run_id)
        return run_id
