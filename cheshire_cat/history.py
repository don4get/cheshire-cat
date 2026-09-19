"""Backward-compatible entry points for historical price storage."""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Price, create_schema, get_engine
from .market_data import YFinanceProvider, ingest_history


def get_ticker(ticker: str) -> pd.DataFrame:
    """Fetch one ticker without writing it to the database."""

    return YFinanceProvider().history(ticker, None, None, "1d").reset_index()


def get_history(
    symbols: list[str] | None = None,
    start: str | date | None = None,
    end: str | date | None = None,
    database_url: str | None = None,
):
    """Download and store history; symbols default to the bundled ticker file."""

    if symbols is None:
        ticker_file = "cheshire_cat/tickers/tickers_stockanalysis.csv"
        symbols = pd.read_csv(ticker_file).iloc[:, 0].dropna().tolist()
    create_schema(database_url)
    return ingest_history(symbols, start, end, database_url=database_url)


def get_history_from_sql(symbol: str, database_url: str | None = None) -> pd.DataFrame:
    engine = get_engine(database_url)
    with Session(engine) as session:
        rows = session.scalars(
            select(Price).where(Price.symbol == symbol.upper()).order_by(Price.date)
        ).all()
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


if __name__ == "__main__":
    print(get_history_from_sql("MSFT"))
