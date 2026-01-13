"""
Risk Manager module for implementing safety guardrails in the Polymarket MM bot.

This module implements three key risk management features:
1. Max Exposure: Limits total inventory exposure
2. Kill Switch: Shuts down the bot if losses exceed threshold
3. Fat Finger Check: Prevents orders that deviate too much from market prices
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass, field

from .position_manager import PositionManager
from ..market_data.order_book_engine import LocalOrderBook


@dataclass
class RiskMetrics:
    """Data class to store current risk metrics"""
    total_exposure: Decimal = Decimal('0')
    current_balance: Decimal = Decimal('0')
    starting_balance: Decimal = Decimal('0')
    loss_percentage: Decimal = Decimal('0')
    last_hour_losses: Decimal = Decimal('0')


class RiskManager:
    """
    Risk management module that implements safety guardrails before any order is sent.
    
    Features:
    1. Max Exposure: If total inventory (YES + NO - Hedged sets) exceeds $1000, reject new open orders
    2. Kill Switch: If the bot loses more than X% of the starting balance in one hour, 
       immediately cancel all orders and shut down
    3. Fat Finger Check: Prevent orders that deviate more than 5% from the last traded price 
       or the best external reference price
    """

    def __init__(
        self,
        position_manager: PositionManager,
        max_exposure: Decimal = Decimal('1000'),
        kill_switch_threshold: Decimal = Decimal('0.10'),  # 10% loss
        fat_finger_threshold: Decimal = Decimal('0.05'),   # 5% deviation
        starting_balance: Decimal = Decimal('10000')       # Starting balance assumption
    ):
        """
        Initialize the RiskManager.

        Args:
            position_manager: PositionManager instance to access inventory
            max_exposure: Maximum total inventory exposure allowed
            kill_switch_threshold: Percentage threshold for kill switch (e.g., 0.10 for 10%)
            fat_finger_threshold: Percentage threshold for fat finger check (e.g., 0.05 for 5%)
            starting_balance: Assumed starting balance for loss calculations
        """
        self.position_manager = position_manager
        self.max_exposure = max_exposure
        self.kill_switch_threshold = kill_switch_threshold
        self.fat_finger_threshold = fat_finger_threshold
        self.starting_balance = starting_balance
        
        self.logger = logging.getLogger(__name__)
        self.last_balance_check_time = datetime.now()
        self.hourly_loss_tracker = {
            'start_time': datetime.now(),
            'losses_in_period': Decimal('0'),
            'current_balance': starting_balance
        }
        
        # Track historical prices for fat finger detection
        self.price_history: Dict[str, List[Tuple[datetime, Decimal]]] = {}

    def calculate_total_inventory_exposure(self) -> Decimal:
        """
        Calculate total inventory exposure across all positions.
        Formula: Sum of (YES + NO - Hedged sets) for all markets.

        Returns:
            Total exposure as a Decimal
        """
        total_exposure = Decimal('0')
        
        for market_id, position in self.position_manager.positions.items():
            # Calculate unhedged exposure for this market
            # For now, assuming "hedged sets" refers to the minimum of YES and NO balances
            # which represents the portion that is hedged
            hedged_sets = min(position.yes_balance, position.no_balance)
            unhedged_exposure = (position.yes_balance + position.no_balance) - hedged_sets
            total_exposure += unhedged_exposure
            
        return total_exposure

    def is_max_exposure_exceeded(self) -> bool:
        """
        Check if the total inventory exposure exceeds the maximum allowed.

        Returns:
            True if max exposure is exceeded, False otherwise
        """
        current_exposure = self.calculate_total_inventory_exposure()
        is_exceeded = current_exposure > self.max_exposure
        
        if is_exceeded:
            self.logger.warning(
                f"Max exposure exceeded: Current exposure ${current_exposure} > "
                f"Max allowed ${self.max_exposure}"
            )
        
        return is_exceeded

    def update_balance_and_check_kill_switch(self, current_balance: Decimal) -> bool:
        """
        Update balance tracking and check if kill switch should be triggered.

        Args:
            current_balance: Current account balance

        Returns:
            True if kill switch should be triggered, False otherwise
        """
        # Update the hourly loss tracker
        current_time = datetime.now()
        time_diff = current_time - self.hourly_loss_tracker['start_time']
        
        # If more than an hour has passed, reset the tracker
        if time_diff.total_seconds() > 3600:
            self.hourly_loss_tracker['start_time'] = current_time
            self.hourly_loss_tracker['losses_in_period'] = self.starting_balance - current_balance
        else:
            # Update losses in the current period
            self.hourly_loss_tracker['losses_in_period'] = (
                self.hourly_loss_tracker['current_balance'] - current_balance
            )
        
        self.hourly_loss_tracker['current_balance'] = current_balance
        
        # Calculate loss percentage
        if self.starting_balance > 0:
            loss_percentage = self.hourly_loss_tracker['losses_in_period'] / self.starting_balance
        else:
            loss_percentage = Decimal('0')
            
        # Check if loss threshold is exceeded
        kill_switch_triggered = loss_percentage > self.kill_switch_threshold
        
        if kill_switch_triggered:
            self.logger.critical(
                f"Kill switch triggered! Losses in last hour: "
                f"${self.hourly_loss_tracker['losses_in_period']} "
                f"({loss_percentage * 100:.2f}%) exceeds threshold "
                f"of {self.kill_switch_threshold * 100:.2f}%"
            )
        
        return kill_switch_triggered

    def is_fat_finger_detected(
        self, 
        market_id: str, 
        order_price: Decimal, 
        reference_price: Optional[Decimal] = None
    ) -> bool:
        """
        Check if an order price deviates more than the threshold from reference prices.

        Args:
            market_id: The market ID for the order
            order_price: The price of the order being placed
            reference_price: External reference price (if available)

        Returns:
            True if fat finger detected (deviation exceeds threshold), False otherwise
        """
        # If no reference price is provided, try to get the last known price for this market
        if reference_price is None:
            last_known_price = self.get_last_known_price(market_id)
            if last_known_price is None:
                # If no reference price available, we can't perform the check
                # In this case, we'll allow the order to proceed but log a warning
                self.logger.warning(
                    f"No reference price available for market {market_id}, "
                    f"skipping fat finger check for order at price {order_price}"
                )
                return False
            reference_price = last_known_price

        # Calculate the percentage deviation
        if reference_price != 0:
            deviation = abs(order_price - reference_price) / reference_price
        else:
            # If reference price is 0, any non-zero order price is a huge deviation
            deviation = Decimal('1.0') if order_price != 0 else Decimal('0')

        is_fat_finger = deviation > self.fat_finger_threshold

        if is_fat_finger:
            self.logger.warning(
                f"Fat finger detected for market {market_id}: "
                f"Order price {order_price} deviates {deviation * 100:.2f}% "
                f"from reference price {reference_price} (threshold: {self.fat_finger_threshold * 100:.2f}%)"
            )

        return is_fat_finger

    def get_last_known_price(self, market_id: str) -> Optional[Decimal]:
        """
        Get the last known price for a market from the price history.

        Args:
            market_id: The market ID

        Returns:
            Last known price or None if not available
        """
        if market_id in self.price_history and self.price_history[market_id]:
            # Return the most recent price
            return self.price_history[market_id][-1][1]
        return None

    def update_price_history(self, market_id: str, price: Decimal):
        """
        Update the price history for a market.

        Args:
            market_id: The market ID
            price: The new price to record
        """
        if market_id not in self.price_history:
            self.price_history[market_id] = []
        
        # Add the current timestamp and price
        self.price_history[market_id].append((datetime.now(), price))
        
        # Keep only the last 100 price points to avoid memory issues
        if len(self.price_history[market_id]) > 100:
            self.price_history[market_id] = self.price_history[market_id][-100:]

    def check_order_risks(
        self,
        market_id: str,
        order_price: Decimal,
        reference_price: Optional[Decimal] = None,
        current_balance: Optional[Decimal] = None
    ) -> Tuple[bool, List[str]]:
        """
        Perform all risk checks for a potential order.

        Args:
            market_id: The market ID for the order
            order_price: The price of the order being placed
            reference_price: External reference price (if available)
            current_balance: Current account balance (if available)

        Returns:
            Tuple of (is_safe, list_of_violated_rules)
        """
        violations = []
        
        # Check 1: Max Exposure
        if self.is_max_exposure_exceeded():
            violations.append("Max exposure exceeded")
        
        # Check 2: Kill Switch (only if current balance is provided)
        if current_balance is not None:
            if self.update_balance_and_check_kill_switch(current_balance):
                violations.append("Kill switch threshold exceeded")
        
        # Check 3: Fat Finger
        if self.is_fat_finger_detected(market_id, order_price, reference_price):
            violations.append("Fat finger detected - price deviation too high")
        
        is_safe = len(violations) == 0
        
        if not is_safe:
            self.logger.warning(f"Order risk check failed for market {market_id}: {', '.join(violations)}")
        
        return is_safe, violations

    def should_shutdown_immediately(self) -> bool:
        """
        Check if the bot should shut down immediately due to risk violations.

        Returns:
            True if immediate shutdown is required, False otherwise
        """
        # Check if kill switch threshold has been exceeded
        if self.hourly_loss_tracker['losses_in_period'] / self.starting_balance > self.kill_switch_threshold:
            return True
        return False

    def get_risk_metrics(self) -> RiskMetrics:
        """
        Get current risk metrics.

        Returns:
            RiskMetrics object with current metrics
        """
        total_exposure = self.calculate_total_inventory_exposure()
        
        # For now, we'll return a basic metrics object
        # In a real implementation, current_balance would come from the exchange
        return RiskMetrics(
            total_exposure=total_exposure,
            current_balance=self.hourly_loss_tracker['current_balance'],
            starting_balance=self.starting_balance,
            loss_percentage=(
                self.hourly_loss_tracker['losses_in_period'] / self.starting_balance
                if self.starting_balance > 0 else Decimal('0')
            ),
            last_hour_losses=self.hourly_loss_tracker['losses_in_period']
        )