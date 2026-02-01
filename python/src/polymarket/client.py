"""Polymarket API client for interacting with the CLOB API."""

import httpx
from typing import Optional, Any
from dataclasses import dataclass
from datetime import datetime
import structlog
from eth_account import Account
from eth_account.messages import encode_defunct
import time
import hmac
import hashlib
import base64

logger = structlog.get_logger()

# Polymarket API endpoints
CLOB_API_BASE = "https://clob.polymarket.com"
GAMMA_API_BASE = "https://gamma-api.polymarket.com"


@dataclass
class Market:
    """Represents a Polymarket market."""

    id: str
    condition_id: str
    question: str
    description: str
    outcomes: list[str]
    outcome_prices: list[float]
    volume: float
    liquidity: float
    end_date: Optional[datetime]
    category: str
    active: bool
    closed: bool


@dataclass
class Order:
    """Represents a trade order."""

    market_id: str
    side: str  # "BUY" or "SELL"
    outcome: int  # 0 or 1
    size: float
    price: float
    order_type: str = "GTC"  # Good Till Cancel


@dataclass
class Position:
    """Represents an open position."""

    market_id: str
    outcome: int
    size: float
    avg_price: float
    current_price: float
    pnl: float


class PolymarketClient:
    """Client for Polymarket CLOB API."""

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        private_key: str = "",
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.private_key = private_key
        self._http_client: Optional[httpx.AsyncClient] = None
        self._account: Optional[Account] = None

        if private_key:
            self._account = Account.from_key(private_key)
            logger.info("Initialized wallet", address=self._account.address)

    async def __aenter__(self):
        """Async context manager entry."""
        self._http_client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._http_client:
            await self._http_client.aclose()

    def _generate_signature(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """Generate HMAC signature for authenticated requests."""
        message = f"{timestamp}{method}{path}{body}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode()

    def _get_auth_headers(self, method: str, path: str, body: str = "") -> dict:
        """Get authentication headers for API requests."""
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, method, path, body)

        return {
            "POLY_API_KEY": self.api_key,
            "POLY_SIGNATURE": signature,
            "POLY_TIMESTAMP": timestamp,
            "POLY_PASSPHRASE": "",  # If using passphrase
        }

    async def _request(
        self,
        method: str,
        url: str,
        authenticated: bool = False,
        **kwargs
    ) -> dict[str, Any]:
        """Make an HTTP request to the API."""
        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=30.0)

        headers = kwargs.pop("headers", {})

        if authenticated:
            path = url.replace(CLOB_API_BASE, "")
            body = kwargs.get("json", "")
            if body:
                import json
                body = json.dumps(body)
            auth_headers = self._get_auth_headers(method, path, body if body else "")
            headers.update(auth_headers)

        response = await self._http_client.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()

        return response.json()

    async def get_markets(
        self,
        category: Optional[str] = None,
        active: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Market]:
        """Fetch markets from Polymarket."""
        params = {
            "limit": limit,
            "offset": offset,
            "active": str(active).lower(),
        }

        if category:
            params["tag"] = category

        try:
            response = await self._request(
                "GET",
                f"{GAMMA_API_BASE}/markets",
                params=params,
            )

            markets = []
            for m in response:
                try:
                    markets.append(self._parse_market(m))
                except Exception as e:
                    logger.warning("Failed to parse market", error=str(e), market_id=m.get("id"))

            return markets

        except Exception as e:
            logger.error("Failed to fetch markets", error=str(e))
            raise

    async def get_market(self, market_id: str) -> Market:
        """Fetch a specific market by ID."""
        response = await self._request(
            "GET",
            f"{GAMMA_API_BASE}/markets/{market_id}",
        )
        return self._parse_market(response)

    async def get_crypto_markets(self, limit: int = 100) -> list[Market]:
        """Fetch crypto-related markets."""
        # Search for crypto-related markets
        all_markets = await self.get_markets(limit=limit)

        crypto_keywords = [
            "bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol",
            "dogecoin", "doge", "xrp", "ripple", "cardano", "ada", "polygon",
            "matic", "avalanche", "avax", "chainlink", "link", "uniswap",
            "defi", "nft", "web3", "blockchain"
        ]

        crypto_markets = []
        for market in all_markets:
            question_lower = market.question.lower()
            desc_lower = (market.description or "").lower()

            if any(kw in question_lower or kw in desc_lower for kw in crypto_keywords):
                crypto_markets.append(market)

        logger.info("Found crypto markets", count=len(crypto_markets))
        return crypto_markets

    async def get_orderbook(self, token_id: str) -> dict[str, Any]:
        """Get orderbook for a specific token."""
        response = await self._request(
            "GET",
            f"{CLOB_API_BASE}/book",
            params={"token_id": token_id},
        )
        return response

    async def get_price_history(
        self,
        token_id: str,
        interval: str = "1h",
        fidelity: int = 60,
    ) -> list[dict]:
        """Get price history for a token."""
        response = await self._request(
            "GET",
            f"{CLOB_API_BASE}/prices-history",
            params={
                "market": token_id,
                "interval": interval,
                "fidelity": fidelity,
            },
        )
        return response.get("history", [])

    async def get_positions(self) -> list[Position]:
        """Get current positions for the authenticated user."""
        if not self._account:
            raise ValueError("Private key required for authenticated endpoints")

        response = await self._request(
            "GET",
            f"{CLOB_API_BASE}/positions",
            authenticated=True,
        )

        positions = []
        for p in response:
            positions.append(Position(
                market_id=p["market"],
                outcome=p["outcome"],
                size=float(p["size"]),
                avg_price=float(p["avgPrice"]),
                current_price=float(p.get("currentPrice", 0)),
                pnl=float(p.get("pnl", 0)),
            ))

        return positions

    async def place_order(self, order: Order) -> dict[str, Any]:
        """Place an order on Polymarket."""
        if not self._account:
            raise ValueError("Private key required for trading")

        order_payload = {
            "market": order.market_id,
            "side": order.side,
            "outcome": order.outcome,
            "size": str(order.size),
            "price": str(order.price),
            "type": order.order_type,
        }

        logger.info(
            "Placing order",
            market=order.market_id,
            side=order.side,
            outcome=order.outcome,
            size=order.size,
            price=order.price,
        )

        response = await self._request(
            "POST",
            f"{CLOB_API_BASE}/order",
            authenticated=True,
            json=order_payload,
        )

        return response

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel an existing order."""
        response = await self._request(
            "DELETE",
            f"{CLOB_API_BASE}/order/{order_id}",
            authenticated=True,
        )
        return response

    async def get_open_orders(self) -> list[dict]:
        """Get all open orders."""
        response = await self._request(
            "GET",
            f"{CLOB_API_BASE}/orders",
            authenticated=True,
        )
        return response

    def _parse_market(self, data: dict) -> Market:
        """Parse market data from API response."""
        # Handle different API response formats
        outcomes = data.get("outcomes", ["Yes", "No"])
        if isinstance(outcomes, str):
            outcomes = outcomes.split(",")

        # Parse outcome prices
        outcome_prices = []
        if "outcomePrices" in data:
            prices = data["outcomePrices"]
            if isinstance(prices, str):
                outcome_prices = [float(p) for p in prices.split(",")]
            elif isinstance(prices, list):
                outcome_prices = [float(p) for p in prices]
        elif "tokens" in data:
            for token in data["tokens"]:
                outcome_prices.append(float(token.get("price", 0.5)))

        # Parse end date
        end_date = None
        if data.get("endDate"):
            try:
                end_date = datetime.fromisoformat(data["endDate"].replace("Z", "+00:00"))
            except:
                pass

        return Market(
            id=data.get("id", data.get("condition_id", "")),
            condition_id=data.get("conditionId", data.get("condition_id", "")),
            question=data.get("question", ""),
            description=data.get("description", ""),
            outcomes=outcomes,
            outcome_prices=outcome_prices if outcome_prices else [0.5, 0.5],
            volume=float(data.get("volume", 0) or 0),
            liquidity=float(data.get("liquidity", 0) or 0),
            end_date=end_date,
            category=data.get("category", data.get("tag", "")),
            active=data.get("active", True),
            closed=data.get("closed", False),
        )
