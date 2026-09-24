"""SEC filing discovery and local report archiving.

SEC filings are the canonical source for US public-company quarterly and annual
reports. The original response is retained byte-for-byte, while a Markdown
rendering is generated for search and dashboard use. The database stores both
paths and the source metadata, making ingestion repeatable.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import threading
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zipfile import ZipFile

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import settings
from .database import (
    FinancialReport,
    FundamentalFact,
    FundamentalIngestionState,
    TickerSymbol,
    create_schema,
    get_engine,
)

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
AMF_RECORDS_URL = (
    "https://www.info-financiere.gouv.fr/api/explore/v2.0/catalog/datasets/"
    "flux-amf-new-prod/records"
)
DEFAULT_FORMS = ("10-K", "10-Q", "20-F", "40-F")
AMF_REPORT_SUBTYPES = (
    "Rapports financiers et d'audit annuels",
    "Document de référence",
)


def _configure_http_retries(session: requests.Session) -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


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


class AmfFilingsClient:
    """Discover official French annual-report packages by issuer ISIN."""

    def __init__(self, session: requests.Session | None = None):
        self.session = _configure_http_retries(session or requests.Session())
        self.session.headers.setdefault("User-Agent", "cheshire-cat/0.1 research client")

    def annual_report(self, isin: str) -> dict[str, Any] | None:
        subtype_filter = " OR ".join(
            f'sous_type_d_information="{subtype}"' for subtype in AMF_REPORT_SUBTYPES
        )
        response = self.session.get(
            AMF_RECORDS_URL,
            params={
                "select": (
                    "uin_idt_uin,informationdeposee_inf_dat_emt,"
                    "informationdeposee_inf_tit_inf,sous_type_d_information,"
                    "url_de_recuperation,fichierdecontenu_inf_fic_nom"
                ),
                "where": f'identificationsociete_iso_cd_isi="{isin}" AND ({subtype_filter})',
                "limit": 100,
            },
            timeout=60,
        )
        response.raise_for_status()
        records = [item.get("record", {}).get("fields", {}) for item in response.json().get("records", [])]
        records = [record for record in records if record.get("url_de_recuperation")]
        if not records:
            return None
        # Prefer the actual reference-document/ESEF package over a publication
        # announcement, then choose the most recently deposited record.
        records.sort(key=_amf_record_priority, reverse=True)
        return records[0]

    def download(self, record: dict[str, Any]) -> tuple[bytes, str]:
        source_url = str(record["url_de_recuperation"])
        content = self._download_bytes(source_url)
        return content, _report_suffix(content)

    def _download_bytes(self, source_url: str) -> bytes:
        total_size: int | None = None
        resolved_url = source_url
        try:
            head = self.session.head(source_url, timeout=15, allow_redirects=True)
            head.raise_for_status()
            resolved_url = head.url
            total_size = int(head.headers.get("Content-Length") or 0) or None
        except (requests.RequestException, ValueError):
            pass

        if total_size and total_size > 2_000_000:
            chunk_size = 2_000_000
            ranges = [
                (start, min(start + chunk_size, total_size) - 1)
                for start in range(0, total_size, chunk_size)
            ]

            thread_state = threading.local()

            def fetch_range(item: tuple[int, int]) -> bytes:
                start, end = item
                session = getattr(thread_state, "session", None)
                if session is None:
                    session = requests.Session()
                    _configure_http_retries(session)
                    session.headers.update(
                        {
                            "User-Agent": self.session.headers.get("User-Agent", "cheshire-cat/0.1"),
                            "Accept-Encoding": "identity",
                        }
                    )
                    thread_state.session = session
                with session.get(
                    resolved_url,
                    headers={
                        "Range": f"bytes={start}-{end}",
                    },
                    stream=True,
                    timeout=(15, 60),
                ) as response:
                    response.raise_for_status()
                    # Check the status before reading the body. Some gateways
                    # ignore Range and would otherwise download the whole large
                    # package for every chunk before we reject it.
                    if response.status_code != 206:
                        raise requests.RequestException("AMF source did not honor the byte range")
                    expected = end - start + 1
                    declared = int(response.headers.get("Content-Length") or 0)
                    if declared != expected:
                        raise requests.RequestException("AMF source returned an unexpected byte range")
                    content = response.content
                    if len(content) != expected:
                        raise requests.RequestException("AMF source returned an incomplete byte range")
                    return content

            try:
                with ThreadPoolExecutor(max_workers=min(4, len(ranges))) as pool:
                    chunks = list(pool.map(fetch_range, ranges))
                return b"".join(chunks)
            except (requests.RequestException, OSError):
                pass

        response = self.session.get(resolved_url, timeout=(15, 120))
        response.raise_for_status()
        return response.content


def _report_suffix(content: bytes) -> str:
    trimmed = content.lstrip(b"\xef\xbb\xbf \t\r\n")
    if content.startswith(b"PK\x03\x04"):
        return ".zip"
    if trimmed.startswith((b"<", b"<?xml")):
        return ".html"
    return ".pdf"


class SecFilingsClient:
    def __init__(self, user_agent: str | None = None, session: requests.Session | None = None):
        self.session = _configure_http_retries(session or requests.Session())
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


def _currency_from_unit(unit: str | None) -> str | None:
    """Extract the reporting currency from an XBRL unit when available."""

    if not unit:
        return None
    token = str(unit).split("/", 1)[0].strip().upper()
    if token in {"SHARES", "SHARE", "RATIO", "PURE", "PERCENT", "%"}:
        return None
    return token or None


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
                    period_start = _parse_date(observation.get("start"))
                    accession = str(observation.get("accn") or "").strip() or None
                    context_parts = [
                        str(item)
                        for item in (
                            period_start,
                            period_end,
                            observation.get("frame"),
                            observation.get("fp"),
                            observation.get("fy"),
                            form,
                        )
                        if item not in (None, "")
                    ]
                    rows.append(
                        {
                            "symbol": symbol.upper(),
                            "cik": cik,
                            "taxonomy": taxonomy,
                            "concept": concept,
                            "unit": unit,
                            "currency": _currency_from_unit(unit),
                            "period_start": period_start,
                            "period_end": period_end,
                            "filed": filed,
                            "form": form,
                            "frame": observation.get("frame"),
                            "value": float(value),
                            "source_url": SEC_FACTS_URL.format(cik=cik),
                            "source_document_id": accession or cik,
                            "source_version": accession or f"{filed.isoformat()}:{form}",
                            "context_ref": "|".join(context_parts),
                            "available_on": filed,
                            # SEC company facts exposes a filing date, not an
                            # exact publication timestamp. Date-only evidence
                            # is deliberately kept separate from available_at.
                            "available_at": None,
                            "availability_status": "date_only",
                            "statement_kind": "duration" if period_start else "instant",
                            "duration_days": (
                                (period_end - period_start).days + 1 if period_start else None
                            ),
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
    forms = tuple(forms)
    create_schema(database_url)
    engine = get_engine(database_url)
    result: dict[str, int] = {}
    with Session(engine) as session:
        for symbol in dict.fromkeys(s.strip().upper() for s in symbols if s.strip()):
            _set_fundamental_ingestion_state(session, "SEC-XBRL", symbol, "in_progress")
            session.commit()
            try:
                cik, payload = client.company_facts(symbol)
                rows = extract_company_facts(payload, symbol, cik, forms, filed_year)
                result[symbol] = _upsert_fundamentals(session, rows)
            except requests.RequestException as exc:
                _set_fundamental_ingestion_state(
                    session, "SEC-XBRL", symbol, "unavailable", error=str(exc)
                )
                session.commit()
                result[symbol] = 0
                continue
            except (KeyError, TypeError, ValueError) as exc:
                _set_fundamental_ingestion_state(
                    session, "SEC-XBRL", symbol, "failed", error=str(exc)
                )
                session.commit()
                result[symbol] = 0
                continue
            else:
                _set_fundamental_ingestion_state(
                    session,
                    "SEC-XBRL",
                    symbol,
                    "complete" if result[symbol] else "empty",
                    rows_ingested=result[symbol],
                    metadata={"filed_year": filed_year, "forms": list(forms)},
                )
                session.commit()
    return result


def _set_fundamental_ingestion_state(
    session: Session,
    source: str,
    symbol: str,
    status: str,
    *,
    rows_ingested: int = 0,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Update a source cursor without overwriting any fact observation."""

    record = session.scalar(
        select(FundamentalIngestionState).where(
            FundamentalIngestionState.source == source,
            FundamentalIngestionState.symbol == symbol,
        )
    )
    if record is None:
        record = FundamentalIngestionState(source=source, symbol=symbol, status=status)
        session.add(record)
    record.status = status
    record.rows_ingested = rows_ingested
    record.attempted_at = datetime.now(UTC).replace(tzinfo=None)
    record.completed_at = record.attempted_at if status in {"complete", "empty", "unavailable", "failed", "error"} else None
    record.last_error = error
    record.metadata_json = metadata


