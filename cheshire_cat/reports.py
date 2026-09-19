"""SEC filing discovery and local report archiving.

SEC filings are the canonical source for US public-company quarterly and annual
reports. The original response is retained byte-for-byte, while a Markdown
rendering is generated for search and dashboard use. The database stores both
paths and the source metadata, making ingestion repeatable.
"""

from __future__ import annotations

import hashlib
import html
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import FinancialReport, FundamentalFact, create_schema, get_engine

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
DEFAULT_FORMS = ("10-K", "10-Q", "20-F", "40-F")


@dataclass(frozen=True)
class Filing:
    symbol: str
    cik: str
    accession_number: str
    form: str
    filing_date: date
    period_end: date | None
    primary_document: str
    source_url: str


class SecFilingsClient:
    def __init__(self, user_agent: str | None = None, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update(
            {"User-Agent": user_agent or settings.sec_user_agent, "Accept-Encoding": "gzip, deflate"}
        )
        self._ticker_map: dict[str, str] | None = None

    def cik_for_symbol(self, symbol: str) -> str:
        if self._ticker_map is None:
            response = self.session.get(SEC_TICKERS_URL, timeout=30)
            response.raise_for_status()
            payload = response.json()
            self._ticker_map = {
                str(item["ticker"]).upper(): str(item["cik_str"]).zfill(10)
                for item in payload.values()
            }
        try:
            return self._ticker_map[symbol.upper()]
        except KeyError as exc:
            raise ValueError(f"SEC does not list ticker {symbol!r}") from exc

    def filings(
        self,
        symbol: str,
        year: int = 2026,
        forms: Iterable[str] = DEFAULT_FORMS,
    ) -> list[Filing]:
        cik = self.cik_for_symbol(symbol)
        response = self.session.get(SEC_SUBMISSIONS_URL.format(cik=cik), timeout=30)
        response.raise_for_status()
        recent = response.json().get("filings", {}).get("recent", {})
        wanted = set(forms)
        found: list[Filing] = []
        for index, filing_form in enumerate(recent.get("form", [])):
            filing_date = _parse_date(recent["filingDate"][index])
            if filing_form not in wanted or filing_date is None or filing_date.year != year:
                continue
            accession = recent["accessionNumber"][index]
            accession_path = accession.replace("-", "")
            document = recent["primaryDocument"][index]
            found.append(
                Filing(
                    symbol=symbol.upper(),
                    cik=cik,
                    accession_number=accession,
                    form=filing_form,
                    filing_date=filing_date,
            period_end=_parse_date(_at(recent.get("reportDate", []), index)),
                    primary_document=document,
                    source_url=SEC_ARCHIVE_URL.format(
                        cik=str(int(cik)), accession=accession_path, document=document
                    ),
                )
            )
        return found

    def company_facts(self, symbol: str) -> tuple[str, dict[str, Any]]:
        cik = self.cik_for_symbol(symbol)
        response = self.session.get(SEC_FACTS_URL.format(cik=cik), timeout=60)
        response.raise_for_status()
        return cik, response.json()

    def download(self, filing: Filing) -> tuple[bytes, str]:
        response = self.session.get(filing.source_url, timeout=60)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        suffix = ".pdf" if "pdf" in content_type or filing.primary_document.lower().endswith(".pdf") else ".html"
        return response.content, suffix


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _at(values: list[str], index: int) -> str | None:
    return values[index] if index < len(values) else None


def extract_company_facts(
    payload: dict[str, Any],
    symbol: str,
    cik: str,
    forms: Iterable[str] = DEFAULT_FORMS,
    filed_year: int | None = None,
) -> list[dict[str, Any]]:
    """Flatten SEC XBRL company facts into database-ready observations."""

    wanted_forms = set(forms)
    rows: list[dict[str, Any]] = []
    for taxonomy, concepts in payload.get("facts", {}).items():
        for concept, definition in concepts.items():
            for unit, observations in definition.get("units", {}).items():
                for observation in observations:
                    form = observation.get("form")
                    period_end = _parse_date(observation.get("end"))
                    filed = _parse_date(observation.get("filed"))
                    if form not in wanted_forms or period_end is None or filed is None:
                        continue
                    if filed_year is not None and filed.year != filed_year:
                        continue
                    value = observation.get("val")
                    if not isinstance(value, (int, float)):
                        continue
                    rows.append(
                        {
                            "symbol": symbol.upper(),
                            "cik": cik,
                            "taxonomy": taxonomy,
                            "concept": concept,
                            "unit": unit,
                            "period_start": _parse_date(observation.get("start")),
                            "period_end": period_end,
                            "filed": filed,
                            "form": form,
                            "frame": observation.get("frame"),
                            "value": float(value),
                            "source_url": SEC_FACTS_URL.format(cik=cik),
                        }
                    )
    return rows


def ingest_fundamentals(
    symbols: list[str],
    filed_year: int | None = None,
    forms: Iterable[str] = DEFAULT_FORMS,
    database_url: str | None = None,
    client: SecFilingsClient | None = None,
) -> dict[str, int]:
    """Retrieve and upsert balance-sheet, income, and cash-flow XBRL facts."""

    client = client or SecFilingsClient()
    create_schema(database_url)
    engine = get_engine(database_url)
    result: dict[str, int] = {}
    with Session(engine) as session:
        for symbol in dict.fromkeys(s.strip().upper() for s in symbols if s.strip()):
            cik, payload = client.company_facts(symbol)
            rows = extract_company_facts(payload, symbol, cik, forms, filed_year)
            inserted = 0
            for values in rows:
                existing = session.scalar(
                    select(FundamentalFact).where(
                        FundamentalFact.symbol == values["symbol"],
                        FundamentalFact.taxonomy == values["taxonomy"],
                        FundamentalFact.concept == values["concept"],
                        FundamentalFact.unit == values["unit"],
                        FundamentalFact.period_end == values["period_end"],
                        FundamentalFact.filed == values["filed"],
                        FundamentalFact.form == values["form"],
                    )
                )
                if existing is None:
                    session.add(FundamentalFact(**values))
                else:
                    for key, value in values.items():
                        setattr(existing, key, value)
                inserted += 1
            session.commit()
            result[symbol] = inserted
    return result


def document_to_markdown(content: bytes | str, source_suffix: str = ".html") -> str:
    """Convert a downloaded filing into readable Markdown without requiring extras."""

    text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
    if source_suffix == ".pdf":
        try:
            from io import BytesIO

            from pypdf import PdfReader

            pages = PdfReader(BytesIO(content if isinstance(content, bytes) else content.encode())).pages
            return "\n\n".join((page.extract_text() or "").strip() for page in pages).strip() + "\n"
        except Exception:  # noqa: BLE001 - malformed vendor PDFs should still archive
            return text
    try:
        from markdownify import markdownify

        return markdownify(text, heading_style="ATX").strip() + "\n"
    except ImportError:
        # This fallback is deliberately conservative and keeps all visible text.
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", html.unescape(text)).strip() + "\n"


def archive_filing(
    filing: Filing,
    content: bytes,
    suffix: str,
    output_dir: Path | None = None,
    database_url: str | None = None,
) -> FinancialReport:
    """Write original and Markdown files and upsert their catalog row."""

    root = output_dir or settings.reports_dir
    create_schema(database_url)
    folder = root / filing.symbol / str(filing.filing_date.year)
    folder.mkdir(parents=True, exist_ok=True)
    safe_accession = filing.accession_number.replace("-", "")
    original = folder / f"{safe_accession}{suffix}"
    markdown = folder / f"{safe_accession}.md"
    original.write_bytes(content)
    markdown.write_text(document_to_markdown(content, suffix), encoding="utf-8")
    digest = hashlib.sha256(content).hexdigest()

    engine = get_engine(database_url)
    with Session(engine) as session:
        record = session.scalar(
            select(FinancialReport).where(
                FinancialReport.symbol == filing.symbol,
                FinancialReport.accession_number == filing.accession_number,
            )
        )
        values: dict[str, Any] = {
            "symbol": filing.symbol,
            "cik": filing.cik,
            "accession_number": filing.accession_number,
            "form": filing.form,
            "filing_date": filing.filing_date,
            "period_end": filing.period_end,
            "source_url": filing.source_url,
            "original_path": str(original),
            "markdown_path": str(markdown),
            "content_hash": digest,
            "metadata_json": {"primary_document": filing.primary_document, "suffix": suffix},
        }
        if record is None:
            record = FinancialReport(**values)
            session.add(record)
        else:
            for key, value in values.items():
                setattr(record, key, value)
        session.commit()
        session.refresh(record)
        return record


def ingest_reports(
    symbols: list[str],
    year: int = 2026,
    forms: Iterable[str] = DEFAULT_FORMS,
    database_url: str | None = None,
    client: SecFilingsClient | None = None,
    output_dir: Path | None = None,
) -> dict[str, int]:
    """Discover, download and archive annual/quarterly filings for each symbol."""

    client = client or SecFilingsClient()
    result: dict[str, int] = {}
    for symbol in dict.fromkeys(s.strip().upper() for s in symbols if s.strip()):
        total = 0
        for filing in client.filings(symbol, year=year, forms=forms):
            content, suffix = client.download(filing)
            archive_filing(filing, content, suffix, output_dir, database_url)
            total += 1
        result[symbol] = total
    return result
