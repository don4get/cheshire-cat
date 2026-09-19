from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from cheshire_cat.database import FinancialReport, create_schema, get_engine
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
