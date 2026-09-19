from datetime import date

from sqlalchemy.orm import Session

from cheshire_cat.dashboard import dashboard_data
from cheshire_cat.database import FundamentalFact, Price, create_schema, get_engine


def test_dashboard_data_returns_all_fundamental_observation_fields(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'dashboard.sqlite'}"
    create_schema(database_url)
    with Session(get_engine(database_url)) as session:
        session.add(
            Price(
                symbol="MSFT",
                date=date(2026, 6, 30),
                close=500.0,
                adj_close=500.0,
                source="test",
            )
        )
        session.add(
            FundamentalFact(
                symbol="MSFT",
                cik="0000789019",
                taxonomy="us-gaap",
                concept="Assets",
                unit="USD",
                period_start=None,
                period_end=date(2026, 6, 30),
                filed=date(2026, 7, 30),
                form="10-K",
                frame="CY2026",
                value=619_000_000_000.0,
                source_url="https://example.test/facts",
            )
        )
        session.commit()

    fundamentals = dashboard_data(database_url, "MSFT")["fundamentals"]
    assert fundamentals.to_dict("records") == [
        {
            "symbol": "MSFT",
            "taxonomy": "us-gaap",
            "concept": "Assets",
            "unit": "USD",
            "period_start": None,
            "period_end": date(2026, 6, 30),
            "filed": date(2026, 7, 30),
            "form": "10-K",
            "frame": "CY2026",
            "value": 619_000_000_000.0,
        }
    ]
