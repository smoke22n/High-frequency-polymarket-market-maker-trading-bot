"""
Market Data Ingestion Engine
Maintains a real-time local mirror of the order book for specific market IDs
"""
import asyncio
import json
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from decimal import Decimal
import logging
from collections import defaultdict, deque

from ..api.client import PolymarketWsClient, Credentials
from ..api.connection_manager import ConnectionManager


@dataclass
class OrderBookEntry:
    """Represents a single price level in the order book"""
    price: Decimal
    size: Decimal
    timestamp: float = field(default_factory=time.time)


@dataclass
class LocalOrderBook:
    """Local representation of the order book"""
    market_id: str
    bids: Dict[Decimal, OrderBookEntry] = field(default_factory=dict)
    asks: Dict[Decimal, OrderBookEntry] = field(default_factory=dict)
    last_update_time: float = field(default_factory=time.time)

    def apply_delta(self, delta: Dict[str, Any]):
        """Apply a delta update to the order book"""
        # Process bid updates
        bid_updates = delta.get('bids', [])
        for bid_update in bid_updates:
            price = Decimal(str(bid_update['price']))
            size = Decimal(str(bid_update['size']))
            
            if size > 0:
                # Update or add bid level
                self.bids[price] = OrderBookEntry(price=price, size=size)
            else:
                # Remove bid level if size is 0
                if price in self.bids:
                    del self.bids[price]

        # Process ask updates
        ask_updates = delta.get('asks', [])
        for ask_update in ask_updates:
            price = Decimal(str(ask_update['price']))
            size = Decimal(str(ask_update['size']))
            
            if size > 0:
                # Update or add ask level
                self.asks[price] = OrderBookEntry(price=price, size=size)
            else:
                # Remove ask level if size is 0
                if price in self.asks:
                    del self.asks[price]

        self.last_update_time = time.time()

    def get_top_of_book(self) -> tuple[Optional[OrderBookEntry], Optional[OrderBookEntry]]:
        """Get the best bid and ask prices"""
        best_bid = max(self.bids.values(), key=lambda x: x.price) if self.bids else None
        best_ask = min(self.asks.values(), key=lambda x: x.price) if self.asks else None
        return best_bid, best_ask

    def calculate_mid_price(self) -> Optional[Decimal]:
        """Calculate the current mid-price"""
        best_bid, best_ask = self.get_top_of_book()
        if best_bid and best_ask:
            return (best_bid.price + best_ask.price) / 2
        return None

    def calculate_spread(self) -> Optional[Decimal]:
        """Calculate the current spread"""
        best_bid, best_ask = self.get_top_of_book()
        if best_bid and best_ask:
            return best_ask.price - best_bid.price
        return None

    def calculate_spread_percentage(self) -> Optional[Decimal]:
        """Calculate the current spread as percentage of mid-price"""
        mid_price = self.calculate_mid_price()
        spread = self.calculate_spread()
        
        if mid_price and spread and mid_price > 0:
            return (spread / mid_price) * 100
        return None


@dataclass
class OrderBookDelta:
    """Represents a delta update to the order book"""
    market_id: str
    bids: List[Dict[str, float]]  # List of {price: float, size: float}
    asks: List[Dict[str, float]]  # List of {price: float, size: float}
    timestamp: float = field(default_factory=time.time)


