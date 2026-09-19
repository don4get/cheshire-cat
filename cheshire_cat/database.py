"""SQLAlchemy schema and small persistence helpers.

PostgreSQL is the production database. SQLite is intentionally supported too so
the ingestion and backtesting code can be tested or demonstrated offline.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
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
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
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


def get_engine(database_url: str | None = None):
    """Create an engine for the configured database URL."""

    return create_engine(database_url or settings.database_url, future=True)


def create_schema(database_url: str | None = None) -> None:
    Base.metadata.create_all(get_engine(database_url))


def upsert_prices(session: Session, rows: list[dict[str, Any]]) -> int:
    """Insert prices idempotently, updating a symbol/date row when it exists."""

    count = 0
    for row in rows:
        symbol = str(row["symbol"]).upper()
        price_date = row["date"]
        existing = session.scalar(
            select(Price).where(Price.symbol == symbol, Price.date == price_date)
        )
        values = {k: v for k, v in row.items() if k not in {"symbol", "date"}}
        if existing is None:
            session.add(Price(symbol=symbol, date=price_date, **values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        count += 1
    session.commit()
    return count


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
