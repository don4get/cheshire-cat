# -*- coding: utf-8 -*-
"""
history.py module containing :class:`~cheshire-cat.history.py.<ClassName>` class.
"""

from tqdm import tqdm
from sqlalchemy import create_engine
import pandas as pd
import yahooquery as yq


def get_ticker(ticker):
    yq_ticker: yq.Ticker = yq.Ticker(ticker)
    hist_df = yq_ticker.history("max", "1d")
    splitted_index_df = hist_df.index.to_frame()
    hist_df = pd.concat([hist_df, splitted_index_df], axis=1)

    return hist_df


def get_history():
    engine = create_engine("mysql+pymysql://cat:meow@localhost/cheshire-cat-db")
    ticker_names = pd.read_csv("tickers/tickers_stockanalysis.csv")
    ticker_names = [v[0] for v in ticker_names.values]

    for t in tqdm(ticker_names):
        ticker_df = get_ticker(t)
        if ticker_df is None:
            print(f"{t} went wrong.")
            continue
        with engine.begin() as connection:
            ticker_df.to_sql("values", con=connection, if_exists="append", index=False)


def get_history_from_sql(symbol):
    engine = create_engine("mysql+pymysql://cat:meow@localhost/cheshire-cat-db")
    with engine.begin() as connection:
        req = f"SELECT * FROM history WHERE symbol= '{symbol}';"
        df = pd.read_sql_query(req, connection)

    return df


if __name__ == "__main__":
    # get_history()
    df = get_history_from_sql("MSFT")
    print(df)
