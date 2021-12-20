from metrics import get_metrics
from filter import filter_metrics
from plotter import plot_metrics, plot_scatter

import os.path

metrics_filepath = "../data/metrics/metrics_stockanalysis.csv"


def main():
    # Create a csv file with the metrics of all tickers, if you don't have it yet
    if not os.path.isfile(metrics_filepath):
        get_metrics(metrics_filepath)

    # Filter the metrics to
    df = filter_metrics(metrics_filepath)

    plot_metrics(df, dtale_format=False)

    plot_scatter(df)

if __name__ == '__main__':
    main()
