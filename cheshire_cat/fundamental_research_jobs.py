"""Persistence helpers for matched fundamental experiments."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from .database import FundamentalResearchRun, create_schema, get_engine
from .fundamental_research import FUNDAMENTAL_RESEARCH_VERSION


def create_run(
    database_url: str | None,
    market: str,
    manifest: dict[str, Any],
) -> str:
    create_schema(database_url)
    run_id = str(uuid.uuid4())
    with Session(get_engine(database_url)) as session:
        session.add(
            FundamentalResearchRun(
                id=run_id,
                market=market,
                version=FUNDAMENTAL_RESEARCH_VERSION,
                status="queued",
                manifest=manifest,
            )
        )
        session.commit()
    return run_id


def save_result(
    database_url: str | None,
    run_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    create_schema(database_url)
    with Session(get_engine(database_url)) as session:
        run = session.get(FundamentalResearchRun, run_id)
        if run is None:
            raise ValueError(f"Unknown fundamental research run {run_id}")
        run.status = "complete"
        run.result = result
        run.error = None
        session.commit()
        return _as_dict(run)


def fail_run(database_url: str | None, run_id: str, error: str) -> dict[str, Any]:
    create_schema(database_url)
    with Session(get_engine(database_url)) as session:
        run = session.get(FundamentalResearchRun, run_id)
        if run is None:
            raise ValueError(f"Unknown fundamental research run {run_id}")
        run.status = "error"
        run.error = error
        session.commit()
        return _as_dict(run)


def get_run(database_url: str | None, run_id: str) -> dict[str, Any] | None:
    create_schema(database_url)
    with Session(get_engine(database_url)) as session:
        run = session.get(FundamentalResearchRun, run_id)
        return _as_dict(run) if run else None


def _as_dict(run: FundamentalResearchRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "market": run.market,
        "version": run.version,
        "status": run.status,
        "manifest": run.manifest,
        "result": run.result,
        "error": run.error,
    }
