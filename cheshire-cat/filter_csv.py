import pandas as pd


def filter_csv(filename):
    df = pd.read_csv(filename)

    df = keep_companies_with_safe_metrics(df)

    df.dropna(axis=1, how="all", thresh=None, subset=None, inplace=True)
    df = df.sort_values(by=["symbol"])

    df.to_csv("data/metrics/filtered_metrics_stockanalysis.csv")

    return df


def keep_companies_with_safe_metrics(df):
    df = df[df.shortRatio < 3]  # https://www.fool.com/knowledge-center/what-is-a-short-ratio.aspx
    df = df[df.pegRatio < 1.5]  # < 1 https://www.investopedia.com/terms/p/pegratio.asp
    df = df[
        df.payoutRatio < 0.6]  # http://www.objectifrente.com/actions/comprendre-et-utiliser-le-payout-ratio-comme-critere-dinvestissement
    df = df[
        df.debtToEquity < 200]  # https://www.investopedia.com/terms/d/debtequityratio.asp#:~:text=%2FE)%20Ratio%3F-,The%20debt%2Dto%2Dequity%20(D%2FE)%20ratio,metric%20used%20in%20corporate%20finance.
    return df


if __name__ == "__main__":
    filter_csv("../data/metrics/metrics_stockanalysis.csv")
