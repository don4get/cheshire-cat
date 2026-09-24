"""Chronological portfolio research with a sealed final holdout.

Selection consumes only the first 80% of weekly investment periods. A small,
predeclared search is scored across four training-era time blocks; the selected
rule is frozen before the final 20% is replayed. All feature calculations are
causal. This module never downloads market data or places orders.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from functools import cached_property
from itertools import pairwise, product
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import func, select

from .backtest import performance_metrics
from .database import Price, TickerSymbol, get_engine

RESEARCH_VERSION = "chronological-momentum-v1"
ANNUALIZATION = 52
MIN_HISTORY = 52
MIN_WEEKLY_LIQUIDITY = 5_000_000.0
LIQUID_UNIVERSE_SIZE = 500
STALE_WEEKS = 4
SOURCES = [
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor_daily.html",
    "https://www.aqr.com/Insights/Research/Journal-Article/Fact-Fiction-and-Momentum-Investing",
    "https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html",
]


@dataclass(frozen=True)
class Candidate:
    signal: str = "blend"
    holdings: int = 20
    trend: bool = True
    weighting: str = "equal"
    rebalance: int = 4

    @property
    def key(self) -> str:
        return (
            f"{self.signal}-{self.holdings}-{'trend' if self.trend else 'all'}"
            f"-{self.weighting}-{self.rebalance}w"
        )


def candidate_catalog() -> tuple[Candidate, ...]:
    """Fixed before opening the holdout; no symbol-specific fitted parameters."""
    momentum = tuple(
        Candidate(*values)
        for values in product(
            ("6m", "12m", "blend"), (10, 20, 40), (False, True),
            ("equal", "inverse_volatility"), (4, 13),
        )
    )
    return momentum + (
        Candidate("low_volatility", 20, False, "equal", 4),
        Candidate("low_volatility", 20, True, "equal", 4),
        Candidate("reversal", 20, True, "equal", 4),
        Candidate("reversal", 40, True, "equal", 4),
        Candidate("benchmark", 500, False, "equal", 4),
        Candidate("classic", 500, True, "equal", 4),
    )


@dataclass
class MarketPanel:
    close: pd.DataFrame
    liquidity: pd.DataFrame
    metadata: dict[str, Any]
    universe_mask: pd.DataFrame | None = None

    def through(self, stop: int) -> MarketPanel:
        # A validation-only IPO must not even influence the training column set.
        close = self.close.iloc[:stop].dropna(axis=1, how="all")
        mask = (
            self.universe_mask.loc[close.index, close.columns]
            if self.universe_mask is not None
            else None
        )
        return MarketPanel(close, self.liquidity.loc[close.index, close.columns], self.metadata, mask)

    @cached_property
    def returns(self) -> pd.DataFrame:
        values = self.close.ffill().pct_change(fill_method=None).fillna(0.0)
        present = self.close.notna().to_numpy()
        age = np.zeros(present.shape[1], dtype=int)
        for i in range(len(values)):
            age = np.where(present[i], 0, age + 1)
            # A missing quote is not a free liquidation. After four missing
            # weeks we conservatively write a held asset down to zero. This is
            # an explicit valuation assumption, not a fabricated market quote.
            values.iloc[i, age == STALE_WEEKS] = -1.0
        return values

    @cached_property
    def eligible(self) -> pd.DataFrame:
        valid = self.close.notna()
        history = valid.rolling(MIN_HISTORY, min_periods=MIN_HISTORY).sum() == MIN_HISTORY
        liquid = self.liquidity.rolling(13, min_periods=13).median()
        # Historical liquidity only. Do not rank by today's size or select
        # assets on their future returns / eventual length of history.
        sufficient = history & valid & (liquid >= MIN_WEEKLY_LIQUIDITY)
        ranks = liquid.where(sufficient).rank(axis=1, ascending=False, method="first")
        result = sufficient & (ranks <= LIQUID_UNIVERSE_SIZE)
        if self.universe_mask is not None:
            result &= self.universe_mask.reindex(index=result.index, columns=result.columns, fill_value=False)
        return result

    @cached_property
    def volatility(self) -> pd.DataFrame:
        return self.close.pct_change(fill_method=None).rolling(26, min_periods=20).std() * np.sqrt(52)

    @cached_property
    def above_trend(self) -> pd.DataFrame:
        return self.close > self.close.rolling(40, min_periods=40).mean()

    @cached_property
    def scores(self) -> dict[str, pd.DataFrame]:
        past = self.close.shift(4)
        six = past / self.close.shift(26) - 1
        twelve = past / self.close.shift(52) - 1
        three = past / self.close.shift(13) - 1
        blend = sum(
            value.where(self.eligible).rank(axis=1, pct=True)
            for value in (three, six, twelve)
        ) / 3
        return {
            "6m": six, "12m": twelve, "blend": blend,
            "low_volatility": -self.volatility,
            "reversal": -(self.close / self.close.shift(4) - 1),
        }

    def fingerprint(self, start: int = 0) -> str:
        digest = hashlib.sha256()
        digest.update(RESEARCH_VERSION.encode())
        digest.update("|".join(self.close.columns).encode())
        frames = [self.close.iloc[start:], self.liquidity.iloc[start:]]
        if self.universe_mask is not None:
            frames.append(self.universe_mask.iloc[start:])
        for frame in frames:
            digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
        return digest.hexdigest()


def prepare_panel(prices: pd.DataFrame, *, metadata: dict[str, Any] | None = None) -> MarketPanel:
    """Align stored weekly bars to Friday, retaining their actual prices.

    Paris Monday bars were stored as Sunday UTC dates. Both Sunday and Monday
    map to the following Friday. A terminal daily quote can duplicate a weekly
    bar; the earlier (whole-week) row takes priority for weekly volume.
    """
    required = {"date", "symbol", "adj_close", "close", "volume"}
    if not required.issubset(prices.columns) or prices.empty:
        raise ValueError("Research requires adjusted close, close and volume history")
    frame = prices.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values(["date", "symbol"])
    frame["week"] = frame["date"].dt.to_period("W-FRI").dt.end_time.dt.normalize()
    invalid = ~np.isfinite(frame["adj_close"]) | (frame["adj_close"] <= 0)
    frame.loc[invalid, "adj_close"] = np.nan
    frame["liquidity"] = frame["close"] * frame["volume"]
    frame.loc[~np.isfinite(frame["liquidity"]) | (frame["liquidity"] <= 0), "liquidity"] = np.nan
    duplicate_count = int(frame.duplicated(["week", "symbol"]).sum())
    frame = frame.drop_duplicates(["week", "symbol"], keep="first")
    close = frame.pivot(index="week", columns="symbol", values="adj_close")
    liquidity = frame.pivot(index="week", columns="symbol", values="liquidity")
    dates = pd.date_range(close.index.min(), close.index.max(), freq="W-FRI")
    close = close.reindex(dates).sort_index(axis=1)
    liquidity = liquidity.reindex(index=dates, columns=close.columns)
    details = {
        **(metadata or {}), "raw_rows": len(prices), "invalid_prices": int(invalid.sum()),
        "duplicate_week_rows": duplicate_count, "symbols": len(close.columns),
    }
    return MarketPanel(close, liquidity, details)


def load_market(database_url: str | None, market: str, years: int = 20) -> tuple[MarketPanel, int]:
    if market not in {"NASDAQ", "EURONEXT_PARIS"}:
        raise ValueError("market must be NASDAQ or EURONEXT_PARIS")
    if not 5 <= years <= 20:
        raise ValueError("Research requires a horizon between 5 and 20 years")
    currency = "USD" if market == "NASDAQ" else "EUR"
    with get_engine(database_url).connect() as connection:
        latest = connection.execute(
            select(func.max(Price.date)).join(TickerSymbol, TickerSymbol.symbol == Price.symbol)
            .where(TickerSymbol.exchange == market, TickerSymbol.currency == currency)
        ).scalar()
        if latest is None:
            raise ValueError(f"No stored prices for {market}")
        # Complete weeks only; an unfinished bar is not a tradable past close.
        end = min(pd.Timestamp(latest).to_period("W-FRI").end_time.normalize(),
                  pd.Timestamp(datetime.now(UTC).date()))
        if end.dayofweek != 4:
            end -= pd.Timedelta(days=(end.dayofweek - 4) % 7)
        start = end - pd.Timedelta(days=round(years * 365.25))
        query = (
            select(Price.date, Price.symbol, Price.close, Price.adj_close, Price.volume)
            .join(TickerSymbol, TickerSymbol.symbol == Price.symbol)
            .where(TickerSymbol.exchange == market, TickerSymbol.currency == currency,
                   Price.date >= (start - timedelta(weeks=56)).date(), Price.date <= end.date())
            .order_by(Price.date, Price.symbol)
        )
        prices = pd.read_sql(query, connection)
    panel = prepare_panel(prices, metadata={"market": market, "currency": currency})
    panel.close = panel.close.loc[:end]
    panel.liquidity = panel.liquidity.loc[:end]
    first = int(panel.close.index.searchsorted(start))
    if len(panel.close) - first < 260:
        raise ValueError("At least five years of weekly history are needed for research")
    return panel, max(1, first)


def targets(panel: MarketPanel, candidate: Candidate, *, phase: int = 0) -> pd.DataFrame:
    """Desired weights decided at a close, executable only at the next close."""
    eligible = panel.eligible.copy()
    if candidate.trend:
        eligible &= panel.above_trend
    if candidate.signal in {"6m", "12m"}:
        eligible &= panel.scores[candidate.signal] > 0
    elif candidate.signal == "blend":
        eligible &= panel.scores["12m"] > 0
    if candidate.signal in {"benchmark", "classic"}:
        if candidate.signal == "classic":
            eligible &= (
                panel.close.rolling(10, min_periods=10).mean()
                > panel.close.rolling(40, min_periods=40).mean()
            ) & panel.above_trend
        selected = eligible.astype(float)
    else:
        rank = panel.scores[candidate.signal].where(eligible).rank(
            axis=1, ascending=False, method="first",
        )
        selected = (rank <= candidate.holdings).astype(float)
    if candidate.weighting == "inverse_volatility":
        selected = selected.div(panel.volatility.clip(lower=0.10)).fillna(0.0)
    weights = selected.div(selected.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    if candidate.signal not in {"benchmark", "classic"}:
        # Unallocated capital stays as cash if too few names pass the rules.
        # No leverage; a small basket never becomes a single-stock bet.
        weights = weights.clip(upper=1 / candidate.holdings)
    schedule = (np.arange(len(weights)) - phase) % candidate.rebalance == 0
    weights.loc[~schedule] = np.nan
    return weights.ffill().fillna(0.0)


@dataclass
class Simulation:
    returns: pd.Series
    turnover: pd.Series
    exposure: pd.Series
    costs: pd.Series
    final_weights: pd.Series
    stale_losses: int
    attribution: pd.Series | None = None


def simulate(
    panel: MarketPanel, desired: pd.DataFrame, *, start: int, cost: float = 0.001,
    rebalance: int = 4,
    snapshot: Callable[[dict[str, Any]], None] | None = None,
    execution_delay: int = 1,
    rebalance_phase: int = 0,
    trade_schedule: pd.Series | None = None,
    attribution_end: int | None = None,
) -> Simulation:
    """Self-financing accounting, real drift, two-close signal/return separation.

    At t: first mark existing holdings with the t return. Then execute the
    decision from t-1 at t's close and pay costs on actual value traded. That
    decision first earns a return at t+1. Missing quotes cannot be traded.
    """
    if not np.isfinite(cost) or not 0 <= cost < 0.1:
        raise ValueError("transaction_cost must be finite and between 0 and 0.1")
    if not 1 <= start < len(panel.close):
        raise ValueError("A prior observation and at least one investment period are required")
    if execution_delay < 1 or rebalance < 1:
        raise ValueError("Execution delay and rebalance interval must be positive")
    desired = desired.reindex(index=panel.close.index, columns=panel.close.columns).fillna(0.0)
    weights = desired.to_numpy(dtype=float)
    if not np.isfinite(weights).all() or (weights < 0).any() or (weights.sum(axis=1) > 1.000001).any():
        raise ValueError("Targets must be finite, long-only and unlevered")
    returns = panel.returns.to_numpy()
    tradable = panel.close.notna().to_numpy()
    positions = np.zeros(weights.shape[1])
    cash = 1.0
    values, turnovers, exposures, costs = [], [], [], []
    stale_losses = 0
    contributions = np.zeros(weights.shape[1]) if attribution_end is not None else None
    schedule = (trade_schedule.reindex(panel.close.index, fill_value=False).to_numpy(dtype=bool)
                if trade_schedule is not None else None)
    for t in range(start, len(weights)):
        previous = cash + positions.sum()
        stale_losses += int(np.count_nonzero((returns[t] == -1) & (positions > 0)))
        if contributions is not None and t < attribution_end:
            contributions += positions * returns[t]
        positions *= 1 + returns[t]
        gross = cash + positions.sum()
        traded, fee = 0.0, 0.0
        decision = t - execution_delay
        due = bool(schedule[t]) if schedule is not None else (decision - rebalance_phase) % rebalance == 0
        if decision >= 0 and (t == max(start, execution_delay) or due):
            free = gross - positions[~tradable[t]].sum()
            requested = weights[decision].copy()
            requested[~tradable[t]] = 0.0
            existing = positions[tradable[t]]
            target = requested[tradable[t]]
            # Solve fee = c * turnover after fees. This accounts for initial
            # entry and drift-induced trades even when target weights repeat.
            for _ in range(12):
                allocation = (free - fee) * target
                traded = float(np.abs(allocation - existing).sum())
                fee = traded * cost
            positions[tradable[t]] = (free - fee) * target
            cash = max(0.0, gross - fee - positions.sum())
        value = cash + positions.sum()
        values.append(value / previous - 1 if previous > 0 else 0.0)
        turnovers.append(traded / gross if gross > 0 else 0.0)
        exposures.append(positions.sum() / value if value > 0 else 0.0)
        costs.append(fee)
        if snapshot is not None:
            snapshot({
                "date": panel.close.index[t].date().isoformat(),
                "value": float(value), "cash": float(cash),
                "traded": traded > 1e-12, "turnover": turnovers[-1], "cost": float(fee),
                "holdings": [
                    {"symbol": str(panel.close.columns[j]), "value": float(positions[j]),
                     "weight": float(positions[j] / value) if value > 0 else 0.0,
                     "priced": bool(tradable[t, j])}
                    for j in np.flatnonzero(positions > 0)
                ],
            })
    dates = panel.close.index[start:]
    final_value = cash + positions.sum()
    return Simulation(
        pd.Series(values, index=dates), pd.Series(turnovers, index=dates),
        pd.Series(exposures, index=dates), pd.Series(costs, index=dates),
        pd.Series(positions / final_value if final_value > 0 else positions, index=panel.close.columns),
        stale_losses,
        pd.Series(contributions, index=panel.close.columns) if contributions is not None else None,
    )


def metrics(simulation: Simulation, initial_cash: float, segment: slice = slice(None)) -> dict[str, float]:
    returns = simulation.returns.iloc[segment]
    result = performance_metrics(returns, ANNUALIZATION)
    # Include starting cash in the high-water mark (the old backtester omits
    # the first loss when establishing peak equity).
    equity = (1 + returns).cumprod()
    drawdown = equity / equity.cummax().clip(lower=1.0) - 1
    result.update(
        max_drawdown=float(drawdown.min()), final_value=float(initial_cash * equity.iloc[-1]),
        exposure=float(simulation.exposure.iloc[segment].mean()),
        average_turnover=float(simulation.turnover.iloc[segment].mean()),
        profitable_periods=float((returns > 0).mean()),
        calmar=float(result["annualized_return"] / abs(drawdown.min())) if drawdown.min() < 0 else 0.0,
    )
    return result


def training_score(returns: pd.Series) -> tuple[float, list[dict[str, Any]]]:
    """ROI objective with a fixed penalty for dependence on one training era.

    Four chronological tuning blocks after an initial 20% history prefix.
    These are internal model-selection results, not an independent holdout.
    """
    edges = np.linspace(len(returns) // 5, len(returns), 5, dtype=int)
    blocks, growth = [], []
    for left, right in pairwise(edges):
        part = returns.iloc[left:right]
        log_growth = float(np.log1p(part.clip(lower=-0.999999)).mean() * 52)
        growth.append(log_growth)
        blocks.append({
            "start_date": part.index[0].date().isoformat(),
            "end_date": part.index[-1].date().isoformat(),
            "total_return": float((1 + part).prod() - 1),
            "annualized_return": float(np.expm1(log_growth)),
        })
    full_growth = float(np.log1p(returns.clip(lower=-0.999999)).mean() * 52)
    return full_growth - 0.25 * float(np.std(growth)), blocks


def select_strategy(
    training: MarketPanel, start: int, cost: float,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Only training is accepted here; the final holdout is inaccessible."""
    leaderboard = []
    candidate_returns = {}
    catalog = candidate_catalog()
    for index, candidate in enumerate(catalog):
        sim = simulate(training, targets(training, candidate), start=start,
                       cost=cost, rebalance=candidate.rebalance)
        score, blocks = training_score(sim.returns)
        candidate_returns[candidate.key] = sim.returns
        leaderboard.append({
            "id": candidate.key, "parameters": asdict(candidate), "score": score,
            "training": metrics(sim, 100_000), "folds": blocks,
        })
        if progress and (index % 8 == 0 or index + 1 == len(catalog)):
            progress(f"Training candidate {index + 1}/{len(catalog)}")
    leaderboard.sort(key=lambda row: (-row["score"], row["id"]))
    # A fixed top-three ensemble reduces dependence on a single parameter set.
    # Its members and its comparison with the winner are decided in training.
    members = [Candidate(**row["parameters"]) for row in leaderboard[:3]]
    ensemble_targets = sum(targets(training, member) for member in members) / len(members)
    ensemble = simulate(training, ensemble_targets, start=start, cost=cost, rebalance=1)
    ensemble_score, ensemble_blocks = training_score(ensemble.returns)
    use_ensemble = ensemble_score > leaderboard[0]["score"]
    selected = members if use_ensemble else members[:1]
    # Independently show a training-era walk-forward selector: each block's
    # rule is picked from its earlier prefix, never from that block's returns.
    edges = np.linspace(len(ensemble.returns) // 3, len(ensemble.returns), 5, dtype=int)
    walk_forward = []
    for left, right in pairwise(edges):
        winner = max(candidate_returns, key=lambda key: training_score(candidate_returns[key].iloc[:left])[0])
        segment = candidate_returns[winner].iloc[left:right]
        walk_forward.append({
            "start_date": segment.index[0].date().isoformat(),
            "end_date": segment.index[-1].date().isoformat(), "selected_id": winner,
            "total_return": float((1 + segment).prod() - 1),
            "note": "Shadow-strategy block returns; excludes costs of switching between bots.",
        })
    return {
        "version": RESEARCH_VERSION, "training_fingerprint": training.fingerprint(),
        "selected_id": "momentum-ensemble" if use_ensemble else selected[0].key,
        "selected_name": "Cheshire momentum ensemble" if use_ensemble else "Cheshire adaptive momentum",
        "members": [asdict(member) for member in selected],
        "selection_score": ensemble_score if use_ensemble else leaderboard[0]["score"],
        "candidate_count": len(catalog) + 1,
        "ensemble_score": ensemble_score, "ensemble_folds": ensemble_blocks,
        "leaderboard": leaderboard, "walk_forward": walk_forward,
        "objective": "Net annualized log growth minus 0.25 × variation across training eras",
        "frozen_at": datetime.now(UTC).isoformat(),
    }


def evaluate_selection(
    panel: MarketPanel, start: int, split: int, selection: dict[str, Any], *,
    initial_cash: float, cost: float,
) -> dict[str, Any]:
    """Replay the already-frozen choice and fixed baselines; never reselect."""
    if panel.through(split).fingerprint() != selection["training_fingerprint"]:
        raise ValueError("The training snapshot does not match the frozen selection")
    members = [Candidate(**member) for member in selection["members"]]
    chosen_targets = sum(targets(panel, member) for member in members) / len(members)
    configs = [
        (selection["selected_id"], selection["selected_name"], chosen_targets,
         members[0].rebalance if len(members) == 1 else 1, False),
        ("liquid_equal_weight", "Liquid universe · equal weight",
         targets(panel, Candidate("benchmark", 500, False)), 4, True),
        ("classic", "Classic trend · 10/40 weeks",
         targets(panel, Candidate("classic", 500, True)), 4, True),
        ("buy_hold", "Starting liquid basket · buy and hold",
         targets(panel, Candidate("benchmark", 500, False)), 1_000_000, True),
    ]
    train_count = split - start
    strategies = []
    for key, name, weights, frequency, is_benchmark in configs:
        sim = simulate(panel, weights, start=start, cost=cost, rebalance=frequency)
        equity = initial_cash * (1 + sim.returns).cumprod()
        yearly = sim.returns.groupby(sim.returns.index.year).apply(lambda part: (1 + part).prod() - 1)
        strategies.append({
            "id": key, "name": name, "is_benchmark": is_benchmark,
            "training": metrics(sim, initial_cash, slice(0, train_count)),
            "validation": metrics(sim, initial_cash, slice(train_count, None)),
            "full": metrics(sim, initial_cash),
            "curve": [{"date": panel.close.index[start - 1].date().isoformat(), "value": initial_cash}]
            + [{"date": day.date().isoformat(), "value": float(value)} for day, value in equity.items()],
            "annual_returns": [{"year": int(year), "total_return": float(value)} for year, value in yearly.items()],
            "holdings": [{"symbol": symbol, "weight": float(weight)}
                         for symbol, weight in sim.final_weights.sort_values(ascending=False).items()
                         if weight > 0.00001],
            "stale_position_writeoffs": sim.stale_losses,
            "total_cost": float(sim.costs.sum() * initial_cash),
        })
    selected = strategies[0]
    # Stress the frozen rule, not a re-optimized high-cost portfolio.
    stressed = simulate(panel, chosen_targets, start=start, cost=min(cost * 2, 0.099),
                        rebalance=members[0].rebalance if len(members) == 1 else 1)
    validation_excess = selected["validation"]["total_return"] - strategies[1]["validation"]["total_return"]
    dates = panel.close.index
    limitations = [
        "The universe is today's tracked listings. Missing delisted companies create survivorship bias; this is not a historical index replication.",
        "Adjusted prices are the provider's current revision. Historical corporate-action and quote corrections are not archived point in time.",
        "Fundamentals are excluded: publication-time coverage is inconsistent over twenty years, especially Yahoo statements.",
        "Weekly close execution uses a full one-bar delay, flat per-side costs, zero cash interest and no taxes. Liquidity is a filter, not a market-impact model.",
        "A held security without a price for four weeks is conservatively written down to zero; no sale at an invented quote is assumed.",
        "Full-period results include training and are descriptive. Only the final 20% evaluates the frozen selection; repeatedly changing the model after reading it would invalidate that holdout.",
    ]
    return {
        "version": RESEARCH_VERSION, "market": panel.metadata.get("market", "custom"),
        "currency": panel.metadata.get("currency", "units"), "frequency": "weekly",
        "initial_cash": initial_cash, "transaction_cost": cost,
        "data_fingerprint": panel.fingerprint(), "coverage": panel.metadata,
        "split": {
            "method": "chronological", "training_fraction": 0.8,
            "training_start": dates[start].date().isoformat(),
            "training_end": dates[split - 1].date().isoformat(),
            "validation_start": dates[split].date().isoformat(),
            "validation_end": dates[-1].date().isoformat(),
            "training_periods": train_count, "validation_periods": len(dates) - split,
            "warmup_periods": start,
        },
        "selection": selection, "strategies": strategies,
        "validation_excess_return": validation_excess,
        "validation_verdict": "Beat the equal-weight benchmark" if validation_excess > 0 else "Did not beat the equal-weight benchmark",
        "cost_stress": {"transaction_cost": min(cost * 2, 0.099),
                        "validation": metrics(stressed, initial_cash, slice(train_count, None))},
        "limitations": limitations, "sources": SOURCES,
        "completed_at": datetime.now(UTC).isoformat(),
    }


def run_research(
    panel: MarketPanel, start: int, *, initial_cash: float = 100_000,
    cost: float = 0.001, progress: Callable[[str], None] | None = None,
    freeze: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if not np.isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError("initial_cash must be positive and finite")
    periods = len(panel.close) - start
    if periods < 260:
        raise ValueError("At least 260 weekly periods are required for an 80/20 research split")
    split = start + int(np.floor(periods * 0.8))
    training = panel.through(split)
    selection = select_strategy(training, start, cost, progress)
    if freeze:
        # Persist this before ANY final-period strategy performance is computed.
        freeze(selection)
    if progress:
        progress("Selection frozen. Evaluating the final 20% once.")
    result = evaluate_selection(panel, start, split, selection, initial_cash=initial_cash, cost=cost)
    # Fail closed rather than serving nonfinite or invalid JSON to the UI.
    json.dumps(result, allow_nan=False)
    return result
