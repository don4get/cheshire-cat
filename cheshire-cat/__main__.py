from fundamentals import get_fundamentals
from filter_csv import filter_csv
from plotter import plot_fundamentals

def main():
    # get_fundamentals()

    df = filter_csv("../data/metrics/fundamentals_stockanalysis.csv")

    plot_fundamentals(df)

if __name__ == '__main__':
    main()
