import numpy as np
import pandas as pd

from cheshire_cat.playground import run_playground


def test_playground_runs_registered_bots_on_same_window():
    dates = pd.date_range("2005-01-01", periods=520, freq="W-FRI")
    trend = np.linspace(100.0, 240.0, len(dates))
    prices = pd.DataFrame(
        [
            {"date": date, "symbol": symbol, "close": value, "adj_close": value}
            for symbol, values in {"AAA": trend, "BBB": trend[::-1]}.items()
            for date, value in zip(dates, values, strict=True)
        ]
    )

    result = run_playground(prices, initial_cash=10_000, annualization=52)

    assert result["frequency"] == "weekly"
    assert result["symbols"] == ["AAA", "BBB"]
    assert len(result["strategies"]) == 5
    assert [item["rank"] for item in result["strategies"]] == [1, 2, 3, 4, 5]
    assert all(len(item["curve"]) == 520 for item in result["strategies"])
    assert all(item["metrics"]["final_value"] > 0 for item in result["strategies"])
