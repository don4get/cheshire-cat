"""Leakage-safe historical investment-agent backtesting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd


class InvestmentAgent(Protocol):
    def weights(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Return one row per date and one column per symbol."""


@dataclass(frozen=True)
class StrategyConfig:
    fast_window: int = 50
    slow_window: int = 200
    transaction_cost: float = 0.001
    annualization: int = 252

    def __post_init__(self) -> None:
        if self.fast_window < 2 or self.slow_window <= self.fast_window:
            raise ValueError("slow_window must be greater than fast_window >= 2")
        if not 0 <= self.transaction_cost < 1:
            raise ValueError("transaction_cost must be between 0 and 1")


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    metrics: dict[str, float]
    benchmark_metrics: dict[str, float]
    weights: pd.DataFrame


class MovingAverageInvestmentAgent:
    """Long-only equal-weight agent with a delayed moving-average signal.

    Signals are shifted by one session before returns are applied, so a bar's
    close can never determine a position that earns that same bar's return.
    """

    def __init__(self, config: StrategyConfig | None = None):
        self.config = config or StrategyConfig()

    def weights(self, prices: pd.DataFrame) -> pd.DataFrame:
        close = _wide_prices(prices)
        fast = close.rolling(self.config.fast_window, min_periods=self.config.fast_window).mean()
        slow = close.rolling(self.config.slow_window, min_periods=self.config.slow_window).mean()
        active = (close > slow) & (fast > slow)
        weights = active.astype(float).div(active.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        return weights.shift(1).fillna(0.0)


def backtest(
    prices: pd.DataFrame,
    agent: InvestmentAgent | None = None,
    config: StrategyConfig | None = None,
) -> BacktestResult:
    """Backtest an agent and compare it with an equal-weight buy-and-hold baseline."""

    config = config or StrategyConfig()
    close = _wide_prices(prices).sort_index().ffill().dropna(how="all")
    if close.empty:
        raise ValueError("At least one historical price is required")
    close = close.dropna(axis=1, how="all")
    agent = agent or MovingAverageInvestmentAgent(config)
    weights = agent.weights(close).reindex(close.index, columns=close.columns).fillna(0.0)
    returns = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    turnover = weights.diff().abs().sum(axis=1).fillna(weights.abs().sum(axis=1))
    strategy_returns = (weights * returns).sum(axis=1) - turnover * config.transaction_cost

    active_symbols = close.columns
    benchmark_weights = pd.DataFrame(1 / len(active_symbols), index=close.index, columns=active_symbols)
    benchmark_returns = (benchmark_weights * returns).sum(axis=1)
    curve = pd.DataFrame(
        {
            "strategy_return": strategy_returns,
            "benchmark_return": benchmark_returns,
            "strategy": (1 + strategy_returns).cumprod(),
            "benchmark": (1 + benchmark_returns).cumprod(),
            "turnover": turnover,
        },
        index=close.index,
    )
    return BacktestResult(
        equity_curve=curve,
        metrics=performance_metrics(strategy_returns, config.annualization),
        benchmark_metrics=performance_metrics(benchmark_returns, config.annualization),
        weights=weights,
    )


def performance_metrics(returns: pd.Series, annualization: int = 252) -> dict[str, float]:
    returns = returns.fillna(0.0)
    equity = (1 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1
    volatility = float(returns.std(ddof=0) * np.sqrt(annualization))
    total_return = float(equity.iloc[-1] - 1)
    years = max(len(returns) / annualization, 1 / annualization)
    annualized = float(equity.iloc[-1] ** (1 / years) - 1)
    return {
        "total_return": total_return,
        "annualized_return": annualized,
        "annualized_volatility": volatility,
        "sharpe": float((returns.mean() / returns.std(ddof=0)) * np.sqrt(annualization))
        if returns.std(ddof=0) > 0
        else 0.0,
        "max_drawdown": float(drawdown.min()),
    }


def _wide_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if {"date", "symbol"}.issubset(prices.columns):
        value_column = "adj_close" if "adj_close" in prices.columns else "close"
        result = prices.pivot_table(index="date", columns="symbol", values=value_column, aggfunc="last")
    elif "symbol" in prices.columns:
        result = prices.drop(columns=["symbol"])
    else:
        result = prices.copy()
    result.index = pd.to_datetime(result.index)
    return result.sort_index().apply(pd.to_numeric, errors="coerce")
