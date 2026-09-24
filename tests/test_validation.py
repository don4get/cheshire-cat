from copy import deepcopy
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from test_research import panel

from cheshire_cat import research, validation, validation_jobs
from cheshire_cat.database import ResearchRun, create_schema, get_engine
from cheshire_cat.research import Candidate, simulate
from cheshire_cat.validation import (
    audit_research,
    family_test,
    rank_past,
    relative_interval,
    temporal_folds,
)


def test_temporal_gap_rolling_boundaries_and_partial_fold():
    for rolling in (False, True):
        folds = temporal_folds(56, 1100, rolling=rolling)
        assert folds[0]["train_stop"] - folds[0]["train_start"] == 260
        assert folds[0]["test_start"] == 320
        for i, fold in enumerate(folds):
            assert fold["test_start"] - fold["train_stop"] == 4
            assert fold["test_stop"] - fold["test_start"] <= 52
            if rolling:
                assert fold["train_stop"] - fold["train_start"] == 260
            if i:
                assert folds[i - 1]["test_stop"] == fold["test_start"]
        assert folds[-1]["test_stop"] == 1100
    assert temporal_folds(0, 270)[-1]["partial"]


def test_selection_scores_never_see_gap_or_future_returns():
    data = pd.DataFrame(np.random.default_rng(8).normal(0, .01, (400, 4)),
                        index=pd.date_range("2000-01-07", periods=400, freq="W-FRI"))
    before = rank_past(data, left=30, right=290)
    data.iloc[290:] = [100, -0.99, 42, -0.5]
    assert rank_past(data, left=30, right=290) == before


def test_actual_switching_costs_and_continuous_equity():
    data = panel(6, 2)
    data.close.iloc[:, :] = [[100, 100], [100, 100], [200, 100], [200, 100], [200, 200], [200, 200]]
    desired = data.close * 0
    desired.iloc[:2, 0] = 1
    desired.iloc[2:, 1] = 1
    schedule = pd.Series([False, True, False, True, False, False], index=data.close.index)
    sim = simulate(data, desired, start=1, cost=.01, trade_schedule=schedule)
    assert sim.costs.iloc[2] > sim.costs.iloc[0] * 3
    assert sim.turnover.iloc[2] == pytest.approx(2 / 1.01)
    # Initial purchase, doubling A, sell A/buy B, doubling B. No free reset.
    assert (1 + sim.returns).prod() == pytest.approx(4 * .99 / 1.01**2)
    assert sim.costs.iloc[[1, 3, 4]].eq(0).all()


def test_extra_delay_and_training_only_attribution():
    data = panel(8, 2)
    desired = data.close * 0
    desired.iloc[:, 0] = 1
    original = simulate(data, desired, start=1, cost=0, execution_delay=2, attribution_end=4)
    assert original.exposure.iloc[0] == 0  # No negative-index future target.
    assert original.exposure.iloc[1] == 1
    changed = replace(data, close=data.close.copy())
    changed.close.iloc[4:, 1] *= 1000
    later = simulate(changed, desired, start=1, cost=0, execution_delay=2, attribution_end=4)
    pd.testing.assert_series_equal(original.attribution, later.attribution)


def test_joint_bootstrap_preserves_dependence_and_null():
    dates = pd.date_range("2000-01-07", periods=100, freq="W-FRI")
    zero = pd.Series(0., index=dates)
    returns = pd.Series(np.random.default_rng(4).normal(.001, .02, 100), index=dates)
    one = family_test(pd.DataFrame({"A": returns}), zero, replicates=200)
    duplicate = family_test(pd.DataFrame({"A": returns, "B": returns}), zero, replicates=200)
    assert one["p_value"] == duplicate["p_value"]
    assert family_test(pd.DataFrame({"A": zero}), zero, replicates=200)["p_value"] == 1
    interval = relative_interval(returns, returns, block=13, replicates=50)
    assert interval["lower"] == interval["upper"] == interval["estimate"] == 0
    assert interval == relative_interval(returns, returns, block=13, replicates=50)
    with pytest.raises(ValueError):
        relative_interval(returns.iloc[:2], zero.iloc[:2], block=13)


