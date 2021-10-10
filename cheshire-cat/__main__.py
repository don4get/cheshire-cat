import yfinance as yf
import pandas as pd
pd.options.plotting.backend = "plotly"

import plotly.graph_objects as go

from tickers.get_tickers import *

from logger import write_data_to_hdf5
from param import Param


def main():
    # Import parameters
    param = Param()

    list_of_tickers = get_biggest_n_tickers(100)
    # print(list_of_tickers)

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
    df = tickers_df.set_index('symbol')
    # print(df.keys())
    cell_values = df.values.tolist()
    cell_values.insert(0, df.columns.tolist())
    # print(cell_values)

    df.to_csv("fundamentals.csv")

    fig = go.Figure(data=[go.Table(
            header=dict(values=[""]+list(df.T.columns),
                        fill_color='paleturquoise',
                        align='left',
                        ),
            cells=dict(values=cell_values,
                       fill_color='lavender',
                       align='left'))
    ])

    fig.show()
    # Log data
    # write_data_to_hdf5(tickers_df, param.exp_name)

if __name__ == '__main__':
    main()
