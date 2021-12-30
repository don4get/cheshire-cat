# -*- coding: utf-8 -*-
"""
scaler.py module containing :class:`~cheshire-cat.scaler.py.<ClassName>` class.
"""

import pandas as pd
from pandas import DataFrame
from sqlalchemy import create_engine
from datetime import datetime

from cheshire_cat.history import get_history_from_sql
from cheshire_cat.kpis import get_kpis_from_sql


def compute_average_history_for_symbol(symbol, period=120):
    engine = create_engine("mysql+pymysql://cat:meow@localhost/cheshire-cat-db")

    history_df: DataFrame = get_history_from_sql(symbol)
    print(history_df)
    # with engine.begin() as connection:
    #     old_ih_df: DataFrame = pd.read_sql_table("improved_history", connection)

    kpis = get_kpis_from_sql(symbol)
    dates_to_keep = kpis.as_of_date

    history_df = history_df.set_index("date")
    history_df.truncate(before=datetime.fromisoformat("2017-01-01"), copy=False)
    history_df.rolling(period)
    history_df = history_df[dates_to_keep]

    print(history_df)


def compute_average_history():
    ticker_names = pd.read_csv("tickers/tickers_stockanalysis_small.csv")

    for t in ticker_names:
        compute_average_history_for_symbol(t)


if __name__ == "__main__":
    symbol = "MSFT"
    compute_average_history_for_symbol(symbol)
