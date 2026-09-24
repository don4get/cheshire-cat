"""Comparable, reproducible strategy simulations for the dashboard playground."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .backtest import InvestmentAgent, MovingAverageInvestmentAgent, StrategyConfig, backtest


@dataclass(frozen=True)
class StrategySpec:
    """A named strategy registered in the playground leaderboard."""

    key: str
    name: str
    description: str
    family: str
    fast_window: int | None = None
    slow_window: int | None = None


@dataclass(frozen=True)
class EqualWeightAgent:
    """Buy-and-hold equal weight across the available instruments."""

    def weights(self, prices: pd.DataFrame) -> pd.DataFrame:
        available = prices.notna().astype(float)
        return available.div(available.sum(axis=1).replace(0, pd.NA), axis=0).fillna(0.0)


def strategy_catalog() -> tuple[StrategySpec, ...]:
    """Return the built-in bots; future bots can be added without changing the API shape."""

    return (
        StrategySpec(
            key="equal_weight",
            name="Equal-weight hold",
            description="Buy every available instrument once and hold the basket.",
            family="Benchmark",
        ),
        StrategySpec(
            key="trend_fast",
            name="Trend · fast",
            description="Long-only moving-average trend with 20/80 observations.",
            family="Cheshire bot",
            fast_window=20,
            slow_window=80,
        ),
        StrategySpec(
            key="trend_classic",
            name="Trend · classic",
            description="The default Cheshire bot with a 50/200 moving-average signal.",
            family="Cheshire bot",
            fast_window=50,
            slow_window=200,
        ),
        StrategySpec(
            key="trend_defensive",
            name="Trend · defensive",
            description="A slower signal designed to trade less often through noise.",
            family="Cheshire bot",
            fast_window=100,
            slow_window=300,
        ),
        StrategySpec(
            key="trend_long",
            name="Trend · long cycle",
            description="A long-cycle 200/400 signal for patient allocations.",
            family="Cheshire bot",
            fast_window=200,
            slow_window=400,
        ),
    )


def run_playground(
    prices: pd.DataFrame,
    *,
    initial_cash: float = 100_000.0,
    transaction_cost: float = 0.001,
    annualization: int = 252,
) -> dict[str, Any]:
    """Run every registered bot on exactly the same real price observations."""

    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if annualization < 1:
        raise ValueError("annualization must be positive")
    if prices.empty:
        raise ValueError("At least one historical price is required")

    normalized = prices.copy()
    normalized["date"] = pd.to_datetime(normalized["date"])
    normalized = normalized.sort_values(["date", "symbol"])
    symbols = sorted(str(symbol) for symbol in normalized["symbol"].dropna().unique())
    results: list[dict[str, Any]] = []
    for spec in strategy_catalog():
        config = StrategyConfig(
            fast_window=spec.fast_window or 2,
            slow_window=spec.slow_window or 3,
            transaction_cost=transaction_cost,
            annualization=annualization,
        )
        agent: InvestmentAgent
        if spec.key == "equal_weight":
            agent = EqualWeightAgent()
        else:
            agent = MovingAverageInvestmentAgent(config)
        result = backtest(normalized, agent=agent, config=config)
        curve = result.equity_curve
        strategy_returns = curve["strategy_return"]
        metrics = dict(result.metrics)
        max_drawdown = abs(metrics.get("max_drawdown", 0.0))
        metrics.update(
            {
                "final_value": float(initial_cash * curve["strategy"].iloc[-1]),
                "exposure": float(result.weights.sum(axis=1).mean()),
                "average_turnover": float(curve["turnover"].mean()),
                "profitable_periods": float((strategy_returns > 0).mean()),
                "calmar": float(metrics["annualized_return"] / max_drawdown)
                if max_drawdown > 0
                else 0.0,
            }
        )
        results.append(
            {
                "id": spec.key,
                "name": spec.name,
                "description": spec.description,
                "family": spec.family,
                "is_benchmark": spec.key == "equal_weight",
                "metrics": metrics,
                "curve": [
                    {
                        "date": timestamp.date().isoformat(),
                        "value": float(initial_cash * value),
                    }
                    for timestamp, value in curve["strategy"].items()
                ],
            }
        )

    # Sharpe is the declared leaderboard score: it keeps high raw returns from
    # winning solely by taking substantially more volatility.
    results.sort(
        key=lambda item: (
            float(item["metrics"].get("sharpe", 0.0)),
            float(item["metrics"].get("annualized_return", 0.0)),
        ),
        reverse=True,
    )
    for rank, item in enumerate(results, start=1):
        item["rank"] = rank
        item["score"] = float(item["metrics"].get("sharpe", 0.0))

    dates = pd.to_datetime(normalized["date"])
    start_date = dates.min().date()
    end_date = dates.max().date()
    actual_years = max((end_date - start_date).days / 365.25, 0.0)
    return {
        "requested_years": None,
        "actual_years": actual_years,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "annualization": annualization,
        "frequency": "daily" if annualization >= 200 else "weekly",
        "symbols": symbols,
        "observations": len(normalized),
        "initial_cash": initial_cash,
        "transaction_cost": transaction_cost,
        "strategies": results,
    }
