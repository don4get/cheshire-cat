import pandas as pd


def filter_metrics(filename):
    df = pd.read_csv(filename)
    df = keep_companies_with_safe_metrics(df)

    df.dropna(axis=1, how="all", thresh=None, subset=None, inplace=True)
    df = df.sort_values(by=["symbol"])

    df.to_csv("../data/metrics/filtered_metrics_stockanalysis.csv")

    df = reorder_columns(df)

    return df


def keep_companies_with_safe_metrics(df):
    df = df[df.shortRatio < 3]  # https://www.fool.com/knowledge-center/what-is-a-short-ratio.aspx
    df = df[df.pegRatio < 1.5]  # < 1 https://www.investopedia.com/terms/p/pegratio.asp
    df = df[
        df.payoutRatio < 0.6]  # http://www.objectifrente.com/actions/comprendre-et-utiliser-le-payout-ratio-comme-critere-dinvestissement
    df = df[
        df.debtToEquity < 200]  # https://www.investopedia.com/terms/d/debtequityratio.asp#:~:text=%2FE)%20Ratio%3F-,The%20debt%2Dto%2Dequity%20(D%2FE)%20ratio,metric%20used%20in%20corporate%20finance.
    return df

def reorder_columns(df):
    # move_column
    cols = list(df.columns)
    cols.insert(126, cols.pop(4))
    df = df.reindex(cols, axis=1)

    # delete_column
    df = df.drop('address2', axis=1)

    # delete_column
    df = df.drop('uuid', axis=1)

    # delete_column
    df = df.drop('companyOfficers', axis=1)

    # delete_column
    df = df.drop('maxAge', axis=1)

    # delete_column
    df = df.drop('tradeable', axis=1)

    # delete_column
    df = df.drop('fax', axis=1)

    # delete_column
    df = df.drop('messageBoardId', axis=1)

    # delete_column
    df = df.drop('quoteType', axis=1)

    # delete_column
    df = df.drop('gmtOffSetMilliseconds', axis=1)

    # delete_column
    df = df.drop('isEsgPopulated', axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(0, cols.pop(27))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(0, cols.pop(41))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(44))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(44))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(43))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(42))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(41))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(0, cols.pop(2))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(3))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(0, cols.pop(3))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(9))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(8))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(7))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(7))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(6))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(6))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(4))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(13))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(0, cols.pop(31))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(0, cols.pop(53))
    df = df.reindex(cols, axis=1)

    # move_column
    cols = list(df.columns)
    cols.insert(116, cols.pop(101))
    df = df.reindex(cols, axis=1)

    # sort_column
    df = df.sort_values('recommendationMean', ascending=True, kind='mergesort')

    return df


if __name__ == "__main__":
    filter_metrics("../data/metrics/metrics_stockanalysis.csv")
