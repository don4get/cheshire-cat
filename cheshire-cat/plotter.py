import dtale


def plot_metrics(df):
    df = df.sort_values(by=["beta"])
    d = dtale.show(df, subprocess=False)
