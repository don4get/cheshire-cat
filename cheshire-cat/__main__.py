from metrics import get_metrics
from filter_csv import filter_csv
from plotter import plot_metrics
import os.path

metrics_filepath = "../data/metrics/metrics_stockanalysis.csv"


def main():
    # Create a csv file with the metrics of all tickers, if you don't have it yet
    if not os.path.isfile(metrics_filepath):
        get_metrics(metrics_filepath)

    # Filter the metrics to
    df = filter_csv(metrics_filepath)

    # Plot metrics
    plot_metrics(df)


if __name__ == '__main__':
    main()
