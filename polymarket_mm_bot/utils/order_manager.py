"""
Order Manager for tracking and managing active orders in the market making bot.
Implements the order lifecycle and cancel-replace functionality.
"""
import asyncio
import logging
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime

from ..api.client import PolymarketRestClient
from ..strategies.hfmm_strategy import Order, OrderBatcher
from ..market_data.order_book_engine import LocalOrderBook


@dataclass
class ActiveOrder:
    """Represents an order that is currently active on the exchange"""
    order_id: str
    market_id: str
    side: str  # 'buy' or 'sell'
    price: Decimal
    size: Decimal
    placed_at: datetime
    original_order: Order  # Reference to the original strategy-generated order


class OrderManager:
    """
    Manages the lifecycle of orders including placement, tracking, cancellation, and replacement.
    """

    def __init__(self, rest_client: PolymarketRestClient, tick_interval_ms: int = 100, risk_manager=None):
        """
        Initialize the OrderManager.

        Args:
            rest_client: Instance of PolymarketRestClient for API interactions
            tick_interval_ms: Interval in milliseconds between ticks (order comparisons/replacements)
            risk_manager: Optional RiskManager instance for risk checks
        """
        self.rest_client = rest_client
        self.tick_interval_ms = tick_interval_ms
        self.risk_manager = risk_manager
        self.active_orders: Dict[str, ActiveOrder] = {}  # order_id -> ActiveOrder
        self.market_orders: Dict[str, Set[str]] = {}  # market_id -> set of order_ids
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self._lock = asyncio.Lock()  # Async lock for thread safety

    async def start(self):
        """Start the order manager"""
        self.is_running = True
        self.logger.info(f"OrderManager started with tick interval {self.tick_interval_ms}ms")

    async def stop(self):
        """Stop the order manager and cancel all active orders"""
        self.is_running = False
        await self.cancel_all_orders()
        self.logger.info("OrderManager stopped")

    async def place_orders(self, orders: List[Order]) -> List[ActiveOrder]:
        """
        Place a batch of orders on the exchange and track them.

        Args:
            orders: List of Order objects to place

        Returns:
            List of ActiveOrder objects representing the placed orders
        """
        if not orders:
            return []

        placed_orders = []

        # Place orders individually to track them properly
        for order in orders:
            # Perform risk checks if risk manager is available
            if self.risk_manager:
                # Get reference price for fat finger check
                # For now, we'll use the order's current price as a fallback
                reference_price = order.price

                # Perform risk checks
                is_safe, violations = self.risk_manager.check_order_risks(
                    market_id=order.market_id,
                    order_price=order.price,
                    reference_price=reference_price
                )

                if not is_safe:
                    self.logger.warning(
                        f"Risk check failed for order in market {order.market_id}, "
                        f"violations: {', '.join(violations)}. Order rejected."
                    )
                    continue  # Skip placing this order

            try:
                # Prepare order parameters for API
                order_params = {
                    'marketId': order.market_id,
                    'side': order.side,
                    'price': str(order.price),
                    'quantity': str(order.size),
                    'type': order.order_type,
                    'timeInForce': 'GTC'  # Good till cancelled
                }

                # Place the order
                response = await self.rest_client.place_order(order_params)

                # Check if the order was placed successfully
                if 'order_id' in response or 'orderId' in response:
                    order_id = response.get('order_id', response.get('orderId'))

                    active_order = ActiveOrder(
                        order_id=order_id,
                        market_id=order.market_id,
                        side=order.side,
                        price=order.price,
                        size=order.size,
                        placed_at=datetime.now(),
                        original_order=order
                    )

                    # Track the order
                    async with self._lock:
                        self.active_orders[order_id] = active_order
                        if order.market_id not in self.market_orders:
                            self.market_orders[order.market_id] = set()
                        self.market_orders[order.market_id].add(order_id)

                    placed_orders.append(active_order)
                    self.logger.info(f"Placed order {order_id} for {order.market_id}: "
                                   f"{order.side.upper()} {order.size} @ {order.price}")
                else:
                    self.logger.error(f"Failed to place order for {order.market_id}: {response}")

            except Exception as e:
                self.logger.error(f"Error placing order for {order.market_id}: {str(e)}")

        return placed_orders

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a specific order by ID.

        Args:
            order_id: ID of the order to cancel

        Returns:
            True if successful, False otherwise
        """
        try:
            response = await self.rest_client.cancel_order(order_id)
            
            # Check if cancellation was successful
            success = 'success' in response or 'status' in response
            
            if success:
                # Remove from tracking
                async with self._lock:
                    if order_id in self.active_orders:
                        active_order = self.active_orders[order_id]
                        # Remove from market-specific tracking
                        if active_order.market_id in self.market_orders:
                            self.market_orders[active_order.market_id].discard(order_id)
                        # Remove from global tracking
                        del self.active_orders[order_id]
                
                self.logger.info(f"Successfully cancelled order {order_id}")
                return True
            else:
                self.logger.error(f"Failed to cancel order {order_id}: {response}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error cancelling order {order_id}: {str(e)}")
            return False

    async def cancel_orders_for_market(self, market_id: str) -> bool:
        """
        Cancel all orders for a specific market.

        Args:
            market_id: ID of the market

        Returns:
            True if successful, False otherwise
        """
        order_ids_to_cancel = []
        
        async with self._lock:
            if market_id in self.market_orders:
                order_ids_to_cancel = list(self.market_orders[market_id])
        
        success_count = 0
        for order_id in order_ids_to_cancel:
            if await self.cancel_order(order_id):
                success_count += 1
        
        self.logger.info(f"Cancelled {success_count}/{len(order_ids_to_cancel)} orders for market {market_id}")
        return success_count == len(order_ids_to_cancel)

    async def cancel_all_orders(self) -> bool:
        """
        Cancel all active orders.

        Returns:
            True if all cancellations were successful, False otherwise
        """
        all_order_ids = []
        
        async with self._lock:
            all_order_ids = list(self.active_orders.keys())
        
        success_count = 0
        for order_id in all_order_ids:
            if await self.cancel_order(order_id):
                success_count += 1
        
        self.logger.info(f"Cancelled {success_count}/{len(all_order_ids)} total orders")
        return success_count == len(all_order_ids)

    async def get_active_orders_for_market(self, market_id: str) -> List[ActiveOrder]:
        """
        Get all active orders for a specific market.

        Args:
            market_id: ID of the market

        Returns:
            List of ActiveOrder objects
        """
        result = []
        async with self._lock:
            if market_id in self.market_orders:
                for order_id in self.market_orders[market_id]:
                    if order_id in self.active_orders:
                        result.append(self.active_orders[order_id])
        return result

    async def are_orders_stale(self, market_id: str, max_age_seconds: float = 30.0) -> bool:
        """
        Check if orders for a market are stale (older than max_age_seconds).

        Args:
            market_id: ID of the market
            max_age_seconds: Maximum age in seconds before orders are considered stale

        Returns:
            True if orders are stale, False otherwise
        """
        active_orders = await self.get_active_orders_for_market(market_id)
        if not active_orders:
            return False  # No orders, so not stale

        current_time = datetime.now()
        for active_order in active_orders:
            age = (current_time - active_order.placed_at).total_seconds()
            if age > max_age_seconds:
                return True

        return False

    async def should_replace_orders(self, market_id: str, current_orders: List[Order],
                             threshold: Decimal = Decimal('0.001')) -> bool:
        """
        Determine if existing orders should be replaced based on price differences.

        Args:
            market_id: ID of the market
            current_orders: New orders generated by the strategy
            threshold: Price difference threshold to trigger replacement

        Returns:
            True if orders should be replaced, False otherwise
        """
        existing_orders = await self.get_active_orders_for_market(market_id)

        # If no existing orders, we should place new ones
        if not existing_orders:
            return True

        # If no new orders from strategy, we should cancel existing ones
        if not current_orders:
            return True

        # Compare prices of existing vs new orders
        existing_buy_prices = {o.price for o in existing_orders if o.side == 'buy'}
        existing_sell_prices = {o.price for o in existing_orders if o.side == 'sell'}

        new_buy_prices = {o.price for o in current_orders if o.side == 'buy'}
        new_sell_prices = {o.price for o in current_orders if o.side == 'sell'}

        # Check if there are significant price differences
        for new_price in new_buy_prices:
            closest_existing = min(existing_buy_prices,
                                 key=lambda x: abs(x - new_price),
                                 default=None)
            if closest_existing and abs(new_price - closest_existing) > threshold:
                return True

        for new_price in new_sell_prices:
            closest_existing = min(existing_sell_prices,
                                 key=lambda x: abs(x - new_price),
                                 default=None)
            if closest_existing and abs(new_price - closest_existing) > threshold:
                return True

        # Check if order count has changed significantly
        if abs(len(existing_orders) - len(current_orders)) > 2:
            return True

        return False

    async def replace_orders_for_market(self, market_id: str, new_orders: List[Order]) -> bool:
        """
        Replace all orders for a market with new ones (cancel and replace pattern).

        Args:
            market_id: ID of the market
            new_orders: New orders to place

        Returns:
            True if successful, False otherwise
        """
        active_orders_count = await self.get_active_orders_for_market(market_id)
        self.logger.info(f"Replacing orders for market {market_id}. "
                        f"Cancelling {len(active_orders_count)} existing orders, "
                        f"placing {len(new_orders)} new orders")
        
        # First, cancel all existing orders for this market
        await self.cancel_orders_for_market(market_id)
        
        # Then place the new orders
        if new_orders:
            placed_orders = await self.place_orders(new_orders)
            success = len(placed_orders) == len(new_orders)
            if success:
                self.logger.info(f"Successfully replaced orders for market {market_id}")
            else:
                self.logger.warning(f"Only placed {len(placed_orders)}/{len(new_orders)} orders for market {market_id}")
            return success
        else:
            self.logger.info(f"No new orders to place for market {market_id}")
            return True

    async def run_event_loop(self, strategy, market_data_engine):
        """
        Main event loop that compares active orders with ideal orders and manages replacements.

        Args:
            strategy: The strategy instance that generates orders
            market_data_engine: The market data engine providing order book updates
        """
        self.logger.info("Starting order management event loop")
        
        while self.is_running:
            start_time = time.time()
            
            try:
                # Iterate through all markets we're tracking
                for market_id in list(self.market_orders.keys()):
                    # Get the current local order book for this market
                    local_book = market_data_engine.get_local_order_book(market_id)
                    if not local_book:
                        continue
                    
                    # Generate new ideal orders from the strategy
                    ideal_orders = strategy.generate_orders(market_id, local_book)
                    
                    # Check if we should replace existing orders
                    if (await self.are_orders_stale(market_id) or
                        await self.should_replace_orders(market_id, ideal_orders)):

                        # Replace orders (cancel and place new ones)
                        await self.replace_orders_for_market(market_id, ideal_orders)

                    # Also check periodically even if not stale to ensure alignment
                    elif (start_time % 5.0) < (self.tick_interval_ms / 1000.0):  # Every 5 seconds
                        # Just refresh to ensure alignment
                        await self.replace_orders_for_market(market_id, ideal_orders)
            
            except Exception as e:
                self.logger.error(f"Error in event loop iteration: {str(e)}")
            
            # Wait for the next tick, accounting for processing time
            elapsed = time.time() - start_time
            sleep_time = max((self.tick_interval_ms / 1000.0) - elapsed, 0)
            await asyncio.sleep(sleep_time)

    async def get_order_count_for_market(self, market_id: str) -> int:
        """
        Get the count of active orders for a specific market.

        Args:
            market_id: ID of the market

        Returns:
            Number of active orders for the market
        """
        active_orders = await self.get_active_orders_for_market(market_id)
        return len(active_orders)