"""
Position Manager for managing YES/NO token positions in Polymarket.
Implements hedging mechanisms using the Conditional Token Framework (CTF).
"""

import logging
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass
from decimal import Decimal
from ..api.blockchain_client import PolymarketCTFApiClient
from .proxy_wallet import ProxyWallet, TransactionData


@dataclass
class Position:
    """Represents a position in a specific market with YES and NO token balances."""
    market_id: str
    yes_balance: Decimal
    no_balance: Decimal
    collateral_token_address: str
    condition_id: str


class PositionManager:
    """
    Manages positions in conditional token markets.
    Tracks YES and NO token balances for specific markets.
    """

    def __init__(self,
                 api_client: PolymarketCTFApiClient,
                 proxy_wallet: Optional[ProxyWallet] = None,
                 proxy_wallet_address: Optional[str] = None):
        """
        Initialize the PositionManager.

        Args:
            api_client: Instance of PolymarketCTFApiClient for blockchain interactions
            proxy_wallet: Optional ProxyWallet instance for gas-efficient transactions
            proxy_wallet_address: Optional address of a proxy wallet for gas-efficient transactions
        """
        self.api_client = api_client
        self.proxy_wallet = proxy_wallet
        self.proxy_wallet_address = proxy_wallet_address
        self.positions: Dict[str, Position] = {}
        self.logger = logging.getLogger(__name__)
        
    def track_position(self, market_id: str, yes_balance: Decimal, no_balance: Decimal, 
                      collateral_token_address: str, condition_id: str) -> None:
        """
        Track a position for a specific market.
        
        Args:
            market_id: Unique identifier for the market
            yes_balance: Amount of YES tokens held
            no_balance: Amount of NO tokens held
            collateral_token_address: Address of the collateral token (USDC)
            condition_id: Condition ID for the market in CTF
        """
        position = Position(
            market_id=market_id,
            yes_balance=yes_balance,
            no_balance=no_balance,
            collateral_token_address=collateral_token_address,
            condition_id=condition_id
        )
        self.positions[market_id] = position
        self.logger.info(f"Tracking position for market {market_id}: "
                        f"YES: {yes_balance}, NO: {no_balance}")
        
    def get_position(self, market_id: str) -> Optional[Position]:
        """
        Get the current position for a specific market.
        
        Args:
            market_id: Unique identifier for the market
            
        Returns:
            Position object or None if not found
        """
        return self.positions.get(market_id)
        
    def update_position_balances(self, market_id: str, yes_delta: Decimal = Decimal(0), 
                                no_delta: Decimal = Decimal(0)) -> bool:
        """
        Update the balances for a specific market position.
        
        Args:
            market_id: Unique identifier for the market
            yes_delta: Change in YES token balance (can be negative)
            no_delta: Change in NO token balance (can be negative)
            
        Returns:
            True if update was successful, False otherwise
        """
        if market_id not in self.positions:
            self.logger.error(f"No position found for market {market_id}")
            return False
            
        position = self.positions[market_id]
        new_yes_balance = position.yes_balance + yes_delta
        new_no_balance = position.no_balance + no_delta
        
        # Ensure balances don't go negative
        if new_yes_balance < 0 or new_no_balance < 0:
            self.logger.error(f"Invalid update: would result in negative balance for market {market_id}")
            return False
            
        position.yes_balance = new_yes_balance
        position.no_balance = new_no_balance
        
        self.logger.info(f"Updated position for market {market_id}: "
                        f"YES: {position.yes_balance}, NO: {position.no_balance}")
        return True
        
    def get_hedgeable_amount(self, market_id: str) -> Decimal:
        """
        Get the amount that can be hedged (minimum of YES and NO balances).
        
        Args:
            market_id: Unique identifier for the market
            
        Returns:
            Amount that can be hedged (in tokens)
        """
        position = self.get_position(market_id)
        if not position:
            return Decimal(0)
            
        return min(position.yes_balance, position.no_balance)
        
    def get_net_exposure(self, market_id: str) -> Tuple[Decimal, str]:
        """
        Get the net exposure for a market (difference between YES and NO).

        Args:
            market_id: Unique identifier for the market

        Returns:
            Tuple of (exposure_amount, direction) where direction is 'YES' or 'NO'
        """
        position = self.get_position(market_id)
        if not position:
            return Decimal(0), 'NO'

        if position.yes_balance > position.no_balance:
            return position.yes_balance - position.no_balance, 'YES'
        elif position.no_balance > position.yes_balance:
            return position.no_balance - position.yes_balance, 'NO'
        else:
            return Decimal(0), 'NO'  # Neutral when balances are equal

    async def merge_positions(self, market_id: str, amount: Optional[Decimal] = None) -> bool:
        """
        Merge equal amounts of YES and NO tokens into USDC (collateral).
        This is the primary hedging mechanism.

        Args:
            market_id: Unique identifier for the market
            amount: Amount of each token to merge (defaults to minimum of YES/NO balances)

        Returns:
            True if successful, False otherwise
        """
        position = self.get_position(market_id)
        if not position:
            self.logger.error(f"No position found for market {market_id}")
            return False

        # Determine how many tokens to merge
        if amount is None:
            amount = self.get_hedgeable_amount(market_id)
        else:
            # Ensure we don't try to merge more than we have
            max_mergeable = self.get_hedgeable_amount(market_id)
            if amount > max_mergeable:
                self.logger.warning(f"Requested to merge {amount}, but only {max_mergeable} available. "
                                  f"Merging {max_mergeable} instead.")
                amount = max_mergeable

        if amount <= 0:
            self.logger.info(f"No tokens to merge for market {market_id}")
            return True  # Not an error, just nothing to do

        try:
            # Prepare transaction data for merging positions
            # This would typically involve encoding the function call to the CTF contract
            # For now, we'll simulate the transaction data
            function_signature = "redeemPositions(bytes32,address,uint256,uint256[])"
            # Note: Actual implementation would require proper ABI encoding

            # Use proxy wallet if available for gas-efficient transactions
            if self.proxy_wallet:
                # Prepare transaction data for the proxy wallet
                tx_data = TransactionData(
                    to=self.api_client.ctf_exchange_contract_address,
                    value=0,
                    data=f"0x{function_signature}",  # This would be the actual encoded data
                    gas_limit=200000  # Estimated gas limit
                )

                # Send transaction via proxy wallet
                tx_hash = await self.proxy_wallet.send_transaction_via_relayer(tx_data)
            else:
                # Fallback to direct transaction
                tx_call_data = {
                    'condition_id': position.condition_id,
                    'collateral_token': position.collateral_token_address,
                    'amount': str(amount),
                    'index_set': [0, 1]  # Assuming binary market with 2 outcomes
                }

                sender_address = self.proxy_wallet_address or self.api_client.wallet_address
                tx_hash = await self.api_client.send_transaction(
                    contract_address=self.api_client.ctf_exchange_contract_address,
                    function_name='redeemPositions',
                    args=[tx_call_data],
                    from_address=sender_address
                )

            if tx_hash:
                # Update position balances after successful merge
                success = self.update_position_balances(
                    market_id,
                    yes_delta=-amount,
                    no_delta=-amount
                )

                if success:
                    self.logger.info(f"Successfully merged {amount} YES and {amount} NO tokens "
                                   f"for market {market_id}. Transaction: {tx_hash}")
                    return True
                else:
                    self.logger.error(f"Failed to update position balances after merge for market {market_id}")
                    return False
            else:
                self.logger.error(f"Failed to send merge transaction for market {market_id}")
                return False

        except Exception as e:
            self.logger.error(f"Error merging positions for market {market_id}: {str(e)}")
            return False

    async def split_collateral(self, market_id: str, collateral_amount: Decimal) -> bool:
        """
        Split USDC (collateral) into equal YES and NO tokens.
        This refills inventory after hedging.

        Args:
            market_id: Unique identifier for the market
            collateral_amount: Amount of collateral to split

        Returns:
            True if successful, False otherwise
        """
        position = self.get_position(market_id)
        if not position:
            self.logger.error(f"No position found for market {market_id}")
            return False

        if collateral_amount <= 0:
            self.logger.info(f"Cannot split zero or negative collateral for market {market_id}")
            return False

        try:
            # Prepare transaction data for splitting collateral
            # This would typically involve encoding the function call to the CTF contract
            # For now, we'll simulate the transaction data
            function_signature = "splitPosition(address,address,bytes32,uint256[],uint256)"
            # Note: Actual implementation would require proper ABI encoding

            # Use proxy wallet if available for gas-efficient transactions
            if self.proxy_wallet:
                # Prepare transaction data for the proxy wallet
                tx_data = TransactionData(
                    to=self.api_client.ctf_exchange_contract_address,
                    value=int(collateral_amount),  # Convert Decimal to int for value
                    data=f"0x{function_signature}",  # This would be the actual encoded data
                    gas_limit=300000  # Estimated gas limit for split operation
                )

                # Send transaction via proxy wallet
                tx_hash = await self.proxy_wallet.send_transaction_via_relayer(tx_data)
            else:
                # Fallback to direct transaction
                tx_call_data = {
                    'condition_id': position.condition_id,
                    'collateral_token': position.collateral_token_address,
                    'amount': str(collateral_amount),
                    'index_set': [0, 1]  # Assuming binary market with 2 outcomes
                }

                sender_address = self.proxy_wallet_address or self.api_client.wallet_address
                tx_hash = await self.api_client.send_transaction(
                    contract_address=self.api_client.ctf_exchange_contract_address,
                    function_name='splitPosition',
                    args=[tx_call_data],
                    from_address=sender_address,
                    value=int(collateral_amount)  # Send collateral amount with transaction
                )

            if tx_hash:
                # Update position balances after successful split
                # Each unit of collateral becomes 1 YES and 1 NO token
                success = self.update_position_balances(
                    market_id,
                    yes_delta=collateral_amount,
                    no_delta=collateral_amount
                )

                if success:
                    self.logger.info(f"Successfully split {collateral_amount} collateral "
                                   f"into YES and NO tokens for market {market_id}. "
                                   f"Transaction: {tx_hash}")
                    return True
                else:
                    self.logger.error(f"Failed to update position balances after split for market {market_id}")
                    return False
            else:
                self.logger.error(f"Failed to send split transaction for market {market_id}")
                return False

        except Exception as e:
            self.logger.error(f"Error splitting collateral for market {market_id}: {str(e)}")
            return False