"""Small, read-only-by-default adapter for Saxo OpenAPI.

The adapter is intentionally not coupled to the research engine. It exposes
portfolio/account reads and order previews, while order placement requires an
explicit opt-in at construction and a second confirmation argument. This
prevents a dashboard research action from becoming a brokerage action.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

SIM_BASE_URL = "https://gateway.saxobank.com/sim/openapi"
LIVE_BASE_URL = "https://gateway.saxobank.com/openapi"
SIM_AUTH_URL = "https://sim.logonvalidation.net"
LIVE_AUTH_URL = "https://live.logonvalidation.net"


@dataclass(frozen=True)
class SaxoConfig:
    environment: str = "sim"
    access_token: str | None = None
    timeout_seconds: float = 20.0
    allow_orders: bool = False

    @property
    def base_url(self) -> str:
        if self.environment not in {"sim", "live"}:
            raise ValueError("environment must be 'sim' or 'live'")
        return SIM_BASE_URL if self.environment == "sim" else LIVE_BASE_URL

    @property
    def auth_url(self) -> str:
        return SIM_AUTH_URL if self.environment == "sim" else LIVE_AUTH_URL

    @classmethod
    def from_environment(cls) -> "SaxoConfig":
        return cls(
            environment=os.getenv("SAXO_ENVIRONMENT", "sim").lower(),
            access_token=os.getenv("SAXO_ACCESS_TOKEN"),
            allow_orders=os.getenv("SAXO_ALLOW_ORDERS", "0").lower() in {"1", "true", "yes"},
        )


class SaxoOpenAPI:
    """Authenticated Saxo client with explicit safe defaults."""

    def __init__(self, config: SaxoConfig | None = None, session: requests.Session | None = None):
        self.config = config or SaxoConfig.from_environment()
        if not self.config.access_token:
            raise ValueError("SAXO_ACCESS_TOKEN or SaxoConfig(access_token=...) is required")
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.config.access_token}",
                "Accept": "application/json",
                "User-Agent": "cheshire-cat/0.1 read-only adapter",
            }
        )

    def get(self, resource: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET a documented OpenAPI resource and return its JSON body."""

        path = resource if resource.startswith("/") else f"/{resource}"
        response = self.session.get(
            f"{self.config.base_url}{path}",
            params=params,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Saxo OpenAPI response must be a JSON object")
        return payload

    def accounts(self) -> dict[str, Any]:
        return self.get("/port/v1/accounts/me")

    def balances(self) -> dict[str, Any]:
        return self.get("/port/v1/balances/me")

    def positions(self) -> dict[str, Any]:
        return self.get("/port/v1/positions/me")

    def orders(self, status: str | None = None) -> dict[str, Any]:
        return self.get("/port/v1/orders/me", {"Status": status} if status else None)

    def quote(self, uic: int, asset_type: str, field_groups: str = "DisplayAndFormat") -> dict[str, Any]:
        return self.get(
            "/trade/v1/infoprices",
            {"Uic": uic, "AssetType": asset_type, "FieldGroups": field_groups},
        )

    @staticmethod
    def preview_order(
        *,
        account_key: str,
        uic: int,
        asset_type: str,
        buy_sell: str,
        amount: float,
        order_type: str = "Market",
        order_price: float | None = None,
    ) -> dict[str, Any]:
        """Build an order payload without sending it anywhere."""

        if amount <= 0:
            raise ValueError("amount must be positive")
        if buy_sell not in {"Buy", "Sell"}:
            raise ValueError("buy_sell must be Buy or Sell")
        if order_type != "Market" and order_price is None:
            raise ValueError("order_price is required for non-market orders")
        payload = {
            "AccountKey": account_key,
            "Uic": uic,
            "AssetType": asset_type,
            "BuySell": buy_sell,
            "Amount": amount,
            "OrderType": order_type,
            "ManualOrder": True,
        }
        if order_price is not None:
            payload["OrderPrice"] = order_price
        return payload

    def place_order(self, payload: dict[str, Any], *, confirm: str | None = None) -> dict[str, Any]:
        """Place an order only after two independent explicit opt-ins."""

        if not self.config.allow_orders:
            raise PermissionError("Order placement is disabled; use preview_order or allow_orders explicitly")
        if confirm != "PLACE_ORDER":
            raise PermissionError("Order placement requires confirm='PLACE_ORDER'")
        response = self.session.post(
            f"{self.config.base_url}/trade/v2/orders",
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {"response": body}
