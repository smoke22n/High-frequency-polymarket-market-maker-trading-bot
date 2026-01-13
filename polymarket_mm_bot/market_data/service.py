"""
Market Data Service
Manages the lifecycle of the market data ingestion engine
"""
import asyncio
import logging
from typing import Dict, List, Optional, Callable

from ..api.client import Credentials
from .engine import MarketDataIngestionEngine, LocalOrderBook


class MarketDataService:
    """
    Service layer for market data ingestion
    Provides a clean interface for subscribing to markets and accessing order book data
    """
    
    def __init__(self, credentials: Credentials, ws_url: str = "wss://clob.polymarket.com/ws"):
        self.credentials = credentials
        self.engine = MarketDataIngestionEngine(credentials, ws_url)
        self.logger = logging.getLogger(__name__)

    async def start(self):
        """Start the market data service"""
        self.logger.info("Starting market data service...")
        await self.engine.start()
        self.logger.info("Market data service started successfully")

    async def stop(self):
        """Stop the market data service"""
        self.logger.info("Stopping market data service...")
        await self.engine.stop()
        self.logger.info("Market data service stopped")

    async def subscribe_to_market(self, market_id: str):
        """Subscribe to a specific market"""
        self.logger.info(f"Subscribing to market: {market_id}")
        await self.engine.subscribe_to_market(market_id)

    async def unsubscribe_from_market(self, market_id: str):
        """Unsubscribe from a specific market"""
        self.logger.info(f"Unsubscribing from market: {market_id}")
        await self.engine.unsubscribe_from_market(market_id)

    def register_update_callback(self, market_id: str, callback: Callable[[str, LocalOrderBook], None]):
        """Register a callback for order book updates"""
        self.engine.register_update_callback(market_id, callback)

    def get_order_book(self, market_id: str) -> Optional[LocalOrderBook]:
        """Get the current order book for a market"""
        return self.engine.get_order_book(market_id)

    def get_market_metrics(self, market_id: str) -> Dict[str, Optional[float]]:
        """Get calculated metrics for a market (converted to float for easier use)"""
        metrics = self.engine.get_market_metrics(market_id)
        
        # Convert Decimal values to float for easier consumption
        result = {}
        for key, value in metrics.items():
            if value is not None:
                result[key] = float(value)
            else:
                result[key] = None
                
        return result

    def get_all_markets_metrics(self) -> Dict[str, Dict[str, Optional[float]]]:
        """Get calculated metrics for all tracked markets"""
        all_metrics = self.engine.get_all_markets_metrics()
        
        # Convert Decimal values to float for easier consumption
        result = {}
        for market_id, metrics in all_metrics.items():
            result[market_id] = {}
            for key, value in metrics.items():
                if value is not None:
                    result[market_id][key] = float(value)
                else:
                    result[market_id][key] = None
                    
        return result

    def get_top_of_book(self, market_id: str) -> tuple:
        """Get the best bid and ask for a market"""
        order_book = self.get_order_book(market_id)
        if order_book:
            return order_book.get_top_of_book()
        return None, None