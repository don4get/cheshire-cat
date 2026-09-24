from concurrent.futures import Future
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
from sqlalchemy import select
from test_research import panel

from cheshire_cat import challenger, challenger_jobs, research
from cheshire_cat.challenger import BATCH1_VERSION, CHALLENGER_VERSION, AtlasRule
from cheshire_cat.database import ResearchChallenger, ResearchRun, create_schema, get_engine


def test_freeze_failure_resume_cached_rankings_and_original_immutability(tmp_path, monkeypatch):
    data = panel(450, 14)
    monkeypatch.setattr(research, "candidate_catalog", lambda: (
        research.Candidate("6m", 10, False), research.Candidate("12m", 10, True),
        research.Candidate("benchmark", 500, False),
    ))
    result = research.run_research(data, 56)
    original = deepcopy(result)
    url = f"sqlite:///{tmp_path / 'challengers.sqlite'}"
    create_schema(url)
    with get_engine(url).begin() as connection:
        connection.execute(ResearchRun.__table__.insert().values(
            id="incumbent", market="NASDAQ", version=research.RESEARCH_VERSION,
            status="complete", progress="Complete", parameters={"years": 20, "cost": .001, "initial_cash": 100000},
            selection=result["selection"], result=result,
        ))
    monkeypatch.setattr(challenger_jobs, "load_market", lambda *_: (data, 56))
    monkeypatch.setattr(challenger, "atlas_catalog", lambda version: (
        (AtlasRule("continuous", 10), AtlasRule("near_high", 10)) if version == BATCH1_VERSION else
        (AtlasRule("12m", 10, False, 4, "bounded", "equal"), AtlasRule("6m", 10, False, 13, "bounded", "equal"))
    ))
    evaluate = challenger_jobs.evaluate_atlas

    def fail_after_freeze(*args, **kwargs):
        with get_engine(url).connect() as connection:
            batches = connection.execute(select(ResearchChallenger.__table__)).mappings().all()
        assert len(batches) == 3
        assert all(row["selection"] is not None and len(row["trials"]) == 2 for row in batches)
        raise RuntimeError("interrupted after selection freeze")

    monkeypatch.setattr(challenger_jobs, "evaluate_atlas", fail_after_freeze)
    with pytest.raises(RuntimeError, match="after selection freeze"):
        challenger_jobs.build_challenger(url, "incumbent")
    assert challenger_jobs.challenger_status(url, "incumbent")["status"] == "failed"
    monkeypatch.setattr(challenger_jobs, "train_atlas", lambda *args, **kwargs: pytest.fail("Frozen batches must not retrain"))
    monkeypatch.setattr(challenger_jobs, "evaluate_atlas", lambda *args, **kwargs: evaluate(*args, **kwargs, replicates=20))
    saved = challenger_jobs.build_challenger(url, "incumbent")
    assert saved["status"] == "ready"
    report = saved["report"]
    assert report["version"] == CHALLENGER_VERSION
    assert len(report["trials"]) == 6
    assert len(report["leaderboard"]) == 10
    assert len(report["stresses"]) == 6
    assert len(report["walk_forward"]) == 2
    chosen = report["strategies"][0]
    for period, rank in report["performance_ranks"].items():
        expected = 1 + sum(row[period]["total_return"] > chosen[period]["total_return"] for row in original["strategies"])
        assert rank == expected
    assert report["strategies"][1:] == original["strategies"]
    assert np.isclose(chosen["curve"][-1]["value"], chosen["full"]["final_value"])
    assert np.isclose(sum(row["weight"] for row in report["holdings"]) + report["cash_weight"], 1)
    assert report["selection"]["winner"]["score"] == max(row["score"] for row in report["trials"])
    with get_engine(url).connect() as connection:
        retained = connection.execute(select(ResearchRun.__table__)).mappings().one()
    assert retained["result"] == original
    assert retained["selection"] == original["selection"]
    monkeypatch.setattr(challenger_jobs, "load_market", lambda *_: pytest.fail("Ready result must be cached"))
    assert challenger_jobs.build_challenger(url, "incumbent") == saved


def test_atlas_rejects_invalid_rules_and_weights():
    for kwargs in ({"holdings": 0}, {"rebalance": 0}, {"signal": "future_returns"}, {"construction": "levered"}):
        with pytest.raises(ValueError):
            AtlasRule(**kwargs)
    for raw, cap in ((np.array([np.nan]), .1), (np.array([-1.]), .1), (np.ones(2), 0)):
        with pytest.raises(ValueError):
            challenger.bounded_allocation(raw, cap)


def test_submit_publishes_queue_before_worker_starts(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'queued.sqlite'}"
    create_schema(url)
    monkeypatch.setattr(challenger_jobs._executor, "submit", lambda *args, **kwargs: Future())
    submitted = challenger_jobs.submit_challenger(url, "queued-incumbent")
    assert submitted["status"] == "evaluating"
    assert challenger_jobs.challenger_status(url, "queued-incumbent")["status"] == "queued"


def test_earlier_walk_forward_ensemble_members_do_not_use_later_training(monkeypatch):
    monkeypatch.setattr(research, "candidate_catalog", lambda: (
        research.Candidate("12m", 10, True), research.Candidate("benchmark", 500, False),
    ))
    rules = (AtlasRule("12m", 10, False, 4, "bounded", "equal"),
             AtlasRule("6m", 20, False, 13, "bounded", "equal"),
             AtlasRule("continuous", 10, False, 4, "bounded", "equal"))

    def audited(data):
        original = research.run_research(data, 56)
        stop = 56 + original["split"]["training_periods"]
        training = data.through(stop)
        trials = challenger.train_atlas(training, 56, rules=rules)
        trials += challenger.train_atlas(training, 56, rules=challenger.ensemble_catalog(trials))
        selection = {"winner": max(trials, key=lambda row: row["score"]),
                     "training_fingerprint": training.fingerprint(), "data_fingerprint": data.fingerprint()}
        return challenger_jobs.evaluate_atlas(data, 56, original, selection, trials, replicates=10)

    data = panel(450, 20)
    first = audited(data)
    changed = replace(data, close=data.close.copy())
    changed.close.iloc[350:, :10] *= 100
    second = audited(changed)
    # The final training fit includes the modified data; the first outer
    # selection ends at week 315 and must not import its fitted members.
    for before, after in zip(first["walk_forward"], second["walk_forward"], strict=True):
        assert before["folds"][0]["selected_id"] == after["folds"][0]["selected_id"]
        assert before["folds"][0]["members"] == after["folds"][0]["members"]
