import yfinance as yf
from tickers.get_tickers import *

def main():

    df = yf.download("AMZN MSFT", start="2019-01-01", end="2020-01-01",
                     group_by="ticker")
    print(df)
    print(df.AMZN)

    amazon = yf.Ticker("AMZN")
    print(amazon.info.keys())
    print(amazon.history(period="max"))


    list_of_tickers = get_tickers()
    print(list_of_tickers)


if __name__ == '__main__':
    main()
