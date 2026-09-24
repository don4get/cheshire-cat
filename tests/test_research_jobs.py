import pytest
from sqlalchemy import select

from cheshire_cat import research_jobs
from cheshire_cat.database import ResearchRun, create_schema, get_engine


def test_frozen_selection_survives_failure_and_resume_without_retraining(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'research.sqlite'}"
    create_schema(url)
    run_id = research_jobs.create_run(url, "NASDAQ", 20, 100_000, 0.001)
    frozen = {"members": [{"signal": "12m"}], "training_fingerprint": "test-snapshot"}

    class Panel:
        close = range(400)

    monkeypatch.setattr(research_jobs, "load_market", lambda *_: (Panel(), 1))

    def fail_after_freeze(*args, **kwargs):
        kwargs["freeze"](frozen)
        raise RuntimeError("interrupted during evaluation")

    monkeypatch.setattr(research_jobs, "run_research", fail_after_freeze)
    with pytest.raises(RuntimeError, match="interrupted"):
        research_jobs.execute_run(url, run_id)
    with get_engine(url).connect() as connection:
        row = connection.execute(select(ResearchRun.__table__)).mappings().one()
        assert row["selection"] == frozen
        assert row["status"] == "failed"

    expected = {"selection": frozen, "validation_verdict": "test only"}

    def resume(panel, start, split, selection, **kwargs):
        assert selection == frozen
        assert split == 320
        return expected

    monkeypatch.setattr(research_jobs, "evaluate_selection", resume)
    assert research_jobs.execute_run(url, run_id) == expected
    assert research_jobs.latest_run(url, "NASDAQ")["status"] == "complete"
    # Reopening a completed result never runs either training or evaluation.
    monkeypatch.setattr(research_jobs, "load_market", lambda *_: pytest.fail("reran a complete experiment"))
    assert research_jobs.execute_run(url, run_id) == expected
