import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from tickers.get_tickers import *
from logger import write_data_to_hdf5
from param import Param
from tqdm import tqdm
from multiprocessing import Pool

pd.options.plotting.backend = "plotly"


def get_ticker(ticker):
    y_ticker: yf.Ticker = yf.Ticker(ticker)
    return pd.DataFrame.from_dict(y_ticker.info, orient='index')


def main():
    param = Param()

    ticker_names = get_tickers()
    with Pool(processes=param.n_processes) as p:
        tickers = p.map(get_ticker, tqdm(ticker_names))

    tickers_df = pd.concat(tickers, axis=1)
    tickers_df = tickers_df.T.set_index('symbol')
    tickers_df.to_csv("fundamentals.csv")


if __name__ == '__main__':
    main()
