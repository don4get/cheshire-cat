import yfinance as yf
from tickers.get_tickers import *

from logger import write_data_to_hdf5
from param import Param


def main():
    # Import parameters
    param = Param()

    # Download data
    df = yf.download("AMZN MSFT", start="2019-01-01", end="2020-01-01",
                     group_by="ticker")

    # Analyze data
    print(df)
    print(df.AMZN)

    amazon = yf.Ticker("AMZN")
    print(amazon.info.keys())
    print(amazon.history(period="max"))

    list_of_tickers = get_tickers()
    print(list_of_tickers)

    # Log data
    write_data_to_hdf5(df, param.exp_name)


if __name__ == '__main__':
    main()
