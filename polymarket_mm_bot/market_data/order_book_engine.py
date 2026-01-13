"""
Order Book Engine for maintaining real-time local order book mirror
"""
import asyncio
import json
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from decimal import Decimal
import threading
from collections import defaultdict, deque

from ..api.client import PolymarketWsClient, Credentials
from ..api.connection_manager import ConnectionManager


@dataclass
class OrderBookEntry:
    """Represents a single order book entry (price level)"""
    price: Decimal
    size: Decimal
    timestamp: float = field(default_factory=time.time)


@dataclass
class OrderBookSnapshot:
    """Complete snapshot of the order book"""
    bids: List[OrderBookEntry]  # Sorted in descending order (highest bid first)
    asks: List[OrderBookEntry]  # Sorted in ascending order (lowest ask first)
    sequence_number: int = 0
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        # Ensure bids are sorted in descending order
        self.bids.sort(key=lambda x: x.price, reverse=True)
        # Ensure asks are sorted in ascending order
        self.asks.sort(key=lambda x: x.price)


@dataclass
class OrderBookDelta:
    """Delta update for the order book"""
    market_id: str
    bids: List[OrderBookEntry]  # New bids or updated bids
    asks: List[OrderBookEntry]  # New asks or updated asks
    deletes: List[Dict[str, Decimal]]  # Entries to delete {price: side}
    sequence_number: int
    timestamp: float = field(default_factory=time.time)


class LocalOrderBook:
    """Maintains a local, real-time mirror of the order book for a specific market"""
    
    def __init__(self, market_id: str):
        self.market_id = market_id
        self.bids: Dict[Decimal, OrderBookEntry] = {}  # price -> OrderBookEntry
        self.asks: Dict[Decimal, OrderBookEntry] = {}  # price -> OrderBookEntry
        self.sequence_number = 0
        self.last_update_time = time.time()
        self._lock = threading.RLock()  # Thread-safe operations
        
    def apply_snapshot(self, snapshot: OrderBookSnapshot):
        """Apply a complete order book snapshot"""
        with self._lock:
            self.bids.clear()
            self.asks.clear()
            
            for bid in snapshot.bids:
                self.bids[bid.price] = bid
                
            for ask in snapshot.asks:
                self.asks[ask.price] = ask
                
            self.sequence_number = snapshot.sequence_number
            self.last_update_time = snapshot.timestamp
            
    def apply_delta(self, delta: OrderBookDelta):
        """Apply a delta update to the local order book"""
        with self._lock:
            # Apply deletions first
            for deletion in delta.deletes:
                price = deletion['price']
                side = deletion['side']  # 'bid' or 'ask'
                
                if side == 'bid':
                    self.bids.pop(price, None)
                elif side == 'ask':
                    self.asks.pop(price, None)
                    
            # Apply updates/additions
            for bid in delta.bids:
                if bid.size > 0:
                    self.bids[bid.price] = bid
                else:
                    # If size is 0, treat as deletion
                    self.bids.pop(bid.price, None)
                    
            for ask in delta.asks:
                if ask.size > 0:
                    self.asks[ask.price] = ask
                else:
                    # If size is 0, treat as deletion
                    self.asks.pop(ask.price, None)
                    
            self.sequence_number = delta.sequence_number
            self.last_update_time = delta.timestamp
            
    def get_best_bid(self) -> Optional[OrderBookEntry]:
        """Get the best bid (highest bid price)"""
        with self._lock:
            if not self.bids:
                return None
            best_price = max(self.bids.keys())
            return self.bids[best_price]
            
    def get_best_ask(self) -> Optional[OrderBookEntry]:
        """Get the best ask (lowest ask price)"""
        with self._lock:
            if not self.asks:
                return None
            best_price = min(self.asks.keys())
            return self.asks[best_price]
            
    def get_mid_price(self) -> Optional[Decimal]:
        """Calculate the current mid-price (average of best bid and ask)"""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        
        if best_bid and best_ask:
            return (best_bid.price + best_ask.price) / 2
        return None
        
    def get_spread(self) -> Optional[Decimal]:
        """Calculate the current spread (difference between best ask and best bid)"""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        
        if best_bid and best_ask:
            return best_ask.price - best_bid.price
        return None
        
    def get_order_book_state(self) -> OrderBookSnapshot:
        """Get current state of the order book"""
        with self._lock:
            bids_list = sorted(self.bids.values(), key=lambda x: x.price, reverse=True)
            asks_list = sorted(self.asks.values(), key=lambda x: x.price)
            
            return OrderBookSnapshot(
                bids=bids_list,
                asks=asks_list,
                sequence_number=self.sequence_number,
                timestamp=self.last_update_time
            )


