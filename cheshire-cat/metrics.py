import logging
import warnings

from pandas import DataFrame

from param import Param
from tqdm import tqdm
from multiprocessing import Pool
from sqlalchemy import create_engine
import pandas as pd
import yahooquery as yq

from proxy import get_proxies
from utils import camel_to_snake
from kpis import Kpis
import random

pd.options.plotting.backend = "plotly"

proxies = get_proxies()


def get_ticker(ticker):
    # plist = random.sample(proxies, len(proxies))
    # pdict = {
    #     "http": "http://"+plist[0],
    #     "https": "http://"+plist[0]
    # }
    yq_ticker: yq.Ticker = yq.Ticker(ticker)  # proxies=pdict

    financial_df = yq_ticker.all_financial_data("a")
    if not isinstance(financial_df, DataFrame):
        print("Blacklisted...")
        return None
    financial_df["symbol"] = financial_df.index
    financial_df = financial_df.set_index("asOfDate")
    new_columns = {k: camel_to_snake(k) for k in financial_df.columns}
    financial_df = financial_df.rename(columns=new_columns)

    quotes_info = yq_ticker.quotes
    kpis = Kpis(ticker, financial_df, quotes_info)
    kpis_df = kpis.to_df()

    return kpis_df


def get_metrics(output_filepath):
    param = Param()
    # ticker_names = get_tickers()
    ticker_names = pd.read_csv("tickers/tickers_stockanalysis.csv")
    ticker_names = [v[0] for v in ticker_names.values]
    # print(ticker_names)
    # with Pool(processes=param.n_processes) as p:
    #     tickers = p.map(get_ticker, tqdm(ticker_names))

    # tickers = [t for t in tickers if t is not None]

    engine = create_engine("mysql+pymysql://cat:meow@localhost/cheshire-cat-db")

    try:
        with engine.begin() as connection:
            df_old = pd.read_sql_table("kpis", connection)
        already_computed_symbols = df_old.symbol.tolist()
        ticker_names = [t for t in ticker_names if t not in already_computed_symbols]
    except ValueError as e:
        logging.warning("Table kpis does not exist.")
        df_old = DataFrame()

    for t in tqdm(ticker_names):
        ticker_df = get_ticker(t)
        if ticker_df is None:
            print(f"{t} went wrong.")
            continue
        with engine.begin() as connection:
            try:
                df_old_symbol = df_old.loc[df_old.symbol == ticker_df.symbol[0]]
                if not df_old_symbol.empty:
                    ticker_df = pd.merge(df_old_symbol, ticker_df, how="outer")
                    req = f"""
                    DELETE FROM kpis 
                    WHERE symbol = '{ticker_df.symbol[0]}';
                    """
                    connection.execute(req)
            except ValueError as ve:
                warnings.warn("Table not found")
            finally:
                ticker_df.to_sql(
                    "kpis", con=connection, if_exists="append", index=False
                )
            # tickers.append(ticker_df)

    # tickers_df = pd.concat(tickers, axis=0)
    # tickers_df = tickers_df.T.set_index('symbol')
    # tickers_df.to_csv(output_filepath)


if __name__ == "__main__":
    metrics_filepath = "../data/metrics/metrics_stockanalysis_yq.csv"
    get_metrics(metrics_filepath)
