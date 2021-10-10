import yfinance as yf

def main():

    df = yf.download("AMZN MSFT", start="2019-01-01", end="2020-01-01",
                     group_by="ticker")
    print(df)
    print(df.AMZN)

    Amazon = yf.Ticker("AMZN")
    print(Amazon.info.keys())
    print(Amazon.history(period="max"))


if __name__ == '__main__':
    main()