def _upsert_fundamentals(
    session: Session,
    rows: list[dict[str, Any]],
    update_existing: bool = True,
) -> int:
    """Bulk-upsert observations while preserving the source values exactly."""

    if not rows:
        return 0

    # SEC company-facts can repeat an observation in a single response. Keep
    # the last copy before sending rows to the database's unique constraint.
    unique_columns = (
        "symbol",
        "taxonomy",
        "concept",
        "unit",
        "period_start",
        "period_end",
        "form",
        "source_document_id",
        "source_version",
        "context_ref",
        "currency",
    )
    normalized_rows = []
    for row in rows:
        normalized = dict(row)
        normalized.setdefault("availability_status", "unknown")
        normalized.setdefault("statement_kind", "unknown")
        normalized.setdefault("source_document_id", None)
        normalized.setdefault("source_version", None)
        normalized.setdefault("context_ref", None)
        normalized.setdefault("currency", _currency_from_unit(normalized.get("unit")))
        normalized.setdefault("available_on", None)
        normalized.setdefault("available_at", None)
        normalized.setdefault("duration_days", None)
        # A provider may omit a report/accession identity.  Preserve such a
        # row as explicitly unverified, but give repeated imports a stable
        # identity so SQLite/PostgreSQL NULL semantics cannot duplicate it.
        identity_seed = {
            key: normalized.get(key)
            for key in (
                "symbol", "taxonomy", "concept", "unit", "currency", "period_start",
                "period_end", "form", "frame", "value", "source_url",
            )
        }
        seed = json.dumps(identity_seed, sort_keys=True, default=str).encode()
        synthetic_id = f"synthetic:{hashlib.sha256(seed).hexdigest()}"
        normalized["source_document_id"] = normalized["source_document_id"] or synthetic_id
        normalized["source_version"] = normalized["source_version"] or "synthetic:unversioned"
        normalized["context_ref"] = normalized["context_ref"] or "synthetic:undimensioned"
        normalized_rows.append(normalized)
    deduplicated = {
        tuple(row[column] for column in unique_columns): row
        for row in normalized_rows
    }
    values = list(deduplicated.values())
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        for row in values:
            existing = session.scalar(
                select(FundamentalFact).where(
                    *(getattr(FundamentalFact, column) == row[column] for column in unique_columns)
                )
            )
            if existing is None:
                session.add(FundamentalFact(**row))
            else:
                for key, value in row.items():
                    setattr(existing, key, value)
        session.commit()
        return len(values)

    if dialect == "postgresql" and not update_existing:
        return _copy_fundamentals(session, values, unique_columns)

    # Keep statements comfortably below PostgreSQL's parameter limit for the
    # largest company-facts payloads (12 columns x 4,000 rows = 48,000 params).
    table = FundamentalFact.__table__
    chunk_size = 4000
    if update_existing:
        for offset in range(0, len(values), chunk_size):
            chunk = values[offset : offset + chunk_size]
            statement = insert(table).values(chunk)
            update = {
                key: getattr(statement.excluded, key)
                for key in chunk[0]
                if key not in unique_columns
            }
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=list(unique_columns),
                    set_=update,
                )
            )
    else:
        for offset in range(0, len(values), chunk_size):
            chunk = values[offset : offset + chunk_size]
            statement = insert(table).values(chunk).on_conflict_do_nothing(
                index_elements=list(unique_columns)
            )
            session.execute(statement)
    session.commit()
    return len(values)


