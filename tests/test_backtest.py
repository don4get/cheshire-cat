import pandas as pd

from cheshire_cat.backtest import StrategyConfig, backtest


def test_backtest_delays_signal_and_reports_benchmark():
    prices = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=8),
            "symbol": ["AAA"] * 8,
            "close": [10, 10, 10, 10, 11, 12, 13, 14],
        }
    )
    result = backtest(prices, config=StrategyConfig(fast_window=2, slow_window=3))
    assert result.weights.iloc[0, 0] == 0
    assert result.equity_curve.iloc[0].strategy == 1
    assert set(result.metrics) == {
        "total_return",
        "annualized_return",
        "annualized_volatility",
        "sharpe",
        "max_drawdown",
    }
    assert "total_return" in result.benchmark_metrics
