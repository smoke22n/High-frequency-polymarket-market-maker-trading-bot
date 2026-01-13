"""
High Frequency Market Making (HFMM) Strategy Implementation

This module implements the core market making logic for the Polymarket bot,
including order generation, skew adjustment, and batch order placement.
"""
import math
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from ..market_data.order_book_engine import LocalOrderBook
from ..utils.position_manager import PositionManager, Position


@dataclass
class Order:
    """Represents a single order to be placed on the exchange"""
    market_id: str
    side: str  # 'buy' or 'sell'
    price: Decimal
    size: Decimal
    order_type: str = 'limit'


@dataclass
class SkewParameters:
    """Parameters for calculating position skew"""
    max_skew: Decimal = Decimal('0.1')  # Maximum skew (10%)
    skew_factor: Decimal = Decimal('2.0')  # How aggressively to adjust for skew


class HFMStrategy:
    """
    High Frequency Market Making Strategy
    
    Takes the Local Order Book and Inventory as inputs to generate limit orders
    that capture the spread while maintaining position neutrality.
    """

    def __init__(
        self,
        position_manager: PositionManager,
        target_spread: Decimal = Decimal('0.0020'),  # 20 basis points
        min_order_size: Decimal = Decimal('10'),
        max_order_size: Decimal = Decimal('1000'),
        num_levels: int = 5,
        skew_params: Optional[SkewParameters] = None
    ):
        """
        Initialize the HFMM strategy
        
        Args:
            position_manager: PositionManager instance to access inventory
            target_spread: Target spread to maintain (default 20 bps)
            min_order_size: Minimum order size allowed
            max_order_size: Maximum order size allowed
            num_levels: Number of price levels to quote on each side
            skew_params: Parameters for skew calculation
        """
        self.position_manager = position_manager
        self.target_spread = target_spread
        self.min_order_size = min_order_size
        self.max_order_size = max_order_size
        self.num_levels = num_levels
        self.skew_params = skew_params or SkewParameters()

    def calculate_skew(self, market_id: str) -> Decimal:
        """
        Calculate position skew for a market.
        
        If holding too many YES tokens, returns positive skew (raise asks, lower bids)
        If holding too many NO tokens, returns negative skew (lower asks, raise bids)
        
        Args:
            market_id: The market ID to calculate skew for
            
        Returns:
            Decimal: Skew factor (-1 to 1, where positive means overweight YES)
        """
        position = self.position_manager.get_position(market_id)
        if not position:
            return Decimal('0')

        total_tokens = position.yes_balance + position.no_balance
        
        if total_tokens == 0:
            return Decimal('0')
            
        # Calculate imbalance: positive if YES-heavy, negative if NO-heavy
        yes_ratio = position.yes_balance / total_tokens
        no_ratio = position.no_balance / total_tokens
        imbalance = yes_ratio - no_ratio  # Positive if YES-heavy, negative if NO-heavy
        
        # Clamp to max skew
        max_skew = self.skew_params.max_skew
        skew = max(min(imbalance, max_skew), -max_skew)
        
        return skew

    def adjust_prices_for_skew(
        self,
        mid_price: Decimal,
        skew: Decimal
    ) -> Tuple[Decimal, Decimal]:
        """
        Adjust bid and ask prices based on position skew.

        Args:
            mid_price: Current fair mid-price
            skew: Current position skew (-1 to 1)

        Returns:
            Tuple of (adjusted_bid_price, adjusted_ask_price)
        """
        # Calculate half of target spread
        half_spread = self.target_spread / 2

        # Calculate base bid and ask
        base_bid = mid_price - half_spread
        base_ask = mid_price + half_spread

        # Apply skew adjustment
        # The adjustment should be limited to prevent bid >= ask
        max_skew_adjustment = half_spread * Decimal('0.9')  # Keep it under half_spread to maintain bid < ask
        skew_adjustment = min(half_spread * abs(skew) * self.skew_params.skew_factor, max_skew_adjustment)

        if skew > 0:  # YES-heavy
            # Lower bid and raise ask to encourage selling YES and buying NO
            adjusted_bid = base_bid - skew_adjustment
            adjusted_ask = base_ask + skew_adjustment
        else:  # NO-heavy
            # Raise bid and lower ask to encourage selling NO and buying YES
            adjusted_bid = base_bid + skew_adjustment
            adjusted_ask = base_ask - skew_adjustment

        # Ensure prices are within valid bounds (0 to 1 for binary options)
        adjusted_bid = max(Decimal('0'), min(Decimal('1'), adjusted_bid))
        adjusted_ask = max(Decimal('0'), min(Decimal('1'), adjusted_ask))

        # Ensure bid < ask
        if adjusted_bid >= adjusted_ask:
            # If bid >= ask, center them around the mid_price with the target spread
            adjusted_bid = mid_price - half_spread
            adjusted_ask = mid_price + half_spread

        return adjusted_bid, adjusted_ask

    def calculate_order_sizes(self, market_id: str) -> Tuple[Decimal, Decimal]:
        """
        Calculate appropriate order sizes based on position.
        
        Args:
            market_id: The market ID to calculate sizes for
            
        Returns:
            Tuple of (bid_size, ask_size)
        """
        position = self.position_manager.get_position(market_id)
        
        # Base order size
        base_size = (self.min_order_size + self.max_order_size) / 2
        
        if not position:
            return base_size, base_size
            
        # Adjust sizes based on inventory to encourage rebalancing
        total_tokens = position.yes_balance + position.no_balance
        if total_tokens > 0:
            yes_ratio = position.yes_balance / total_tokens
            no_ratio = position.no_balance / total_tokens
            
            # If YES-heavy, increase ask size to sell YES tokens
            if yes_ratio > no_ratio:
                bid_size = base_size * (1 - (yes_ratio - no_ratio) / 2)
                ask_size = base_size * (1 + (yes_ratio - no_ratio) / 2)
            else:
                bid_size = base_size * (1 + (no_ratio - yes_ratio) / 2)
                ask_size = base_size * (1 - (no_ratio - yes_ratio) / 2)
                
            # Ensure sizes are within bounds
            bid_size = max(self.min_order_size, min(self.max_order_size, bid_size))
            ask_size = max(self.min_order_size, min(self.max_order_size, ask_size))
        else:
            bid_size = base_size
            ask_size = base_size
            
        return bid_size, ask_size

    def generate_orders(
        self,
        market_id: str,
        local_order_book: LocalOrderBook
    ) -> List[Order]:
        """
        Generate a batch of limit orders to place based on current market conditions.
        
        Args:
            market_id: The market ID to generate orders for
            local_order_book: Current local order book state
            
        Returns:
            List of Order objects to place
        """
        orders = []
        
        # Get current mid-price from the local order book
        mid_price = local_order_book.get_mid_price()
        if not mid_price:
            return orders  # Can't generate orders without a mid-price
            
        # Calculate skew for this market
        skew = self.calculate_skew(market_id)
        
        # Adjust prices for skew
        bid_price, ask_price = self.adjust_prices_for_skew(mid_price, skew)
        
        # Calculate order sizes
        bid_size, ask_size = self.calculate_order_sizes(market_id)
        
        # Generate orders at multiple price levels
        for i in range(self.num_levels):
            # Calculate price levels with increasing depth
            level_multiplier = Decimal('1.0') + (Decimal(str(i)) * Decimal('0.001'))  # 10 bp increments
            
            # Calculate bid and ask prices for this level
            level_bid_price = bid_price - (self.target_spread * level_multiplier * Decimal('0.5'))
            level_ask_price = ask_price + (self.target_spread * level_multiplier * Decimal('0.5'))
            
            # Clamp prices to valid range
            level_bid_price = max(Decimal('0'), min(Decimal('1'), level_bid_price))
            level_ask_price = max(Decimal('0'), min(Decimal('1'), level_ask_price))
            
            # Ensure bid < ask
            if level_bid_price >= level_ask_price:
                continue
                
            # Add bid order if size is sufficient
            if bid_size >= self.min_order_size:
                orders.append(Order(
                    market_id=market_id,
                    side='buy',
                    price=self._round_price(level_bid_price),
                    size=self._round_size(bid_size / (i + 1)),  # Reduce size for deeper levels
                    order_type='limit'
                ))
                
            # Add ask order if size is sufficient
            if ask_size >= self.min_order_size:
                orders.append(Order(
                    market_id=market_id,
                    side='sell',
                    price=self._round_price(level_ask_price),
                    size=self._round_size(ask_size / (i + 1)),  # Reduce size for deeper levels
                    order_type='limit'
                ))
        
        return orders

    def _round_price(self, price: Decimal) -> Decimal:
        """Round price to appropriate precision for Polymarket"""
        return price.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    def _round_size(self, size: Decimal) -> Decimal:
        """Round size to appropriate precision"""
        return size.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class OrderBatcher:
    """
    Utility class to batch orders for efficient placement via POST /orders endpoint
    """
    
    def __init__(self, max_batch_size: int = 100):
        """
        Initialize the order batcher
        
        Args:
            max_batch_size: Maximum number of orders per batch
        """
        self.max_batch_size = max_batch_size

    def batch_orders(self, orders: List[Order]) -> List[List[Dict]]:
        """
        Convert Order objects to API-compatible dictionaries and batch them
        
        Args:
            orders: List of Order objects to batch
            
        Returns:
            List of batches, where each batch is a list of order dictionaries
        """
        # Convert Order objects to API-compatible dictionaries
        order_dicts = []
        for order in orders:
            order_dict = {
                'market_id': order.market_id,
                'side': order.side,
                'price': str(order.price),
                'size': str(order.size),
                'type': order.order_type
            }
            order_dicts.append(order_dict)
        
        # Split into batches
        batches = []
        for i in range(0, len(order_dicts), self.max_batch_size):
            batch = order_dicts[i:i + self.max_batch_size]
            batches.append(batch)
            
        return batches