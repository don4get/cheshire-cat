from datetime import date

import pandas as pd

from cheshire_cat.market_data import YahooChartProvider, ingest_history, normalize_history


def test_normalize_history_handles_provider_frame():
    frame = pd.DataFrame(
        {"Open": [10], "High": [11], "Low": [9], "Close": [10.5], "Volume": [100]},
        index=pd.DatetimeIndex(["2024-01-02"], name="Date"),
    )
    assert normalize_history(frame, "msft") == [
        {
            "symbol": "MSFT",
            "date": date(2024, 1, 2),
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "adj_close": 10.5,
            "volume": 100,
            "source": "yfinance",
        }
    ]


def test_ingest_history_is_idempotent(tmp_path):
    class Provider:
        def history(self, symbol, start, end, interval):
            return pd.DataFrame(
                {"open": [10], "high": [11], "low": [9], "close": [10.5], "volume": [100]},
                index=pd.DatetimeIndex(["2024-01-02"]),
            )

    database_url = f"sqlite:///{tmp_path / 'prices.sqlite'}"
    assert ingest_history(["msft"], database_url=database_url, provider=Provider()) == {"MSFT": 1}
    assert ingest_history(["MSFT"], database_url=database_url, provider=Provider()) == {"MSFT": 1}


def test_yahoo_chart_provider_normalizes_real_chart_payload():
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "chart": {
                    "result": [
                        {
                            "timestamp": [1704153600],
                            "indicators": {
                                "quote": [
                                    {
                                        "open": [10.0],
                                        "high": [11.0],
                                        "low": [9.0],
                                        "close": [10.5],
                                        "volume": [2_000_000_000],
                                    }
                                ],
                                "adjclose": [{"adjclose": [10.25]}],
                            },
                        }
                    ]
                }
            }

    class Session:
        def __init__(self):
            self.headers = {}
            self.proxies = {}

        def get(self, *args, **kwargs):
            return Response()

    frame = YahooChartProvider(session=Session()).history("MSFT", None, None, "1wk")
    assert frame.iloc[0]["Close"] == 10.5
    assert frame.iloc[0]["Adj Close"] == 10.25
    assert frame.iloc[0]["Volume"] == 2_000_000_000