def _copy_fundamentals(
    session: Session,
    values: list[dict[str, Any]],
    unique_columns: tuple[str, ...],
) -> int:
    """Load a fresh company-facts payload through PostgreSQL COPY."""

    columns = tuple(values[0])
    column_sql = ",".join(columns)
    table = FundamentalFact.__table__
    connection = session.connection()
    driver = connection.connection.driver_connection
    with driver.cursor() as cursor:
        cursor.execute(
            "CREATE TEMP TABLE fundamental_facts_stage "
            "(LIKE fundamental_facts INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        with cursor.copy(
            f"COPY fundamental_facts_stage ({column_sql}) FROM STDIN"
        ) as copy:
            for row in values:
                copy.write_row(tuple(row[column] for column in columns))
        cursor.execute(
            f"INSERT INTO {table.name} ({column_sql}) "
            f"SELECT {column_sql} FROM fundamental_facts_stage "
            f"ON CONFLICT ({','.join(unique_columns)}) DO NOTHING"
        )
    session.commit()
    return len(values)


def document_to_markdown(content: bytes | str, source_suffix: str = ".html") -> str:
    """Convert a downloaded filing into readable Markdown without requiring extras."""

    if source_suffix == ".zip" and isinstance(content, bytes):
        if len(content) > 20_000_000:
            return (
                "ESEF package archived as ZIP; Markdown extraction skipped for this "
                f"{len(content) / 1_000_000:.1f} MB source package.\n"
            )
        try:
            with ZipFile(BytesIO(content)) as archive:
                candidates = [
                    info
                    for info in archive.infolist()
                    if not info.is_dir() and info.filename.lower().endswith((".html", ".xhtml"))
                ]
                if candidates:
                    main_document = max(candidates, key=lambda info: info.file_size)
                    return _compact_html_text(archive.read(main_document))
        except Exception:  # noqa: BLE001 - preserve an unreadable ESEF package as-is
            return "ESEF package archived as ZIP; no HTML document could be extracted.\n"
        return "ESEF package archived as ZIP; no HTML document could be extracted.\n"
    text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
    if source_suffix == ".pdf":
        try:
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
    engine=None,
) -> FinancialReport:
    """Write original and Markdown files and upsert their catalog row."""

    root = output_dir or settings.reports_dir
    folder = root / filing.symbol / str(filing.filing_date.year)
    folder.mkdir(parents=True, exist_ok=True)
    safe_accession = filing.accession_number.replace("-", "")
    original = folder / f"{safe_accession}{suffix}"
    markdown = folder / f"{safe_accession}.md"
    original.write_bytes(content)
    markdown.write_text(document_to_markdown(content, suffix), encoding="utf-8")
    digest = hashlib.sha256(content).hexdigest()

    database_engine = engine or get_engine(database_url)
    with Session(database_engine) as session:
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
    forms = tuple(forms)
    create_schema(database_url)
    result: dict[str, int] = {}
    state_session = Session(get_engine(database_url))
    try:
        for symbol in dict.fromkeys(s.strip().upper() for s in symbols if s.strip()):
            _set_fundamental_ingestion_state(state_session, "SEC-FILING", symbol, "in_progress")
            state_session.commit()
            total = 0
            try:
                for filing in client.filings(symbol, year=year, forms=forms):
                    content, suffix = client.download(filing)
                    archive_filing(filing, content, suffix, output_dir, database_url)
                    total += 1
            except requests.RequestException as exc:
                _set_fundamental_ingestion_state(
                    state_session, "SEC-FILING", symbol, "unavailable", error=str(exc)
                )
                state_session.commit()
                result[symbol] = 0
                continue
            except (OSError, KeyError, TypeError, ValueError) as exc:
                _set_fundamental_ingestion_state(
                    state_session, "SEC-FILING", symbol, "failed", error=str(exc)
                )
                state_session.commit()
                result[symbol] = 0
                continue
            result[symbol] = total
            _set_fundamental_ingestion_state(
                state_session,
                "SEC-FILING",
                symbol,
                "complete" if total else "empty",
                rows_ingested=total,
                metadata={"year": year, "forms": list(forms)},
            )
            state_session.commit()
    finally:
        state_session.close()
    return result


