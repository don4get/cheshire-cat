"""SQLAlchemy schema and small persistence helpers.

PostgreSQL is the production database. SQLite is intentionally supported too so
the ingestion and backtesting code can be tested or demonstrated offline.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .config import settings


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_prices_symbol_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    adj_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="yfinance")
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class FinancialReport(Base):
    __tablename__ = "financial_reports"
    __table_args__ = (
        UniqueConstraint("symbol", "accession_number", name="uq_reports_symbol_accession"),
        Index("ix_reports_symbol_filing_date", "symbol", "filing_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    cik: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    accession_number: Mapped[str] = mapped_column(String(32), index=True)
    form: Mapped[str] = mapped_column(String(16), index=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    original_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class FundamentalFact(Base):
    __tablename__ = "fundamental_facts"
    __table_args__ = (
        UniqueConstraint(
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
            name="uq_fundamental_fact_observation",
        ),
        Index("ix_facts_symbol_period_filed", "symbol", "period_end", "filed"),
        Index("ix_facts_symbol_concept_period", "symbol", "concept", "period_end", "filed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    cik: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    taxonomy: Mapped[str] = mapped_column(String(32))
    concept: Mapped[str] = mapped_column(Text, index=True)
    unit: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    # ``filed`` is retained for compatibility with the first schema. It is a
    # reporting/source field, not a promise that the fact was usable at a
    # particular historical decision time.
    filed: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    form: Mapped[str] = mapped_column(String(16), index=True)
    frame: Mapped[str | None] = mapped_column(String(32), nullable=True)
    value: Mapped[float] = mapped_column(Float)
    source_url: Mapped[str] = mapped_column(Text)
    source_document_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(256), nullable=True)
    context_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    available_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    available_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    availability_status: Mapped[str] = mapped_column(
        String(24), default="unknown", nullable=False, index=True
    )
    statement_kind: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class PortfolioTransaction(Base):
    __tablename__ = "portfolio_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio: Mapped[str] = mapped_column(String(128), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    fees: Mapped[float] = mapped_column(Float, default=0.0)


class TickerSymbol(Base):
    """A symbol in the tracked Nasdaq/PEA universe."""

    __tablename__ = "ticker_universe"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    isin: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    pea_eligible: Mapped[bool | None] = mapped_column(default=None, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(128))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class UniverseSnapshot(Base):
    """Immutable, versioned investable-universe materialization."""

    __tablename__ = "universe_snapshots"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    market: Mapped[str] = mapped_column(String(32), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    version: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(256))
    historical_status: Mapped[str] = mapped_column(String(32))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class UniverseMembership(Base):
    """One symbol's as-of membership and eligibility evidence."""

    __tablename__ = "universe_memberships"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "symbol", name="uq_universe_membership_snapshot_symbol"),
        Index("ix_universe_membership_symbol_asof", "symbol", "as_of"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(128), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    exchange: Mapped[str] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    isin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pea_eligible: Mapped[bool | None] = mapped_column(nullable=True)
    membership_status: Mapped[str] = mapped_column(String(24))
    historical_status: Mapped[str] = mapped_column(String(32))
    price_eligible: Mapped[bool | None] = mapped_column(nullable=True)
    liquidity_eligible: Mapped[bool | None] = mapped_column(nullable=True)
    completeness_status: Mapped[str] = mapped_column(String(24), default="unknown")
    price_observation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    price_freshness_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    median_dollar_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    fundamental_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(256))