class MarketDataIngestionEngine:
    """
    Market Data Ingestion Engine
    Subscribes to WebSocket channels, buffers delta updates, and maintains local order books
    """
    
    def __init__(self, credentials: Credentials, ws_url: str = "wss://clob.polymarket.com/ws"):
        self.credentials = credentials
        self.ws_url = ws_url
        self.connection_manager = ConnectionManager(credentials, ws_url)
        self.order_books: Dict[str, LocalOrderBook] = {}
        self.delta_buffer: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))  # Buffer up to 1000 deltas per market
        self.is_running = False
        self.update_callbacks: Dict[str, List[Callable]] = defaultdict(list)
        self.logger = logging.getLogger(__name__)
        
        # Register handlers for WebSocket messages
        self.connection_manager.register_handler("orderbook_update", self._handle_orderbook_update)

    async def start(self):
        """Start the market data ingestion engine"""
        self.is_running = True
        
        # Start the connection manager
        await self.connection_manager.start()
        
        # Start the periodic calculation task
        asyncio.create_task(self._periodic_calculations())

    async def stop(self):
        """Stop the market data ingestion engine"""
        self.is_running = False
        await self.connection_manager.stop()

    async def subscribe_to_market(self, market_id: str):
        """Subscribe to order book updates for a specific market"""
        await self.connection_manager.subscribe_to_orderbook([market_id])
        
        # Initialize local order book for this market
        if market_id not in self.order_books:
            self.order_books[market_id] = LocalOrderBook(market_id=market_id)

    async def unsubscribe_from_market(self, market_id: str):
        """Unsubscribe from order book updates for a specific market"""
        await self.connection_manager.unsubscribe_from_orderbook([market_id])
        
        # Remove local order book for this market
        if market_id in self.order_books:
            del self.order_books[market_id]

    def register_update_callback(self, market_id: str, callback: Callable[[str, LocalOrderBook], None]):
        """Register a callback to be called when the order book for a market is updated"""
        self.update_callbacks[market_id].append(callback)

    async def _handle_orderbook_update(self, message: Dict[str, Any]):
        """Handle incoming order book update messages"""
        try:
            market_id = message.get('market_id')
            if not market_id:
                self.logger.warning("Received orderbook update without market_id")
                return

            # Create delta object from the message
            delta = OrderBookDelta(
                market_id=market_id,
                bids=message.get('bids', []),
                asks=message.get('asks', []),
                timestamp=time.time()
            )

            # Add to buffer
            self.delta_buffer[market_id].append(delta)

            # Apply delta to local order book
            if market_id in self.order_books:
                self.order_books[market_id].apply_delta({
                    'bids': delta.bids,
                    'asks': delta.asks
                })

                # Call registered callbacks
                for callback in self.update_callbacks[market_id]:
                    try:
                        callback(market_id, self.order_books[market_id])
                    except Exception as e:
                        self.logger.error(f"Error in callback for market {market_id}: {e}")

        except Exception as e:
            self.logger.error(f"Error processing orderbook update: {e}")

    async def _periodic_calculations(self):
        """Periodically calculate mid-price and spread every 100ms"""
        while self.is_running:
            try:
                for market_id, order_book in self.order_books.items():
                    mid_price = order_book.calculate_mid_price()
                    spread = order_book.calculate_spread()
                    
                    # Log calculations if they exist
                    if mid_price is not None and spread is not None:
                        self.logger.debug(
                            f"Market {market_id}: Mid-price: {mid_price}, "
                            f"Spread: {spread}, Spread %: {order_book.calculate_spread_percentage()}"
                        )
                
                # Wait 100ms before next calculation
                await asyncio.sleep(0.1)
                
            except Exception as e:
                self.logger.error(f"Error in periodic calculations: {e}")
                await asyncio.sleep(0.1)  # Still wait before next iteration

    def get_order_book(self, market_id: str) -> Optional[LocalOrderBook]:
        """Get the current order book for a specific market"""
        return self.order_books.get(market_id)

    def get_market_metrics(self, market_id: str) -> Dict[str, Optional[Decimal]]:
        """Get calculated metrics for a specific market"""
        order_book = self.get_order_book(market_id)
        if not order_book:
            return {
                'mid_price': None,
                'spread': None,
                'spread_percentage': None
            }
        
        return {
            'mid_price': order_book.calculate_mid_price(),
            'spread': order_book.calculate_spread(),
            'spread_percentage': order_book.calculate_spread_percentage()
        }

    def get_all_markets_metrics(self) -> Dict[str, Dict[str, Optional[Decimal]]]:
        """Get calculated metrics for all tracked markets"""
        metrics = {}
        for market_id in self.order_books.keys():
            metrics[market_id] = self.get_market_metrics(market_id)
        return metrics