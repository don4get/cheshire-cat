"""Durable, independently versioned robustness audits with cross-process leases."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any

from sqlalchemy import select, text, update

from .database import ResearchRun, ResearchValidationAudit, get_engine
from .research import load_market
from .validation import AUDIT_VERSION, audit_research

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research-audit")
_pending: dict[tuple[str | None, str], Future] = {}
_lock = Lock()


def _where(run_id: str):
    return (ResearchValidationAudit.run_id == run_id, ResearchValidationAudit.version == AUDIT_VERSION)


def audit_status(database_url: str | None, run_id: str) -> dict[str, Any]:
    with get_engine(database_url).connect() as connection:
        row = connection.execute(select(ResearchValidationAudit.__table__).where(*_where(run_id))).mappings().first()
    return ({"run_id": run_id, "version": AUDIT_VERSION, "status": "not_started", "progress": "Audit not yet run"}
            if row is None else {key: row[key] for key in ("run_id", "version", "status", "progress", "report", "error")})


def build_audit(database_url: str | None, run_id: str, *,
                progress: Callable[[str], None] = lambda _: None) -> dict[str, Any]:
    engine = get_engine(database_url)
    with engine.connect() as lease:
        lock_key = int.from_bytes(hashlib.sha256(f"audit:{run_id}:{AUDIT_VERSION}".encode()).digest()[:8], "big", signed=True)
        if engine.dialect.name == "postgresql":
            acquired = lease.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}).scalar()
            lease.commit()
            if not acquired:
                return audit_status(database_url, run_id)
        try:
            saved = audit_status(database_url, run_id)
            if saved["status"] == "ready":
                return saved
            with engine.begin() as connection:
                run = connection.execute(select(ResearchRun.__table__).where(ResearchRun.id == run_id)).mappings().one_or_none()
                if run is None or run["status"] != "complete":
                    raise ValueError("A completed research run is required")
                if saved["status"] == "not_started":
                    connection.execute(ResearchValidationAudit.__table__.insert().values(
                        run_id=run_id, version=AUDIT_VERSION, status="building", progress="Loading stored weekly history",
                    ))
                else:
                    connection.execute(update(ResearchValidationAudit).where(*_where(run_id)).values(
                        status="building", progress="Resuming audit from saved experiment", error=None,
                    ))

            def on_progress(message: str) -> None:
                with engine.begin() as connection:
                    connection.execute(update(ResearchValidationAudit).where(*_where(run_id)).values(progress=message))
                progress(message)

            panel, start = load_market(database_url, run["market"], run["parameters"]["years"])
            report = audit_research(panel, start, run["result"], progress=on_progress)
            with engine.begin() as connection:
                connection.execute(update(ResearchValidationAudit).where(*_where(run_id)).values(
                    status="ready", report=report, progress="Audit complete · original selection unchanged", error=None,
                ))
            return audit_status(database_url, run_id)
        except Exception as exc:
            with engine.begin() as connection:
                connection.execute(update(ResearchValidationAudit).where(*_where(run_id)).values(status="failed", error=str(exc)))
            raise
        finally:
            if engine.dialect.name == "postgresql":
                lease.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
                lease.commit()


def submit_audit(database_url: str | None, run_id: str) -> dict[str, Any]:
    with _lock:
        status = audit_status(database_url, run_id)
        if status["status"] == "ready":
            return status
        key = (database_url, run_id)
        pending = _pending.get(key)
        if pending is None or pending.done():
            _pending[key] = _executor.submit(build_audit, database_url, run_id)
        return {"run_id": run_id, "version": AUDIT_VERSION, "status": "building", "progress": "Audit queued"}
