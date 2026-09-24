from dataclasses import asdict, replace

import numpy as np
import pandas as pd
from test_research import panel

from cheshire_cat.challenger import (
    BATCH1_VERSION,
    AtlasFeatures,
    AtlasRule,
    atlas_catalog,
    bounded_allocation,
    ensemble_catalog,
    train_atlas,
)


def test_registered_catalog_and_position_limits():
    assert len(atlas_catalog()) == len({rule.key for rule in atlas_catalog()}) == 48
    assert len(atlas_catalog(BATCH1_VERSION)) == 24
    data = panel(400, 30)
    features = AtlasFeatures(data)
    for rule in (*atlas_catalog(), *atlas_catalog(BATCH1_VERSION)):
        weights = features.targets(rule)
        assert np.isfinite(weights).all().all()
        assert weights.min().min() >= 0
        maximum = min(.10, (2 if rule.construction == "bounded" else 1) / rule.holdings)
        assert weights.max().max() <= maximum + 1e-10
        assert weights.sum(axis=1).max() <= 1 + 1e-10
        assert weights.iloc[:52].sum().sum() == 0


def test_signals_risk_and_targets_are_causal_with_future_ipo():
    data = panel(400, 20)
    original = AtlasFeatures(data)
    changed = replace(data, close=data.close.copy(), liquidity=data.liquidity.copy())
    changed.close.iloc[320:] *= np.arange(20) + 1
    changed.close['FUTURE'] = np.nan
    changed.close.loc[changed.close.index[320]:, 'FUTURE'] = 1_000_000
    changed.liquidity['FUTURE'] = 100_000_000
    later = AtlasFeatures(changed)
    pd.testing.assert_series_equal(original.market_risk.iloc[:320], later.market_risk.iloc[:320])
    for signal in original.signals:
        for defensive in (False, True):
            rule = AtlasRule(signal, 10, defensive)
            pd.testing.assert_frame_equal(original.targets(rule).iloc[:320], later.targets(rule)[data.close.columns].iloc[:320])
        rule = AtlasRule(signal, 10, False, 4, "bounded", "equal")
        pd.testing.assert_frame_equal(original.targets(rule).iloc[:320], later.targets(rule)[data.close.columns].iloc[:320])


def test_all_training_trials_are_exposed_before_ranking():
    data = panel(350, 12)
    saved = []
    rows = train_atlas(data, 56, save_trial=saved.append)
    assert len(saved) == len(rows) == 48
    assert {row['id'] for row in rows} == {row['id'] for row in saved}
    assert rows[0]['score'] == max(row['score'] for row in saved)


def test_bounded_allocation_redistributes_excess_without_leverage():
    raw = np.array([100., *([1.] * 19)])
    weights = bounded_allocation(raw, .1)
    assert np.isclose(weights.sum(), 1)
    assert weights.max() <= .1
    assert np.isclose(weights[0], .1)
    sparse = bounded_allocation(np.array([5., 0., 1.]), .1)
    assert np.isclose(sparse.sum(), .2)
    assert bounded_allocation(np.zeros(3), .1).sum() == 0


def test_training_ensembles_deduplicate_equivalent_sleeves_and_roundtrip():
    rules = [AtlasRule("12m", 10, False, 4, "bounded", "equal"),
             AtlasRule("12m", 10, False, 4, "bounded", "inverse_volatility"),
             AtlasRule("continuous", 20, False, 4, "bounded", "equal"),
             AtlasRule("6m", 40, False, 13, "bounded", "equal")]
    trials = [{"id": rule.key, "parameters": asdict(rule), "score": 4 - i} for i, rule in enumerate(rules)]
    top3, diverse = ensemble_catalog(trials)
    assert len(top3.sleeves) == len(diverse.sleeves) == 3
    assert top3.sleeves[0].weighting == "equal"
    assert [member.signal for member in diverse.sleeves] == ["12m", "continuous", "6m"]
    assert AtlasRule(**asdict(top3)) == top3
    data = panel(400, 20)
    original = AtlasFeatures(data).targets(top3)
    changed = replace(data, close=data.close.copy())
    changed.close.iloc[320:, 0] *= 100
    later = AtlasFeatures(changed).targets(top3)
    pd.testing.assert_frame_equal(original.iloc[:320], later.iloc[:320])
    assert original.max().max() <= .1 + 1e-10
    assert original.sum(axis=1).max() <= 1 + 1e-10
