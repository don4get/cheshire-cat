import numpy as np
import pandas as pd

from cheshire_cat.fundamental_research import (
    FundamentalCandidate,
    build_fundamental_targets,
    run_fundamental_experiment,
)
from cheshire_cat.research import MarketPanel


def _panel(periods=180):
    dates = pd.date_range("2010-01-01", periods=periods, freq="W-FRI")
    close = pd.DataFrame(
        {
            "AAA": np.linspace(100, 180, len(dates)),
            "BBB": np.linspace(120, 110, len(dates)),
        },
        index=dates,
    )
    return MarketPanel(close, close * 100_000, {"market": "fixture", "currency": "USD"})


def _features(panel):
    rows = []
    for decision_date in panel.close.index:
        for symbol in panel.close.columns:
            rows.extend(
                {
                    "decision_date": decision_date,
                    "symbol": symbol,
                    "feature": feature,
                    "value": value,
                    "status": "usable",
                }
                for feature, value in {
                    "earnings_yield": 0.10 if symbol == "AAA" else 0.05,
                    "fcf_yield": 0.08 if symbol == "AAA" else 0.04,
                    "book_to_price": 1.0,
                    "operating_margin": 0.2 if symbol == "AAA" else 0.1,
                }.items()
            )
    return pd.DataFrame(rows)


def test_fundamental_targets_use_the_same_price_panel_dates():
    panel = _panel()
    weights = build_fundamental_targets(
        panel,
        FundamentalCandidate("value", ("earnings_yield", "fcf_yield"), holdings=1),
        _features(panel),
    )
    assert weights.index.equals(panel.close.index)
    assert weights.columns.tolist() == ["AAA", "BBB"]
    assert np.isfinite(weights.to_numpy()).all()


def test_matched_experiment_records_manifest_trials_stress_and_uncertainty():
    panel = _panel()
    report = run_fundamental_experiment(
        panel,
        _features(panel),
        60,
        candidate_catalog=(
            FundamentalCandidate("value", ("earnings_yield", "fcf_yield"), holdings=1),
            FundamentalCandidate("benchmark", (), holdings=500),
        ),
        sector_by_symbol={"AAA": "Technology", "BBB": "Consumer"},
    )
    assert report["manifest"]["same_universe_and_cost_for_all"] is True
    assert len(report["trials"]) == 2
    assert report["stress"]["transaction_cost"] == 0.002
    assert "extra_week_execution_delay" in report["stress"]["variants"]
    assert "sector_exposure" in report["concentration"]
    assert report["uncertainty"]["replicates"] == 200


def test_matched_experiment_selects_inside_expanding_and_rolling_folds():
    panel = _panel(periods=700)
    report = run_fundamental_experiment(
        panel,
        _features(panel),
        60,
        candidate_catalog=(
            FundamentalCandidate("value", ("earnings_yield",), holdings=1),
            FundamentalCandidate("benchmark", (), holdings=500),
        ),
    )
    assert report["manifest"]["selection_protocol"]["selection_gap_weeks"] == 4
    assert [row["status"] for row in report["walk_forward"]] == ["complete", "complete"]
    assert report["walk_forward"][0]["folds"]
    assert all(row["selection_scores"] for row in report["walk_forward"][0]["folds"])
