from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from cheshire_cat import research
from cheshire_cat.research import Candidate, MarketPanel, prepare_panel, simulate, targets


def panel(periods=400, symbols=12):
    rng = np.random.default_rng(24)
    dates = pd.date_range("2000-01-07", periods=periods, freq="W-FRI")
    close = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0.003, 0.025, (periods, symbols)), axis=0)),
        index=dates, columns=[f"S{i:02}" for i in range(symbols)],
    )
    return MarketPanel(close, close * 1_000_000, {})


def test_friday_alignment_invalid_prices_and_terminal_duplicates():
    prices = pd.DataFrame([
        {"date": "2020-01-05", "symbol": "PARIS", "adj_close": 10, "close": 11, "volume": 200},
        {"date": "2020-01-06", "symbol": "USA", "adj_close": 20, "close": 22, "volume": 100},
        {"date": "2020-01-10", "symbol": "USA", "adj_close": 20, "close": 22, "volume": 20},
        {"date": "2020-01-13", "symbol": "USA", "adj_close": 0, "close": 0, "volume": 50},
    ])
    prepared = prepare_panel(prices)
    assert prepared.close.loc["2020-01-10", "PARIS"] == 10
    assert prepared.close.loc["2020-01-10", "USA"] == 20
    assert prepared.liquidity.loc["2020-01-10", "USA"] == 2200
    assert pd.isna(prepared.close.loc["2020-01-17", "USA"])
    assert prepared.metadata["duplicate_week_rows"] == 1


def test_execution_delay_initial_fee_and_drift_rebalance():
    data = panel(6, 2)
    data.close.iloc[:, :] = [[100, 100], [100, 100], [200, 100], [200, 100], [200, 100], [200, 100]]
    target = data.close * 0
    target.iloc[2:, 0] = 1
    sim = simulate(data, target, start=1, cost=0.01, rebalance=1)
    # A signal at the doubled close cannot capture that doubling or the next bar.
    assert sim.returns.iloc[:2].eq(0).all()
    assert sim.returns.iloc[2] == pytest.approx(1 / 1.01 - 1)
    equal = data.close * 0 + 0.5
    sim = simulate(data, equal, start=1, cost=0.01, rebalance=1)
    assert sim.turnover.iloc[0] > 0.99
    # Constant targets still trade after one asset doubles.
    assert sim.turnover.iloc[1] > 0.3
    assert sim.costs.iloc[1] > 0
    assert sim.final_weights.sum() <= 1.0000001


def test_missing_quote_is_not_a_free_exit_or_backfilled_ipo():
    data = panel(8, 2)
    data.close.iloc[:, :] = 100
    data.close.iloc[2:6, 0] = np.nan
    data.close.iloc[:4, 1] = np.nan
    target = data.close * 0 + 0.5
    sim = simulate(data, target, start=1, cost=0, rebalance=1)
    assert sim.exposure.iloc[0] == 0.5
    assert sim.stale_losses == 1
    assert sim.returns.iloc[4] < 0


def test_future_prices_and_ipo_do_not_change_past_signals():
    data = panel()
    candidate = Candidate(holdings=10)
    original = targets(data, candidate)
    changed = replace(data, close=data.close.copy(), liquidity=data.liquidity.copy())
    changed.close.iloc[320:] *= 1000
    changed.close["FUTURE_IPO"] = np.nan
    changed.close.loc[changed.close.index[320]:, "FUTURE_IPO"] = 100
    changed.liquidity["FUTURE_IPO"] = 100_000_000
    later = targets(changed, candidate)
    pd.testing.assert_frame_equal(original.iloc[:320], later[original.columns].iloc[:320])
    assert original.max().max() <= 0.1
    assert original.sum(axis=1).max() <= 1.000001


def test_selection_cannot_access_validation_and_is_frozen_first(monkeypatch):
    data = panel()
    monkeypatch.setattr(research, "candidate_catalog", lambda: (
        Candidate(holdings=10), Candidate("6m", 10, False),
    ))
    events = []
    actual_select = research.select_strategy

    def checked_select(training, start, cost, progress):
        assert training.close.index[-1] == data.close.index[335]
        events.append("train")
        return actual_select(training, start, cost, progress)

    monkeypatch.setattr(research, "select_strategy", checked_select)
    result = research.run_research(data, 80, freeze=lambda _: events.append("frozen"))
    assert events == ["train", "frozen"]
    assert result["split"]["training_periods"] == 256
    assert result["split"]["validation_periods"] == 64
    changed = replace(data, close=data.close.copy(), liquidity=data.liquidity.copy())
    changed.close.iloc[336:] = changed.close.iloc[336:] ** 2
    second = research.run_research(changed, 80)
    assert result["selection"]["members"] == second["selection"]["members"]
    assert result["selection"]["training_fingerprint"] == second["selection"]["training_fingerprint"]
    assert result["strategies"][0]["training"] == second["strategies"][0]["training"]
    assert result["strategies"][0]["validation"] != second["strategies"][0]["validation"]
    first = result["strategies"][0]
    assert (1 + first["training"]["total_return"]) * (1 + first["validation"]["total_return"]) == pytest.approx(1 + first["full"]["total_return"])


def test_rejects_short_history_and_nonfinite_cost():
    with pytest.raises(ValueError, match="260"):
        research.run_research(panel(100), 1)
    with pytest.raises(ValueError, match="transaction_cost"):
        simulate(panel(), panel().close * 0, start=1, cost=float("nan"))


def test_universe_mask_is_applied_to_every_candidate_at_each_date():
    data = panel(100, 2)
    data.universe_mask = pd.DataFrame(
        {"S00": True, "S01": False}, index=data.close.index
    )
    eligible = data.eligible
    assert eligible["S00"].any()
    assert not eligible["S01"].any()