class IngestionState(Base):
    """Per-symbol cursor used to spread a large universe over many runs."""

    __tablename__ = "ingestion_state"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_due_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    last_price_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class FundamentalIngestionState(Base):
    """Resumable status for a source/symbol fundamentals ingestion attempt."""

    __tablename__ = "fundamental_ingestion_state"
    __table_args__ = (
        UniqueConstraint("source", "symbol", name="uq_fundamental_ingestion_source_symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    rows_ingested: Mapped[int] = mapped_column(Integer, default=0)
    attempted_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class FundamentalFeatureSnapshot(Base):
    """Immutable cache of one reproducible decision-date feature materialization."""

    __tablename__ = "fundamental_feature_snapshots"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(128), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    feature_version: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ResearchRun(Base):
    """Durable experiment with its choice persisted before holdout evaluation."""

    __tablename__ = "research_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    market: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    progress: Mapped[str] = mapped_column(Text)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    selection: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class FundamentalResearchRun(Base):
    """Persisted matched fundamentals experiment; reports are append-by-run."""

    __tablename__ = "fundamental_research_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    market: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class ResearchChallenger(Base):
    """Append-only-by-version challenger experiments alongside frozen incumbents."""

    __tablename__ = "research_challengers"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    progress: Mapped[str] = mapped_column(Text, default="Queued")
    trials: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    selection: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class ResearchValidationAudit(Base):
    """Versioned diagnostics; never overwrite the original experiment."""

    __tablename__ = "research_validation_audits"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    progress: Mapped[str] = mapped_column(Text, default="Queued")
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class ResearchPortfolioTimeline(Base):
    """A separately cached replay of a research run's frozen top three rules."""

    __tablename__ = "research_portfolio_timelines"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchPortfolioSnapshot(Base):
    """One indexed date per row, so moving the slider reads only that date."""

    __tablename__ = "research_portfolio_snapshots"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    portfolios: Mapped[list[dict[str, Any]]] = mapped_column(JSON)


@lru_cache(maxsize=8)
def get_engine(database_url: str | None = None):
    """Create an engine for the configured database URL."""

    return create_engine(
        database_url or settings.database_url,
        future=True,
        pool_pre_ping=True,
    )


def create_schema(database_url: str | None = None) -> None:
    engine = get_engine(database_url)
    if engine.dialect.name == "sqlite":
        _migrate_sqlite_fundamental_facts(engine)
        _migrate_sqlite_legacy_columns(engine)
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            for column, definition in (
                ("period_start", "DATE"),
                ("filed", "DATE"),
                ("currency", "VARCHAR(16)"),
                ("source_document_id", "VARCHAR(256)"),
                ("source_version", "VARCHAR(256)"),
                ("context_ref", "VARCHAR(512)"),
                ("available_on", "DATE"),
                ("available_at", "TIMESTAMP"),
                ("availability_status", "VARCHAR(24) NOT NULL DEFAULT 'unknown'"),
                ("statement_kind", "VARCHAR(16) NOT NULL DEFAULT 'unknown'"),
                ("duration_days", "INTEGER"),
                ("retrieved_at", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
            ):
                connection.execute(
                    text(
                        f"ALTER TABLE fundamental_facts ADD COLUMN IF NOT EXISTS "
                        f"{column} {definition}"
                    )
                )
            connection.execute(text("ALTER TABLE fundamental_facts ALTER COLUMN filed DROP NOT NULL"))
            connection.execute(
                text(
                    "ALTER TABLE fundamental_facts DROP CONSTRAINT IF EXISTS "
                    "uq_fundamental_fact_observation"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE fundamental_facts ADD CONSTRAINT "
                    "uq_fundamental_fact_observation UNIQUE "
                    "(symbol, taxonomy, concept, unit, period_start, period_end, form, "
                    "source_document_id, source_version, context_ref, currency)"
                )
            )
            connection.execute(text("ALTER TABLE prices ALTER COLUMN volume TYPE BIGINT"))
            connection.execute(text("ALTER TABLE ticker_universe ALTER COLUMN pea_eligible DROP NOT NULL"))
            connection.execute(text("ALTER TABLE fundamental_facts ALTER COLUMN concept TYPE TEXT"))
            connection.execute(text("ALTER TABLE ticker_universe ADD COLUMN IF NOT EXISTS sector VARCHAR(128)"))
            for column, definition in (
                ("price_observation_date", "DATE"),
                ("price_freshness_days", "INTEGER"),
                ("median_dollar_volume", "DOUBLE PRECISION"),
                ("fundamental_coverage", "DOUBLE PRECISION"),
            ):
                connection.execute(
                    text(
                        f"ALTER TABLE universe_memberships ADD COLUMN IF NOT EXISTS "
                        f"{column} {definition}"
                    )
                )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_facts_symbol_period_filed "
                    "ON fundamental_facts (symbol, period_end, filed)"
                )
            )


def _migrate_sqlite_fundamental_facts(engine) -> None:
    """Rebuild an old SQLite fact table without losing existing observations.

    SQLite cannot drop or replace an inline unique constraint. A small table
    rebuild is therefore the least surprising migration path for local test and
    demo databases. New columns remain explicitly nullable/defaulted so old
    rows are preserved but remain unverified for historical use.
    """

    required = {
        "source_document_id",
        "source_version",
        "context_ref",
        "currency",
        "available_on",
        "available_at",
        "availability_status",
        "statement_kind",
        "duration_days",
        "retrieved_at",
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        if not inspector.has_table("fundamental_facts"):
            return
        columns = [column["name"] for column in inspector.get_columns("fundamental_facts")]
        if required.issubset(columns) and "period_start" in columns:
            return
        legacy = "fundamental_facts_legacy_migration"
        connection.execute(text(f"DROP TABLE IF EXISTS {legacy}"))
        connection.execute(text("ALTER TABLE fundamental_facts RENAME TO " + legacy))
        FundamentalFact.__table__.create(connection)
        new_columns = [column.name for column in FundamentalFact.__table__.columns]
        target_columns: list[str] = []
        select_expressions: list[str] = []
        defaults = {
            "currency": "NULL",
            "availability_status": "'unknown'",
            "statement_kind": "'unknown'",
            "retrieved_at": "CURRENT_TIMESTAMP",
        }
        for column in new_columns:
            if column in columns:
                target_columns.append(column)
                select_expressions.append(column)
            elif column in defaults:
                target_columns.append(column)
                select_expressions.append(defaults[column])
        column_sql = ", ".join(target_columns)
        select_sql = ", ".join(select_expressions)
        connection.execute(
            text(
                f"INSERT INTO fundamental_facts ({column_sql}) "
                f"SELECT {select_sql} FROM {legacy}"
            )
        )
        connection.execute(text(f"DROP TABLE {legacy}"))


def _migrate_sqlite_legacy_columns(engine) -> None:
    """Add nullable columns that SQLite's create_all cannot retrofit."""

    with engine.begin() as connection:
        inspector = inspect(connection)
        if inspector.has_table("ticker_universe"):
            columns = {column["name"] for column in inspector.get_columns("ticker_universe")}
            if "sector" not in columns:
                connection.execute(text("ALTER TABLE ticker_universe ADD COLUMN sector VARCHAR(128)"))
        if inspector.has_table("universe_memberships"):
            columns = {column["name"] for column in inspector.get_columns("universe_memberships")}
            additions = {
                "price_observation_date": "DATE",
                "price_freshness_days": "INTEGER",
                "median_dollar_volume": "FLOAT",
                "fundamental_coverage": "FLOAT",
            }
            for column, definition in additions.items():
                if column not in columns:
                    connection.execute(
                        text(f"ALTER TABLE universe_memberships ADD COLUMN {column} {definition}")
                    )


def upsert_prices(session: Session, rows: list[dict[str, Any]]) -> int:
    """Insert prices idempotently, updating a symbol/date row when it exists."""

    if not rows:
        return 0
    values = [{**row, "symbol": str(row["symbol"]).upper()} for row in rows]
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        for row in values:
            existing = session.scalar(
                select(Price).where(Price.symbol == row["symbol"], Price.date == row["date"])
            )
            update = {key: value for key, value in row.items() if key not in {"symbol", "date"}}
            if existing is None:
                session.add(Price(**row))
            else:
                for key, value in update.items():
                    setattr(existing, key, value)
        session.commit()
        return len(values)

    statement = insert(Price).values(values)
    update = {
        key: getattr(statement.excluded, key)
        for key in values[0]
        if key not in {"symbol", "date"}
    }
    session.execute(
        statement.on_conflict_do_update(index_elements=["symbol", "date"], set_=update)
    )
    session.commit()
    return len(values)


def prices_as_frame(session: Session, symbols: list[str] | None = None):
    """Return stored prices as a normalized pandas DataFrame."""

    import pandas as pd

    query = select(Price).order_by(Price.symbol, Price.date)
    if symbols:
        query = query.where(Price.symbol.in_([s.upper() for s in symbols]))
    rows = session.scalars(query).all()
    return pd.DataFrame(
        [
            {
                "symbol": row.symbol,
                "date": row.date,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "adj_close": row.adj_close,
                "volume": row.volume,
            }
            for row in rows
        ]
    )
