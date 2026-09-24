import copy

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import func, select

from cheshire_cat import portfolio_timeline, research
from cheshire_cat.database import (
    ResearchPortfolioSnapshot,
    ResearchRun,
    create_schema,
    get_engine,
)


@pytest.fixture
def experiment(monkeypatch):
    rng = np.random.default_rng(58)
    dates = pd.date_range("2000-01-07", periods=400, freq="W-FRI")
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0.003, 0.025, (400, 12)), axis=0)),
                         index=dates, columns=[f"S{i:02}" for i in range(12)])
    panel = research.MarketPanel(close, close * 1_000_000, {"currency": "USD", "market": "NASDAQ"})
    monkeypatch.setattr(research, "candidate_catalog", lambda: (
        research.Candidate(holdings=10), research.Candidate("6m", 10, False),
        research.Candidate("benchmark", 500, False),
    ))
    return panel, research.run_research(panel, 80)


def test_observer_records_executed_holdings_and_drift_without_changing_accounting():
    prices = pd.DataFrame({"A": [100, 100, 200, 200, 200], "B": [100] * 5},
                          index=pd.date_range("2020-01-03", periods=5, freq="W-FRI"))
    panel = research.MarketPanel(prices, prices * 100_000, {})
    desired = prices * 0 + 0.5
    history = []
    observed = research.simulate(panel, desired, start=1, cost=0.001, rebalance=13,
                                 snapshot=history.append)
    plain = research.simulate(panel, desired, start=1, cost=0.001, rebalance=13)
    pd.testing.assert_series_equal(observed.returns, plain.returns)
    assert history[0]["date"] == "2020-01-10"
    assert history[0]["traded"] is True
    assert history[0]["cost"] > 0
    assert history[1]["traded"] is False
    assert history[1]["holdings"][0]["weight"] == pytest.approx(2 / 3)
    for point, equity in zip(history, (1 + observed.returns).cumprod(), strict=True):
        assert point["value"] == pytest.approx(equity)
        assert point["cash"] + sum(row["value"] for row in point["holdings"]) == pytest.approx(equity)


def test_top_three_include_ensemble_and_ignore_validation(experiment):
    _, result = experiment
    altered = copy.deepcopy(result)
    singles = altered["selection"]["leaderboard"]
    for score, row in enumerate(singles):
        row["score"] = 3 - score
    altered["selection"]["ensemble_score"] = 2.5
    best = portfolio_timeline.ranked_candidates(altered)
    assert [row["id"] for row in best] == [singles[0]["id"], "momentum-ensemble", singles[1]["id"]]
    for strategy in altered["strategies"]:
        strategy["validation"]["total_return"] = 1e12
    assert best == portfolio_timeline.ranked_candidates(altered)
    altered["selection"]["ensemble_score"] = 3
    assert portfolio_timeline.ranked_candidates(altered)[0]["id"] == singles[0]["id"]


def test_each_week_reconciles_and_replay_never_retrains(experiment, monkeypatch):
    panel, result = experiment
    original = copy.deepcopy(result)
    monkeypatch.setattr(research, "select_strategy", lambda *_: pytest.fail("must not train"))
    metadata, rows = portfolio_timeline.replay_top_portfolios(panel, 80, result)
    assert len(metadata["dates"]) == len(rows) == 321
    assert len(metadata["candidates"]) == 3
    for row in rows:
        assert len(row["portfolios"]) == 3
        for portfolio in row["portfolios"]:
            assert portfolio["cash"] + sum(h["value"] for h in portfolio["holdings"]) == pytest.approx(portfolio["value"])
            assert portfolio["cash_weight"] + sum(h["weight"] for h in portfolio["holdings"]) == pytest.approx(1)
            assert portfolio["value"] / result["initial_cash"] - 1 == pytest.approx(portfolio["total_return"])
    assert all(p["holdings"] == [] and p["cash_weight"] == 1 for p in rows[0]["portfolios"])
    first_decision = rows[1]["portfolios"][0]
    assert first_decision["strategy_family"] == "price_only"
    assert first_decision["information_cutoff"] == "2001-07-13"
    assert first_decision["decision_inputs"]["fundamentals_used"] is False
    assert "available through" in first_decision["selection_explanation"]
    assert result == original
    panel.close.iloc[-1, 0] *= 1.1
    with pytest.raises(ValueError, match="prices changed"):
        portfolio_timeline.replay_top_portfolios(panel, 80, result)


def test_saved_timeline_is_indexed_by_date_and_reused_after_restart(experiment, tmp_path, monkeypatch):
    panel, result = experiment
    url = f"sqlite:///{tmp_path / 'timeline.sqlite'}"
    create_schema(url)
    with get_engine(url).begin() as connection:
        connection.execute(ResearchRun.__table__.insert().values(
            id="run-1", market="NASDAQ", status="complete", version=research.RESEARCH_VERSION,
            progress="Complete", parameters={"years": 20}, selection=result["selection"], result=result,
        ))
    monkeypatch.setattr(portfolio_timeline, "load_market", lambda *_: (panel, 80))
    status = portfolio_timeline.build_timeline(url, "run-1")
    assert status["status"] == "ready"
    latest = portfolio_timeline.portfolio_snapshot(url, "run-1", panel.close.index[-1].date())
    assert len(latest["portfolios"]) == 3
    assert portfolio_timeline.portfolio_snapshot(url, "run-1", pd.Timestamp("1900-01-01").date()) is None
    monkeypatch.setattr(portfolio_timeline, "load_market", lambda *_: pytest.fail("replayed a saved timeline"))
    assert portfolio_timeline.build_timeline(url, "run-1") == status
    with get_engine(url).connect() as connection:
        assert connection.execute(select(func.count()).select_from(ResearchPortfolioSnapshot)).scalar_one() == 321
        assert connection.execute(select(ResearchRun.result)).scalar_one() == result
