import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from cheshire_cat.database import FundamentalIngestionState, get_engine
from cheshire_cat.reports import ingest_fundamentals


class FakeSecClient:
    def company_facts(self, symbol):
        return "0001", {
            "facts": {
                "us-gaap": {
                    "Assets": {
                        "units": {
                            "USD": [
                                {
                                    "start": "2024-01-01",
                                    "end": "2024-12-31",
                                    "filed": "2025-02-15",
                                    "form": "10-K",
                                    "accn": "0001-25-000001",
                                    "val": 100,
                                }
                            ]
                        }
                    }
                }
            }
        }


class PartialSecClient(FakeSecClient):
    def company_facts(self, symbol):
        if symbol == "BAD":
            raise requests.Timeout("fixture timeout")
        return super().company_facts(symbol)


def test_sec_ingestion_records_resumable_status_and_provenance(tmp_path):
    url = f"sqlite:///{tmp_path / 'state.sqlite'}"
    assert ingest_fundamentals(["ACME"], database_url=url, client=FakeSecClient()) == {"ACME": 1}
    with Session(get_engine(url)) as session:
        state = session.scalar(select(FundamentalIngestionState))
        assert state.source == "SEC-XBRL"
        assert state.status == "complete"
        assert state.rows_ingested == 1


def test_sec_ingestion_continues_after_an_unavailable_symbol(tmp_path):
    url = f"sqlite:///{tmp_path / 'partial.sqlite'}"
    assert ingest_fundamentals(["BAD", "ACME"], database_url=url, client=PartialSecClient()) == {
        "BAD": 0,
        "ACME": 1,
    }
    with Session(get_engine(url)) as session:
        states = {
            row.symbol: row.status
            for row in session.scalars(select(FundamentalIngestionState)).all()
        }
    assert states == {"BAD": "unavailable", "ACME": "complete"}
