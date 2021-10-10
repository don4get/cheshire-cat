import yfinance as yf
import pandas as pd
pd.options.plotting.backend = "plotly"

from tickers.get_tickers import *

from logger import write_data_to_hdf5
from param import Param


def main():
    # Import parameters
    param = Param()

    list_of_tickers = get_biggest_n_tickers(2)
    print(list_of_tickers)

    tickers_df = None

    for ticker in list_of_tickers:
        y_ticker: yf.Ticker = yf.Ticker(ticker)
        if tickers_df is None:
            tickers_df = pd.DataFrame.from_dict(y_ticker.info, orient='index')
            # print(tickers_df)
        else:
            df = pd.DataFrame.from_dict(y_ticker.info, orient='index')
            frames = [tickers_df, df]
            tickers_df = pd.concat(frames, axis=1)

    tickers_df = tickers_df.T
    tickers_df = tickers_df.set_index('symbol')
    print(tickers_df)

    # fig = infos_df.plot.barh()
    # fig.show()

    # Log data
    write_data_to_hdf5(tickers_df, param.exp_name)

if __name__ == '__main__':
    main()
