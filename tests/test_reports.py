from datetime import date
from io import BytesIO
from zipfile import ZipFile

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from cheshire_cat.database import FinancialReport, FundamentalFact, create_schema, get_engine
from cheshire_cat.reports import Filing, archive_filing, document_to_markdown, extract_company_facts


def test_archive_filing_keeps_original_and_markdown(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'reports.sqlite'}"
    create_schema(database_url)
    filing = Filing(
        symbol="MSFT",
        cik="0000789019",
        accession_number="0000789019-26-000001",
        form="10-Q",
        filing_date=date(2026, 4, 30),
        period_end=date(2026, 3, 31),
        primary_document="msft-10q.htm",
        source_url="https://example.test/filing",
    )
    record = archive_filing(
        filing,
        b"<html><body><h1>Balance Sheet</h1><p>Total assets</p></body></html>",
        ".html",
        tmp_path / "reports",
        database_url,
    )
    assert record.original_path.endswith(".html")
    assert record.markdown_path.endswith(".md")
    with open(record.markdown_path, encoding="utf-8") as markdown_file:
        assert "Balance Sheet" in markdown_file.read()
    with Session(get_engine(database_url)) as session:
        assert len(session.scalars(select(FinancialReport)).all()) == 1


def test_document_fallback_removes_html_tags():
    markdown = document_to_markdown("<h1>Title</h1><p>Hello</p>", ".unknown")
    assert "Title" in markdown and "Hello" in markdown


def test_document_to_markdown_extracts_esef_zip_without_losing_source():
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("reports/main.xhtml", "<html><body><h1>Annual report</h1></body></html>")
    markdown = document_to_markdown(buffer.getvalue(), ".zip")
    assert "Annual report" in markdown


def test_extract_company_facts_keeps_quarterly_and_annual_observations():
    payload = {
        "facts": {
            "us-gaap": {
                "Assets": {
                    "label": "Assets",
                    "units": {
                        "USD": [
                            {"end": "2026-03-31", "filed": "2026-04-30", "form": "10-Q", "val": 123},
                            {"end": "2026-12-31", "filed": "2027-02-01", "form": "10-K", "val": 456},
                        ]
                    },
                }
            }
        }
    }
    rows = extract_company_facts(payload, "msft", "0000789019", filed_year=2026)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "MSFT"
    assert rows[0]["value"] == 123.0


def test_sqlite_migration_preserves_legacy_facts_and_marks_them_unknown(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'legacy.sqlite'}"
    engine = get_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE fundamental_facts ("
                "id INTEGER PRIMARY KEY, symbol VARCHAR(32), cik VARCHAR(16), "
                "taxonomy VARCHAR(32), concept TEXT, unit VARCHAR(32), period_end DATE NOT NULL, "
                "filed DATE NOT NULL, form VARCHAR(16), frame VARCHAR(32), value FLOAT, source_url TEXT, "
                "CONSTRAINT uq_old UNIQUE(symbol, taxonomy, concept, unit, period_end, filed, form))"
            )
        )
        connection.execute(
            text(
                "INSERT INTO fundamental_facts "
                "(symbol, cik, taxonomy, concept, unit, period_end, filed, form, value, source_url) "
                "VALUES ('MSFT', '1', 'us-gaap', 'Assets', 'USD', '2024-12-31', '2025-02-01', '10-K', 1, 'fixture')"
            )
        )
    create_schema(database_url)
    with Session(engine) as session:
        fact = session.scalar(select(FundamentalFact))
        assert fact is not None
        assert fact.period_start is None
        assert fact.availability_status == "unknown"
        assert fact.retrieved_at is not None


def test_fundamental_reimport_is_idempotent_but_amendment_is_a_new_version(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'versions.sqlite'}"

    class Client:
        amended = False

        def company_facts(self, symbol):
            observations = [
                {
                    "start": "2024-01-01", "end": "2024-12-31", "filed": "2025-02-15",
                    "form": "10-K", "accn": "0001-25-000001", "val": 100,
                },
                {
                    "start": "2024-01-01", "end": "2024-03-31", "filed": "2024-04-30",
                    "form": "10-Q", "accn": "0001-24-000001", "val": 20,
                },
            ]
            if self.amended:
                observations.append(
                    {
                        "start": "2024-01-01", "end": "2024-12-31", "filed": "2025-04-01",
                        "form": "10-K", "accn": "0001-25-000002", "val": 110,
                    }
                )
            return "0001", {"facts": {"us-gaap": {"Revenue": {"units": {"USD": observations}}}}}

    client = Client()
    from cheshire_cat.reports import ingest_fundamentals

    ingest_fundamentals(["ACME"], database_url=database_url, client=client)
    ingest_fundamentals(["ACME"], database_url=database_url, client=client)
    with Session(get_engine(database_url)) as session:
        assert len(session.scalars(select(FundamentalFact)).all()) == 2
        assert {fact.currency for fact in session.scalars(select(FundamentalFact)).all()} == {"USD"}
    client.amended = True
    ingest_fundamentals(["ACME"], database_url=database_url, client=client)
    with Session(get_engine(database_url)) as session:
        facts = session.scalars(select(FundamentalFact)).all()
        assert len(facts) == 3
        assert {fact.value for fact in facts} == {20.0, 100.0, 110.0}


def test_quarter_and_ytd_observations_sharing_an_end_date_remain_distinct():
    payload = {
        "facts": {
            "us-gaap": {
                "Revenue": {
                    "units": {
                        "USD": [
                            {"start": "2026-01-01", "end": "2026-03-31", "filed": "2026-04-30", "form": "10-Q", "accn": "q", "val": 10},
                            {"start": "2026-01-01", "end": "2026-03-31", "filed": "2026-04-30", "form": "10-Q", "accn": "ytd", "fp": "Q1", "val": 10},
                        ]
                    }
                }
            }
        }
    }
    rows = extract_company_facts(payload, "ACME", "1")
    assert len(rows) == 2
    assert {row["source_document_id"] for row in rows} == {"q", "ytd"}
