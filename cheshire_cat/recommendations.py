"""Explainable investment-allocation suggestions with no broker side effects."""

from __future__ import annotations

from typing import Any, Iterable


def suggest_investments(
    portfolio: Iterable[dict[str, Any]],
    amount: float,
    *,
    strategy: str = "equal_weight",
    prices: dict[str, float] | None = None,
    target_weights: dict[str, float] | None = None,
    max_positions: int = 20,
    fractional_precision: int = 6,
) -> dict[str, Any]:
    """Suggest buys for a known portfolio and a cash amount.

    The portfolio is treated as the allowed universe. Existing holdings are
    marked to the supplied prices; new cash is allocated to the target weights.
    The function returns a preview only and never places or records a trade.
    """

    if amount <= 0:
        raise ValueError("amount must be positive")
    if max_positions < 1:
        raise ValueError("max_positions must be positive")
    prices = {str(symbol).upper(): float(value) for symbol, value in (prices or {}).items()}
    holdings: dict[str, float] = {}
    for row in portfolio:
        symbol = str(row.get("symbol", "")).upper()
        quantity = float(row.get("quantity", 0.0))
        if not symbol or quantity < 0:
            raise ValueError("portfolio rows require a symbol and non-negative quantity")
        holdings[symbol] = holdings.get(symbol, 0.0) + quantity
        if row.get("price") is not None:
            prices.setdefault(symbol, float(row["price"]))
    symbols = [symbol for symbol in holdings if symbol in prices and prices[symbol] > 0]
    if not symbols:
        raise ValueError("known portfolio has no positive prices")
    symbols = sorted(symbols, key=lambda symbol: (-holdings[symbol] * prices[symbol], symbol))[:max_positions]
    current_values = {symbol: holdings[symbol] * prices[symbol] for symbol in symbols}
    current_total = sum(current_values.values())
    if target_weights is None and strategy in {"current_weight", "current_weights", "hold"}:
        weights = {
            symbol: current_values[symbol] / current_total
            for symbol in symbols
        } if current_total else {symbol: 1.0 / len(symbols) for symbol in symbols}
    elif target_weights is None:
        weights = {symbol: 1.0 / len(symbols) for symbol in symbols}
    else:
        weights = {symbol: max(0.0, float(target_weights.get(symbol, 0.0))) for symbol in symbols}
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("target_weights must allocate to at least one known symbol")
        weights = {symbol: value / total for symbol, value in weights.items()}
    target_total = current_total + amount
    suggestions = []
    spent = 0.0
    for symbol in symbols:
        desired_value = target_total * weights[symbol]
        additional_value = max(0.0, desired_value - current_values[symbol])
        quantity = round(additional_value / prices[symbol], fractional_precision)
        allocation = quantity * prices[symbol]
        if quantity > 0:
            suggestions.append(
                {
                    "symbol": symbol,
                    "action": "buy",
                    "quantity": quantity,
                    "price": prices[symbol],
                    "estimated_value": allocation,
                    "current_quantity": holdings[symbol],
                    "current_weight": current_values[symbol] / current_total if current_total else 0.0,
                    "target_weight": weights[symbol],
                    "reason": f"{strategy}: move toward the declared target weight within the known portfolio",
                }
            )
            spent += allocation
    return {
        "strategy": strategy,
        "input_amount": amount,
        "known_portfolio_value": current_total,
        "target_weights": weights,
        "suggestions": suggestions,
        "estimated_spent": spent,
        "unallocated_cash": max(0.0, amount - spent),
        "method": "No sells; allocate new cash toward target weights using supplied prices.",
        "disclaimer": "Research allocation preview only. Review prices, fees, taxes, suitability, and execution before acting.",
    }
