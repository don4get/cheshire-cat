from datetime import date

import pandas as pd

from cheshire_cat.external_fundamentals import yahoo_frame_to_facts
from cheshire_cat.fundamental_ratios import compute_fundamental_ratios


def test_yahoo_statement_units_do_not_treat_equity_as_shares():
    facts = yahoo_frame_to_facts(
        pd.DataFrame(
            [
                {
                    "symbol": "MC.PA",
                    "asOfDate": date(2025, 12, 31),
                    "periodType": "12M",
                    "currencyCode": "EUR",
                    "StockholdersEquity": 50_000_000.0,
                    "OrdinarySharesNumber": 1_000_000.0,
                    "DilutedEPS": 5.0,
                }
            ]
        )
    )
    units = {row["concept"]: row["unit"] for row in facts}
    assert units["StockholdersEquity"] == "EUR"
    assert units["OrdinarySharesNumber"] == "shares"
    assert units["DilutedEPS"] == "EUR/share"


def test_compute_fundamental_ratios_uses_annual_observations():
    facts = pd.DataFrame(
        [
            {"taxonomy": "YahooFinance", "concept": "TotalRevenue", "unit": "EUR", "period_end": "2025-12-31", "filed": "2025-12-31", "form": "YAHOO-12M", "value": 1_000.0},
            {"taxonomy": "YahooFinance", "concept": "NetIncome", "unit": "EUR", "period_end": "2025-12-31", "filed": "2025-12-31", "form": "YAHOO-12M", "value": 100.0},
            {"taxonomy": "YahooFinance", "concept": "StockholdersEquity", "unit": "EUR", "period_end": "2025-12-31", "filed": "2025-12-31", "form": "YAHOO-12M", "value": 500.0},
            {"taxonomy": "YahooFinance", "concept": "Assets", "unit": "EUR", "period_end": "2025-12-31", "filed": "2025-12-31", "form": "YAHOO-12M", "value": 2_000.0},
            {"taxonomy": "YahooFinance", "concept": "DilutedEPS", "unit": "EUR/share", "period_end": "2025-12-31", "filed": "2025-12-31", "form": "YAHOO-12M", "value": 5.0},
            {"taxonomy": "YahooFinance", "concept": "OrdinarySharesNumber", "unit": "shares", "period_end": "2025-12-31", "filed": "2025-12-31", "form": "YAHOO-12M", "value": 100.0},
        ]
    )
    ratios = {row["key"]: row["value"] for row in compute_fundamental_ratios(facts, 50.0)}
    assert ratios["pe"] == 10.0
    assert ratios["ps"] == 5.0
    assert ratios["pb"] == 10.0
    assert ratios["net_margin"] == 0.1
    assert ratios["roe"] == 0.2
    assert ratios["roa"] == 0.05