class MarketDataIngestionEngine:
    """Main engine for subscribing to market data and maintaining local order book mirrors"""
    
    def __init__(self, credentials: Credentials, ws_url: str = "wss://clob.polymarket.com/ws"):
        self.credentials = credentials
        self.connection_manager = ConnectionManager(credentials, ws_url)
        self.local_order_books: Dict[str, LocalOrderBook] = {}
        self.delta_buffer: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))  # Buffer for each market
        self.is_running = False
        self.update_callbacks: Dict[str, List[Callable]] = defaultdict(list)
        self.mid_price_callbacks: Dict[str, List[Callable]] = defaultdict(list)
        self.spread_callbacks: Dict[str, List[Callable]] = defaultdict(list)
        
        # Register handlers
        self.connection_manager.register_handler("orderbook_update", self._handle_orderbook_update)
        
    async def start(self):
        """Start the market data ingestion engine"""
        self.is_running = True
        await self.connection_manager.start()
        
        # Start periodic calculations
        asyncio.create_task(self._periodic_calculations())
        
    async def stop(self):
        """Stop the market data ingestion engine"""
        self.is_running = False
        await self.connection_manager.stop()
        
    def subscribe_to_market(self, market_id: str):
        """Subscribe to a specific market for order book updates"""
        if market_id not in self.local_order_books:
            self.local_order_books[market_id] = LocalOrderBook(market_id)
            self.delta_buffer[market_id] = deque(maxlen=1000)
            
        # Subscribe via connection manager
        asyncio.create_task(self.connection_manager.subscribe_to_orderbook([market_id]))
        
    def unsubscribe_from_market(self, market_id: str):
        """Unsubscribe from a specific market"""
        if market_id in self.local_order_books:
            del self.local_order_books[market_id]
        if market_id in self.delta_buffer:
            del self.delta_buffer[market_id]
            
        # Unsubscribe via connection manager
        asyncio.create_task(self.connection_manager.unsubscribe_from_orderbook([market_id]))
        
    def register_update_callback(self, market_id: str, callback: Callable[[LocalOrderBook], None]):
        """Register a callback to be called when the order book for a market is updated"""
        self.update_callbacks[market_id].append(callback)
        
    def register_mid_price_callback(self, market_id: str, callback: Callable[[Decimal], None]):
        """Register a callback to be called when mid-price is calculated"""
        self.mid_price_callbacks[market_id].append(callback)
        
    def register_spread_callback(self, market_id: str, callback: Callable[[Decimal], None]):
        """Register a callback to be called when spread is calculated"""
        self.spread_callbacks[market_id].append(callback)
        
    async def _handle_orderbook_update(self, message: Dict[str, Any]):
        """Handle incoming order book update messages"""
        market_id = message.get('market_id')
        if not market_id or market_id not in self.local_order_books:
            return
            
        # Parse the update into a delta
        delta = self._parse_orderbook_delta(message, market_id)
        
        # Add to buffer
        self.delta_buffer[market_id].append(delta)
        
        # Apply the delta to the local order book
        local_book = self.local_order_books[market_id]
        local_book.apply_delta(delta)
        
        # Trigger callbacks for order book updates
        for callback in self.update_callbacks[market_id]:
            try:
                callback(local_book)
            except Exception as e:
                print(f"Error in update callback for {market_id}: {e}")
                
    def _parse_orderbook_delta(self, message: Dict[str, Any], market_id: str) -> OrderBookDelta:
        """Parse raw order book update message into an OrderBookDelta object"""
        # This parsing depends on the actual message format from Polymarket
        # For now, assuming a standard format
        bids_updates = []
        asks_updates = []
        deletes = []
        
        # Extract bids from message
        raw_bids = message.get('bids', [])
        for bid_data in raw_bids:
            price = Decimal(str(bid_data['price']))
            size = Decimal(str(bid_data['size']))
            bids_updates.append(OrderBookEntry(price=price, size=size))
            
        # Extract asks from message
        raw_asks = message.get('asks', [])
        for ask_data in raw_asks:
            price = Decimal(str(ask_data['price']))
            size = Decimal(str(ask_data['size']))
            asks_updates.append(OrderBookEntry(price=price, size=size))
            
        # Extract deletions if any
        raw_deletes = message.get('deletes', [])
        for delete_data in raw_deletes:
            price = Decimal(str(delete_data['price']))
            side = delete_data['side']
            deletes.append({'price': price, 'side': side})
            
        return OrderBookDelta(
            market_id=market_id,
            bids=bids_updates,
            asks=asks_updates,
            deletes=deletes,
            sequence_number=message.get('sequence', 0),
            timestamp=time.time()
        )
        
    async def _periodic_calculations(self):
        """Periodically calculate mid-price and spread every 100ms"""
        while self.is_running:
            start_time = time.time()
            
            for market_id, local_book in self.local_order_books.items():
                # Calculate mid-price
                mid_price = local_book.get_mid_price()
                if mid_price is not None:
                    for callback in self.mid_price_callbacks[market_id]:
                        try:
                            callback(mid_price)
                        except Exception as e:
                            print(f"Error in mid-price callback for {market_id}: {e}")
                            
                # Calculate spread
                spread = local_book.get_spread()
                if spread is not None:
                    for callback in self.spread_callbacks[market_id]:
                        try:
                            callback(spread)
                        except Exception as e:
                            print(f"Error in spread callback for {market_id}: {e}")
                            
            # Sleep for remaining time to achieve ~100ms interval
            elapsed = time.time() - start_time
            sleep_time = max(0.1 - elapsed, 0)  # 100ms = 0.1 seconds
            await asyncio.sleep(sleep_time)
            
    def get_local_order_book(self, market_id: str) -> Optional[LocalOrderBook]:
        """Get the local order book for a specific market"""
        return self.local_order_books.get(market_id)
        
    def get_current_mid_price(self, market_id: str) -> Optional[Decimal]:
        """Get the current mid-price for a specific market"""
        local_book = self.get_local_order_book(market_id)
        if local_book:
            return local_book.get_mid_price()
        return None
        
    def get_current_spread(self, market_id: str) -> Optional[Decimal]:
        """Get the current spread for a specific market"""
        local_book = self.get_local_order_book(market_id)
        if local_book:
            return local_book.get_spread()
        return None