@pytest.fixture
def experiment(monkeypatch):
    data = panel(450)
    monkeypatch.setattr(research, "candidate_catalog", lambda: (
        Candidate("6m", 10, False), Candidate("12m", 10, True), Candidate("blend", 10, True),
        Candidate("benchmark", 500, False),
    ))
    result = research.run_research(data, 56)
    return data, result


def test_full_audit_preserves_result_and_reconciles(experiment):
    data, result = experiment
    before = deepcopy(result)
    report = audit_research(data, 56, result, replicates=30)
    assert result == before
    assert len(report["finalists"]) == 3
    assert len(report["walk_forward"]) == 2
    for candidate in report["finalists"]:
        assert len(candidate["stresses"]) == 6
        assert len(candidate["intervals"]) == 3
    for protocol in report["walk_forward"]:
        assert protocol["fees"] > 0
        assert protocol["curve"][-1]["value"] == pytest.approx(protocol["metrics"]["final_value"])
        assert np.prod([1 + fold["total_return"] for fold in protocol["folds"]]) - 1 == pytest.approx(protocol["metrics"]["total_return"])
    selected = next(row for row in report["finalists"] if row["selected"])
    assert selected["stresses"][0]["metrics"]["total_return"] == pytest.approx(result["strategies"][0]["validation"]["total_return"])
    changed = replace(data, close=data.close * 2)
    with pytest.raises(ValueError, match="snapshot"):
        audit_research(changed, 56, result)


def test_fold_choices_do_not_change_with_future_prices(experiment):
    data, result = experiment
    original = audit_research(data, 56, result, replicates=10)
    # Original selection may change; earlier fold choices must not.
    changed = replace(data, close=data.close.copy())
    changed.close.iloc[380:, 0] *= 30
    later_result = research.run_research(changed, 56)
    later = audit_research(changed, 56, later_result, replicates=10)
    for a, b in zip(original["walk_forward"], later["walk_forward"], strict=True):
        for first, second in zip(a["folds"][:2], b["folds"][:2], strict=True):
            assert first["members"] == second["members"]
            assert first["selection_score"] == pytest.approx(second["selection_score"])


def test_persisted_audit_cache_and_original_run_immutable(tmp_path, monkeypatch, experiment):
    data, result = experiment
    url = f"sqlite:///{tmp_path / 'audit.db'}"
    create_schema(url)
    with get_engine(url).begin() as connection:
        connection.execute(ResearchRun.__table__.insert().values(
            id="frozen", market="NASDAQ", version="v1", status="complete", progress="Done",
            parameters={"years": 20}, selection=result["selection"], result=result,
        ))
    def interrupted(*_):
        raise RuntimeError("interrupted before replay")

    assert validation_jobs.audit_status(url, "frozen")["status"] == "not_started"
    monkeypatch.setattr(validation_jobs, "load_market", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        validation_jobs.build_audit(url, "frozen")
    assert validation_jobs.audit_status(url, "frozen")["status"] == "failed"
    monkeypatch.setattr(validation_jobs, "load_market", lambda *_: (data, 56))
    monkeypatch.setattr(validation_jobs, "audit_research", lambda *args, **kwargs: validation.audit_research(*args, **kwargs, replicates=10))
    saved = validation_jobs.build_audit(url, "frozen")
    assert saved["status"] == "ready"
    monkeypatch.setattr(validation_jobs, "load_market", lambda *_: pytest.fail("Cached audit must not replay"))
    assert validation_jobs.build_audit(url, "frozen") == saved
    with get_engine(url).connect() as connection:
        original = connection.execute(ResearchRun.__table__.select()).mappings().one()
    assert original["result"] == result
    assert original["selection"] == result["selection"]
