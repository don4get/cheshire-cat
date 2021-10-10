# -*- coding: utf-8 -*-
"""
filter_csv.py module containing :class:`~cheshire-cat.filter_csv.py.<ClassName>` class.
"""

import pandas as pd

def filter_csv(filename):
    df = pd.read_csv(filename)

    df = df[df.shortRatio < 3]


    print(df)

if __name__ == "__main__":
    filter_csv("fundamentals.csv")
