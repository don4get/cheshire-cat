from param import Param
from tickers.get_tickers import *
from tqdm import tqdm
from multiprocessing import Pool
import yfinance as yf

pd.options.plotting.backend = "plotly"


def get_ticker(ticker):
    y_ticker: yf.Ticker = yf.Ticker(ticker)
    return pd.DataFrame.from_dict(y_ticker.info, orient='index')


def get_metrics(output_filepath):
    param = Param()
    # ticker_names = get_tickers()
    ticker_names = pd.read_csv('cheshire-cat/tickers/tickers_stockanalysis.csv')
    ticker_names = [v[0] for v in ticker_names.values]
    print(ticker_names)
    with Pool(processes=param.n_processes) as p:
        tickers = p.map(get_ticker, tqdm(ticker_names))
    tickers_df = pd.concat(tickers, axis=1)
    tickers_df = tickers_df.T.set_index('symbol')
    tickers_df.to_csv(output_filepath)
