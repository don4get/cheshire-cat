from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from cheshire_cat.api import create_app
from cheshire_cat.database import (
    FundamentalFact,
    PortfolioTransaction,
    Price,
    TickerSymbol,
    create_schema,
    get_engine,
)


pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


def test_api_e2e_serves_playground_readiness_coverage_and_recommendations(tmp_path):
    url = f"sqlite:///{tmp_path / 'api.sqlite'}"
    create_schema(url)
    engine = get_engine(url)
    with Session(engine) as session:
        session.add(TickerSymbol(symbol="AAA", exchange="NASDAQ", currency="USD", source="fixture"))
        session.add(
            FundamentalFact(
                symbol="AAA",
                taxonomy="us-gaap",
                concept="NetIncomeLoss",
                unit="USD",
                currency="USD",
                period_start=date(2023, 1, 1),
                period_end=date(2023, 12, 31),
                filed=date(2024, 2, 15),
                form="10-K",
                value=100.0,
                source_url="fixture",
                source_document_id="fixture-10k",
                source_version="v1",
                context_ref="annual",
                available_on=date(2024, 2, 15),
                availability_status="date_only",
                statement_kind="duration",
                duration_days=365,
            )
        )
        session.add(
            PortfolioTransaction(
                portfolio="long-term",
                symbol="AAA",
                trade_date=date(2024, 1, 1),
                quantity=10,
                price=100,
            )
        )
        for offset in range(130):
            day = date(2023, 1, 6) + timedelta(days=offset * 7)
            session.add(Price(symbol="AAA", date=day, close=100 + offset, adj_close=100 + offset, volume=1_000_000))
        session.commit()

    with TestClient(create_app(url)) as client:
        assert client.get("/health").json() == {"status": "ok"}

        playground = client.get("/api/playground", params={"symbols": "AAA", "years": 1})
        assert playground.status_code == 200
        assert playground.json()["frequency"] == "weekly"
        assert len(playground.json()["strategies"]) == 5
        assert "fundamental_readiness" in playground.json()

        readiness = client.get("/api/fundamentals/readiness", params={"symbols": "AAA", "as_of": "2025-01-01"})
        assert readiness.status_code == 200
        assert readiness.json()["as_of"] == "2025-01-01"

        coverage = client.get("/api/fundamentals/coverage", params={"dates": "2024-03-01,2025-01-01"})
        assert coverage.status_code == 200
        assert coverage.json()["request_scope"]["bounded_default_cohort"] is True
        scoped = client.get(
            "/api/fundamentals/coverage",
            params={"dates": "2025-01-01", "symbols": "AAA"},
        )
        assert scoped.status_code == 200
        assert scoped.json()["request_scope"]["symbols"] == ["AAA"]
        assert coverage.json()["snapshots"][0]["universe_symbols"] == 1
        assert "ingestion_progress" in coverage.json()

        recommendation = client.get(
            "/api/recommendations", params={"portfolio": "long-term", "amount": 1000}
        )
        assert recommendation.status_code == 200
        assert recommendation.json()["suggestions"][0]["symbol"] == "AAA"
