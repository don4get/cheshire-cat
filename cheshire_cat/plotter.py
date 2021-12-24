import dtale
from pandasgui import show
import plotly.express as px


def plot_metrics(df, dtale_format=True):
    df = df.sort_values(by=["beta"])
    if dtale_format:
        d = dtale.show(df, subprocess=False)
    else:
        show(df)


def plot_scatter(df):
    fig = px.scatter(
        data_frame=df,
        x="symbol",
        y="beta",
        color="sector",
        symbol="recommendationKey",
        size=None,
        trendline=None,
        marginal_x=None,
        marginal_y=None,
        facet_row=None,
        facet_col="sector",
        render_mode="auto",
    )
    fig.update()
    show(fig)
