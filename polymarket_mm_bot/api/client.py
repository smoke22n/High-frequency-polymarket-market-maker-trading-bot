"""
Polymarket API Client Implementation
This module contains the REST and WebSocket clients for interacting with Polymarket's CLOB.
"""
import asyncio
import json
import time
import hashlib
import hmac
from typing import Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass
import aiohttp
import websockets
from ..utils.rate_limiter import RateLimiter


@dataclass
class Credentials:
    """Credentials for Polymarket API authentication"""
    api_key: str
    secret_key: str
    wallet_address: str


class PolymarketRestClient:
    """
    REST client for Polymarket CLOB API
    Handles placing/cancelling orders and other REST operations
    """
    
    def __init__(self, credentials: Credentials, base_url: str = "https://clob.polymarket.com"):
        self.credentials = credentials
        self.base_url = base_url
        self.session = None
        self.rate_limiter = RateLimiter(max_requests=500, time_window=10)  # 500 requests per 10 seconds
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    def _sign_request(self, method: str, endpoint: str, payload: str = "") -> Dict[str, str]:
        """
        Sign the request using HMAC-SHA256
        """
        timestamp = str(int(time.time() * 1000))
        message = f"{method.upper()}{endpoint}{payload}{timestamp}"
        
        signature = hmac.new(
            self.credentials.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return {
            "API-KEY": self.credentials.api_key,
            "SIGNATURE": signature,
            "TIMESTAMP": timestamp,
            "CONTENT-TYPE": "application/json"
        }
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make an authenticated request to the API
        """
        await self.rate_limiter.wait_if_needed()
        
        url = f"{self.base_url}{endpoint}"
        payload = json.dumps(data) if data else ""
        
        headers = self._sign_request(method, endpoint, payload)
        
        if data:
            headers["CONTENT-TYPE"] = "application/json"
        
        async with self.session.request(
            method=method,
            url=url,
            headers=headers,
            json=data if data else None
        ) as response:
            response_data = await response.text()
            return json.loads(response_data)
    
    async def get_markets(self) -> Dict[str, Any]:
        """Get all available markets"""
        return await self._make_request("GET", "/markets")
    
    async def get_market(self, market_id: str) -> Dict[str, Any]:
        """Get specific market details"""
        return await self._make_request("GET", f"/markets/{market_id}")
    
    async def get_orderbook(self, market_id: str) -> Dict[str, Any]:
        """Get orderbook for a specific market"""
        return await self._make_request("GET", f"/markets/{market_id}/orderbook")
    
    async def place_order(self, order_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Place an order on the CLOB
        Expected params: marketId, side, price, quantity, type, etc.
        """
        return await self._make_request("POST", "/orders", order_params)
    
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel a specific order"""
        return await self._make_request("DELETE", f"/orders/{order_id}")
    
    async def get_orders(self, **filters) -> Dict[str, Any]:
        """Get list of orders with optional filters"""
        # Convert filters to query string
        query_params = "&".join([f"{k}={v}" for k, v in filters.items()])
        endpoint = f"/orders?{query_params}" if query_params else "/orders"
        return await self._make_request("GET", endpoint)
    
    async def get_balances(self) -> Dict[str, Any]:
        """Get account balances"""
        return await self._make_request("GET", "/balances")


class PolymarketWsClient:
    """
    WebSocket client for streaming Orderbook (L2) data from Polymarket
    """
    
    def __init__(self, credentials: Credentials, ws_url: str = "wss://clob.polymarket.com/ws"):
        self.credentials = credentials
        self.ws_url = ws_url
        self.websocket = None
        self.is_connected = False
        self.handlers = {}
        
    def register_handler(self, event_type: str, handler: Callable[[Dict], Awaitable[None]]):
        """Register a handler for specific event types"""
        self.handlers[event_type] = handler
        
    async def connect(self):
        """Connect to the WebSocket server"""
        self.websocket = await websockets.connect(self.ws_url)
        self.is_connected = True
        
        # Authenticate
        auth_message = {
            "type": "AUTH",
            "API-KEY": self.credentials.api_key,
            "SIGNATURE": self._generate_signature(),
            "TIMESTAMP": str(int(time.time() * 1000)),
            "PASSPHRASE": ""  # May be required depending on API
        }
        
        await self.websocket.send(json.dumps(auth_message))
        
        # Start listening for messages
        asyncio.create_task(self._listen())
        
    def _generate_signature(self) -> str:
        """Generate signature for WebSocket authentication"""
        timestamp = str(int(time.time() * 1000))
        message = f"websocket_auth_{timestamp}"
        signature = hmac.new(
            self.credentials.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def subscribe_to_orderbook(self, market_ids: list):
        """Subscribe to orderbook updates for specific markets"""
        subscription_message = {
            "type": "SUBSCRIBE",
            "channel": "l2_book",
            "market_ids": market_ids
        }
        await self.websocket.send(json.dumps(subscription_message))
    
    async def unsubscribe_from_orderbook(self, market_ids: list):
        """Unsubscribe from orderbook updates for specific markets"""
        subscription_message = {
            "type": "UNSUBSCRIBE",
            "channel": "l2_book",
            "market_ids": market_ids
        }
        await self.websocket.send(json.dumps(subscription_message))
    
    async def _listen(self):
        """Listen for incoming WebSocket messages"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                await self._handle_message(data)
        except websockets.exceptions.ConnectionClosed:
            print("WebSocket connection closed")
            self.is_connected = False
        except Exception as e:
            print(f"Error in WebSocket listener: {e}")
            self.is_connected = False
    
    async def _handle_message(self, message: Dict[str, Any]):
        """Handle incoming WebSocket messages"""
        msg_type = message.get("type", "unknown")
        
        if msg_type in self.handlers:
            await self.handlers[msg_type](message)
        elif "l2_book" in message.get("channel", ""):
            # Handle orderbook updates
            if "orderbook_update" in self.handlers:
                await self.handlers["orderbook_update"](message)
        else:
            print(f"Unhandled message type: {msg_type}, data: {message}")
    
    async def disconnect(self):
        """Disconnect from the WebSocket server"""
        if self.websocket:
            await self.websocket.close()
        self.is_connected = False