def ingest_external_report(
    symbol: str,
    accession_number: str,
    form: str,
    filing_date: date,
    period_end: date | None,
    source_url: str,
    database_url: str | None = None,
    output_dir: Path | None = None,
    session: requests.Session | None = None,
) -> FinancialReport:
    """Archive an issuer-hosted report when SEC does not cover the issuer."""

    http = session or requests.Session()
    http.headers.setdefault("User-Agent", settings.sec_user_agent)
    response = http.get(source_url, timeout=120)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    suffix = ".pdf" if "pdf" in content_type or urlparse(source_url).path.lower().endswith(".pdf") else ".html"
    filing = Filing(
        symbol=symbol.upper(),
        cik="",
        accession_number=accession_number,
        form=form,
        filing_date=filing_date,
        period_end=period_end,
        primary_document=Path(urlparse(source_url).path).name or accession_number,
        source_url=source_url,
    )
    return archive_filing(
        filing,
        response.content,
        suffix,
        output_dir=output_dir,
        database_url=database_url,
    )


def ingest_amf_reports(
    symbols: Iterable[str],
    database_url: str | None = None,
    output_dir: Path | None = None,
    client: AmfFilingsClient | None = None,
    workers: int = 4,
) -> dict[str, int]:
    """Archive the latest official AMF annual/ESEF report for each ISIN."""

    if workers < 1:
        raise ValueError("workers must be positive")
    normalized = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
    create_schema(database_url)
    with Session(get_engine(database_url)) as session:
        isin_by_symbol = dict(
            session.execute(
                select(TickerSymbol.symbol, TickerSymbol.isin).where(
                    TickerSymbol.symbol.in_(normalized),
                    TickerSymbol.isin.is_not(None),
                )
            ).all()
        )
    result = {symbol: 0 for symbol in normalized}
    candidates = [(symbol, isin) for symbol, isin in isin_by_symbol.items() if isin]
    clients = [client] if client is not None else [AmfFilingsClient() for _ in range(workers)]

    def discover(item: tuple[str, str]) -> tuple[str, dict[str, Any] | None]:
        symbol, isin = item
        try:
            return symbol, clients[hash(symbol) % len(clients)].annual_report(isin)
        except requests.RequestException:
            return symbol, None

    discovered: list[tuple[str, dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed(pool.submit(discover, item) for item in candidates):
            symbol, record = future.result()
            if record:
                discovered.append((symbol, record))

    def archive(item: tuple[str, dict[str, Any]]) -> tuple[str, bool]:
        symbol, record = item
        try:
            filing_date = _parse_datetime_date(record.get("informationdeposee_inf_dat_emt"))
            source_url = str(record["url_de_recuperation"])
            if filing_date is None:
                return symbol, False
            accession = f"AMF-{record.get('uin_idt_uin') or _safe_accession(source_url)}"
            with Session(get_engine(database_url)) as session:
                if session.scalar(
                    select(FinancialReport.id).where(
                        FinancialReport.symbol == symbol,
                        FinancialReport.accession_number == accession,
                    )
                ):
                    return symbol, True
            content, suffix = AmfFilingsClient().download(record)
            filing = Filing(
                symbol=symbol,
                cik="",
                accession_number=accession,
                form="AMF-ANNUAL",
                filing_date=filing_date,
                period_end=None,
                primary_document=record.get("fichierdecontenu_inf_fic_nom") or source_url.rsplit("/", 1)[-1],
                source_url=source_url,
            )
            archive_filing(filing, content, suffix, output_dir, database_url)
            return symbol, True
        except (requests.RequestException, OSError, ValueError):
            return symbol, False

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed(pool.submit(archive, item) for item in discovered):
            symbol, success = future.result()
            result[symbol] = int(success)
    return result


def _parse_datetime_date(value: str | None) -> date | None:
    return _parse_date(value[:10] if value else None)


def _safe_accession(source_url: str) -> str:
    return Path(urlparse(source_url).path).stem or hashlib.sha256(source_url.encode()).hexdigest()[:16]


def _compact_html_text(content: bytes) -> str:
    text = content.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip() + "\n"


def _amf_record_priority(record: dict[str, Any]) -> tuple[bool, str]:
    title = str(record.get("informationdeposee_inf_tit_inf") or "").lower()
    announcement = "availability" in title or "mise a disposition" in title or "mise à disposition" in title
    return (not announcement, record.get("informationdeposee_inf_dat_emt") or "")
