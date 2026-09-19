"""SQLAlchemy schema and small persistence helpers.

PostgreSQL is the production database. SQLite is intentionally supported too so
the ingestion and backtesting code can be tested or demonstrated offline.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
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
            "period_end",
            "filed",
            "form",
            name="uq_fundamental_fact_observation",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    cik: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    taxonomy: Mapped[str] = mapped_column(String(32))
    concept: Mapped[str] = mapped_column(String(128), index=True)
    unit: Mapped[str] = mapped_column(String(32))
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    filed: Mapped[date] = mapped_column(Date, index=True)
    form: Mapped[str] = mapped_column(String(16), index=True)
    frame: Mapped[str | None] = mapped_column(String(32), nullable=True)
    value: Mapped[float] = mapped_column(Float)
    source_url: Mapped[str] = mapped_column(Text)


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
    pea_eligible: Mapped[bool | None] = mapped_column(default=None, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(128))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class IngestionState(Base):
    """Per-symbol cursor used to spread a large universe over many runs."""

    __tablename__ = "ingestion_state"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_due_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    last_price_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


def get_engine(database_url: str | None = None):
    """Create an engine for the configured database URL."""

    return create_engine(database_url or settings.database_url, future=True)


def create_schema(database_url: str | None = None) -> None:
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        from sqlalchemy import text

        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE prices ALTER COLUMN volume TYPE BIGINT"))
            connection.execute(text("ALTER TABLE ticker_universe ALTER COLUMN pea_eligible DROP NOT NULL"))


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
