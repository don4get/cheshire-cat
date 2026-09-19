"""Portfolio accounting used by the dashboard and backtester."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class Trade:
    symbol: str
    trade_date: date
    quantity: float
    price: float
    fees: float = 0.0


@dataclass
class Portfolio:
    name: str = "default"
    cash: float = 0.0
    positions: dict[str, float] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)

    def trade(self, symbol: str, quantity: float, price: float, trade_date: date, fees: float = 0.0) -> None:
        """Apply a buy (positive quantity) or sell (negative quantity)."""

        symbol = symbol.upper()
        quantity = float(quantity)
        cost = quantity * float(price) + float(fees)
        if quantity < 0 and self.positions.get(symbol, 0.0) + quantity < -1e-9:
            raise ValueError(f"Cannot sell more {symbol} than the portfolio holds")
        if quantity > 0 and cost > self.cash + 1e-9:
            raise ValueError("Insufficient cash for trade")
        self.cash -= cost
        self.positions[symbol] = self.positions.get(symbol, 0.0) + quantity
        if abs(self.positions[symbol]) < 1e-9:
            del self.positions[symbol]
        self.trades.append(Trade(symbol, trade_date, quantity, float(price), float(fees)))

    def value(self, prices: dict[str, float]) -> float:
        return self.cash + sum(quantity * prices.get(symbol, 0.0) for symbol, quantity in self.positions.items())

    def snapshot(self, prices: dict[str, float], as_of: date) -> dict[str, object]:
        return {
            "date": as_of,
            "portfolio": self.name,
            "cash": self.cash,
            "market_value": sum(qty * prices.get(symbol, 0.0) for symbol, qty in self.positions.items()),
            "value": self.value(prices),
        }


def portfolio_curve(
    trades: list[Trade],
    prices: pd.DataFrame,
    initial_cash: float,
) -> pd.DataFrame:
    """Replay trades and return a daily equity curve.

    ``prices`` may be long-form (symbol/date/adj_close) or a date-indexed wide
    frame. Trade cash and position changes are applied on their trade date.
    """

    if prices.empty:
        return pd.DataFrame(columns=["date", "cash", "market_value", "value"])
    frame = _wide_prices(prices)
    portfolio = Portfolio(cash=float(initial_cash))
    trades_by_day: dict[pd.Timestamp, list[Trade]] = {}
    for trade in trades:
        trades_by_day.setdefault(pd.Timestamp(trade.trade_date), []).append(trade)
    rows = []
    for timestamp, row in frame.sort_index().iterrows():
        for trade in trades_by_day.get(pd.Timestamp(timestamp), []):
            portfolio.trade(trade.symbol, trade.quantity, row.get(trade.symbol, 0.0), trade.trade_date, trade.fees)
        rows.append(portfolio.snapshot(row.dropna().to_dict(), timestamp.date()))
    return pd.DataFrame(rows).set_index("date")


def _wide_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if {"date", "symbol"}.issubset(prices.columns):
        value_column = "adj_close" if "adj_close" in prices.columns else "close"
        return prices.pivot_table(index="date", columns="symbol", values=value_column, aggfunc="last")
    result = prices.copy()
    result.index = pd.to_datetime(result.index).date
    return result
