"""Interactive Dash dashboard for prices, fundamentals, filings, and portfolios."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import FinancialReport, FundamentalFact, PortfolioTransaction, Price, get_engine
from .portfolio import Trade, portfolio_curve


def dashboard_data(database_url: str | None = None, symbol: str | None = None) -> dict[str, pd.DataFrame]:
    """Load the datasets needed by the dashboard from PostgreSQL."""

    engine = get_engine(database_url)
    with Session(engine) as session:
        price_query = select(Price).order_by(Price.date)
        report_query = select(FinancialReport).order_by(FinancialReport.filing_date.desc())
        fact_query = select(FundamentalFact).order_by(FundamentalFact.period_end.desc())
        transaction_query = select(PortfolioTransaction).order_by(PortfolioTransaction.trade_date)
        if symbol:
            symbol = symbol.upper()
            price_query = price_query.where(Price.symbol == symbol)
            report_query = report_query.where(FinancialReport.symbol == symbol)
            fact_query = fact_query.where(FundamentalFact.symbol == symbol)
        price_rows = session.scalars(price_query).all()
        report_rows = session.scalars(report_query).all()
        fact_rows = session.scalars(fact_query).all()
        transaction_rows = session.scalars(transaction_query).all()
    return {
        "prices": pd.DataFrame(
            [{"date": p.date, "symbol": p.symbol, "close": p.close, "adj_close": p.adj_close, "volume": p.volume} for p in price_rows],
            columns=["date", "symbol", "close", "adj_close", "volume"],
        ),
        "reports": pd.DataFrame(
            [{"symbol": r.symbol, "form": r.form, "filing_date": r.filing_date, "period_end": r.period_end, "markdown_path": r.markdown_path} for r in report_rows],
            columns=["symbol", "form", "filing_date", "period_end", "markdown_path"],
        ),
        "fundamentals": pd.DataFrame(
            [{"symbol": f.symbol, "concept": f.concept, "unit": f.unit, "period_end": f.period_end, "filed": f.filed, "form": f.form, "value": f.value} for f in fact_rows],
            columns=["symbol", "concept", "unit", "period_end", "filed", "form", "value"],
        ),
        "transactions": pd.DataFrame(
            [{"portfolio": t.portfolio, "symbol": t.symbol, "trade_date": t.trade_date, "quantity": t.quantity, "price": t.price, "fees": t.fees} for t in transaction_rows],
            columns=["portfolio", "symbol", "trade_date", "quantity", "price", "fees"],
        ),
    }


def fundamental_metrics(prices: pd.DataFrame) -> pd.DataFrame:
    """Calculate transparent market metrics when a fundamentals feed is absent."""

    if prices.empty:
        return pd.DataFrame(columns=["symbol", "last_price", "return_1y", "volatility", "high_1y", "low_1y"])
    prices = prices.copy()
    prices["date"] = pd.to_datetime(prices["date"])
    rows = []
    for symbol, group in prices.groupby("symbol"):
        series = group.sort_values("date")["adj_close"].fillna(group["close"])
        returns = series.pct_change().dropna()
        window = series.tail(252)
        rows.append(
            {
                "symbol": symbol,
                "last_price": float(series.iloc[-1]),
                "return_1y": float(window.iloc[-1] / window.iloc[0] - 1) if len(window) > 1 else None,
                "volatility": float(returns.tail(252).std() * (252**0.5)) if len(returns) > 1 else None,
                "high_1y": float(window.max()),
                "low_1y": float(window.min()),
            }
        )
    return pd.DataFrame(rows)


def latest_fundamentals(facts: pd.DataFrame) -> pd.DataFrame:
    """Return one latest observation per XBRL concept/unit for the selected stock."""

    if facts.empty:
        return facts
    ordered = facts.sort_values(["concept", "unit", "period_end", "filed"])
    return ordered.drop_duplicates(["symbol", "concept", "unit"], keep="last")


def portfolio_valuation(data: dict[str, pd.DataFrame], initial_cash: float = 100_000.0) -> pd.DataFrame:
    """Replay persisted trades against stored prices for the portfolio chart."""

    transactions = data["transactions"]
    if transactions.empty:
        return pd.DataFrame()
    trades = [
        Trade(row.symbol, pd.Timestamp(row.trade_date).date(), row.quantity, row.price, row.fees)
        for row in transactions.itertuples()
    ]
    return portfolio_curve(trades, data["prices"], initial_cash)


def create_app(database_url: str | None = None):
    """Create the Dash application; optional dependencies are loaded only here."""

    try:
        import plotly.express as px
        from dash import Dash, Input, Output, State, dash_table, dcc, html
    except ImportError as exc:
        raise RuntimeError("Install dashboard support with `uv sync --extra dashboard`.") from exc

    app = Dash(__name__, title="Cheshire Cat — Stock Research")
    initial = dashboard_data(database_url)
    symbols = sorted(initial["prices"]["symbol"].dropna().unique().tolist()) if not initial["prices"].empty else []
    app.layout = html.Div(
        [
            html.H1("Cheshire Cat stock research"),
            html.P("Prices, filings, and portfolio data from the configured PostgreSQL database."),
            dcc.Dropdown(symbols, symbols[0] if symbols else None, id="symbol", clearable=False),
            dcc.Graph(id="price-chart"),
            html.H2("Fundamental and market metrics"),
            dash_table.DataTable(id="metrics-table", page_size=20, sort_action="native"),
            html.H2("Latest SEC XBRL fundamentals"),
            dash_table.DataTable(id="fundamentals-table", page_size=20, sort_action="native"),
            html.H2("Annual and quarterly publications"),
            dash_table.DataTable(id="reports-table", page_size=10, sort_action="native"),
            html.H2("Portfolio"),
            html.P("Enter a positive quantity to buy or a negative quantity to sell."),
            dcc.Input(id="portfolio-name", value="default", type="text", placeholder="Portfolio"),
            dcc.Input(id="trade-symbol", type="text", placeholder="Symbol"),
            dcc.Input(id="trade-quantity", type="number", placeholder="Quantity"),
            dcc.Input(id="trade-price", type="number", placeholder="Execution price"),
            dcc.Input(id="trade-date", type="text", value=str(datetime.now(UTC).date()), placeholder="YYYY-MM-DD"),
            html.Button("Record trade", id="trade-submit", n_clicks=0),
            html.Div(id="trade-status"),
            dcc.Graph(id="portfolio-chart"),
        ],
        style={"maxWidth": "1400px", "margin": "2rem auto", "fontFamily": "system-ui"},
    )

    @app.callback(
        Output("price-chart", "figure"),
        Output("metrics-table", "data"),
        Output("metrics-table", "columns"),
        Output("fundamentals-table", "data"),
        Output("fundamentals-table", "columns"),
        Output("reports-table", "data"),
        Output("reports-table", "columns"),
        Output("portfolio-chart", "figure"),
        Input("symbol", "value"),
        Input("trade-submit", "n_clicks"),
    )
    def update(symbol: str | None):
        data = dashboard_data(database_url, symbol)
        prices = data["prices"]
        figure = px.line(prices, x="date", y="adj_close", color="symbol", title=f"{symbol or 'All symbols'} price history")
        metrics = fundamental_metrics(prices)
        reports = data["reports"]
        fundamentals = latest_fundamentals(data["fundamentals"])
        valuation = portfolio_valuation(dashboard_data(database_url, None))
        portfolio_figure = px.line(valuation.reset_index(), x="date", y="value", title="Portfolio value") if not valuation.empty else px.line(title="Portfolio value")
        return (
            figure,
            metrics.to_dict("records"),
            [{"name": column, "id": column} for column in metrics.columns],
            fundamentals.to_dict("records"),
            [{"name": column, "id": column} for column in fundamentals.columns],
            reports.to_dict("records"),
            [{"name": column, "id": column} for column in reports.columns],
            portfolio_figure,
        )

    @app.callback(
        Output("trade-status", "children"),
        Input("trade-submit", "n_clicks"),
        State("portfolio-name", "value"),
        State("trade-symbol", "value"),
        State("trade-quantity", "value"),
        State("trade-price", "value"),
        State("trade-date", "value"),
        prevent_initial_call=True,
    )
    def record_trade(_n_clicks, portfolio, symbol, quantity, price, trade_date):
        if not all((portfolio, symbol, quantity, price, trade_date)):
            return "Portfolio, symbol, quantity, price, and date are required."
        try:
            trade = PortfolioTransaction(
                portfolio=portfolio,
                symbol=symbol.upper(),
                trade_date=date.fromisoformat(trade_date),
                quantity=float(quantity),
                price=float(price),
                fees=0.0,
            )
            with Session(get_engine(database_url)) as session:
                session.add(trade)
                session.commit()
            return f"Recorded {quantity:g} {symbol.upper()} at {price:g}."
        except (TypeError, ValueError) as exc:
            return f"Trade not recorded: {exc}"

    return app


def run_dashboard(database_url: str | None = None, host: str = "127.0.0.1", port: int = 8050, debug: bool = False) -> None:
    app = create_app(database_url)
    app.run(host=host, port=port, debug=debug)
