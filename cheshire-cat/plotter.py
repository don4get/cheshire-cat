import dtale

def plot_fundamentals(df):
    df = df.sort_values(by=["beta"])
    d = dtale.show(df, subprocess=False)