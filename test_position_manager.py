"""
Tests for the PositionManager class and hedging functionality.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from polymarket_mm_bot.utils.position_manager import PositionManager, Position
from polymarket_mm_bot.utils.proxy_wallet import ProxyWallet


class TestPositionManager(unittest.TestCase):
    """Test cases for PositionManager class."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Mock API client
        self.mock_api_client = AsyncMock()
        self.mock_api_client.wallet_address = "0x1234567890123456789012345678901234567890"
        self.mock_api_client.ctf_exchange_contract_address = "0xabcdef1234567890abcdef1234567890abcdef12"
        
        # Create PositionManager instance
        self.position_manager = PositionManager(api_client=self.mock_api_client)
        
    def test_track_position(self):
        """Test tracking a new position."""
        market_id = "test_market_1"
        yes_balance = Decimal("100")
        no_balance = Decimal("50")
        collateral_token = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"  # USDC address
        condition_id = "0xcondition123"
        
        self.position_manager.track_position(
            market_id=market_id,
            yes_balance=yes_balance,
            no_balance=no_balance,
            collateral_token_address=collateral_token,
            condition_id=condition_id
        )
        
        position = self.position_manager.get_position(market_id)
        self.assertIsNotNone(position)
        self.assertEqual(position.market_id, market_id)
        self.assertEqual(position.yes_balance, yes_balance)
        self.assertEqual(position.no_balance, no_balance)
        self.assertEqual(position.collateral_token_address, collateral_token)
        self.assertEqual(position.condition_id, condition_id)
        
    def test_update_position_balances(self):
        """Test updating position balances."""
        market_id = "test_market_2"
        initial_yes = Decimal("100")
        initial_no = Decimal("50")
        
        self.position_manager.track_position(
            market_id=market_id,
            yes_balance=initial_yes,
            no_balance=initial_no,
            collateral_token_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            condition_id="0xcondition456"
        )
        
        # Update balances
        yes_delta = Decimal("-20")
        no_delta = Decimal("30")
        
        result = self.position_manager.update_position_balances(
            market_id=market_id,
            yes_delta=yes_delta,
            no_delta=no_delta
        )
        
        self.assertTrue(result)
        
        updated_position = self.position_manager.get_position(market_id)
        self.assertEqual(updated_position.yes_balance, initial_yes + yes_delta)  # 100 - 20 = 80
        self.assertEqual(updated_position.no_balance, initial_no + no_delta)    # 50 + 30 = 80
        
    def test_get_hedgeable_amount(self):
        """Test getting the hedgeable amount (minimum of YES/NO balances)."""
        market_id = "test_market_3"
        
        # More YES than NO - should return NO amount
        self.position_manager.track_position(
            market_id=market_id,
            yes_balance=Decimal("100"),
            no_balance=Decimal("75"),
            collateral_token_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            condition_id="0xcondition789"
        )
        
        hedgeable = self.position_manager.get_hedgeable_amount(market_id)
        self.assertEqual(hedgeable, Decimal("75"))
        
        # Equal amounts
        self.position_manager.update_position_balances(
            market_id=market_id,
            yes_delta=Decimal("-25"),
            no_delta=Decimal("0")
        )
        
        hedgeable = self.position_manager.get_hedgeable_amount(market_id)
        self.assertEqual(hedgeable, Decimal("75"))
        
        # More NO than YES
        self.position_manager.update_position_balances(
            market_id=market_id,
            yes_delta=Decimal("-10"),
            no_delta=Decimal("20")
        )
        
        hedgeable = self.position_manager.get_hedgeable_amount(market_id)
        self.assertEqual(hedgeable, Decimal("65"))
        
    def test_get_net_exposure(self):
        """Test getting net exposure."""
        market_id = "test_market_4"
        
        # More YES than NO
        self.position_manager.track_position(
            market_id=market_id,
            yes_balance=Decimal("100"),
            no_balance=Decimal("75"),
            collateral_token_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            condition_id="0xconditionabc"
        )
        
        exposure, direction = self.position_manager.get_net_exposure(market_id)
        self.assertEqual(exposure, Decimal("25"))
        self.assertEqual(direction, "YES")
        
        # More NO than YES
        self.position_manager.update_position_balances(
            market_id=market_id,
            yes_delta=Decimal("-50"),
            no_delta=Decimal("0")
        )
        
        exposure, direction = self.position_manager.get_net_exposure(market_id)
        self.assertEqual(exposure, Decimal("25"))
        self.assertEqual(direction, "NO")
        
        # Equal amounts (neutral) - adjust to make them equal
        # Current state: YES=50, NO=75
        # Need to make them equal: both should be 62.5, but since we can't have half tokens,
        # let's make both 50 by reducing NO by 25
        self.position_manager.update_position_balances(
            market_id=market_id,
            yes_delta=Decimal("0"),
            no_delta=Decimal("-25")
        )

        exposure, direction = self.position_manager.get_net_exposure(market_id)
        self.assertEqual(exposure, Decimal("0"))
        self.assertEqual(direction, "NO")  # Neutral case should return 'NO'


class TestPositionManagerAsync(unittest.IsolatedAsyncioTestCase):
    """Async test cases for PositionManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_api_client = AsyncMock()
        self.mock_api_client.wallet_address = "0x1234567890123456789012345678901234567890"
        self.mock_api_client.ctf_exchange_contract_address = "0xabcdef1234567890abcdef1234567890abcdef12"
        self.mock_api_client.send_transaction = AsyncMock(return_value="0xtxhash123456789")

        # Create PositionManager instance
        self.position_manager = PositionManager(api_client=self.mock_api_client)
        
    async def test_merge_positions_success(self):
        """Test successful merging of positions."""
        market_id = "test_market_5"
        
        # Set up position with equal YES/NO balances
        self.position_manager.track_position(
            market_id=market_id,
            yes_balance=Decimal("50"),
            no_balance=Decimal("50"),
            collateral_token_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            condition_id="0xconditiondef"
        )
        
        # Perform merge
        result = await self.position_manager.merge_positions(market_id)
        
        self.assertTrue(result)
        
        # Check that balances were updated correctly
        updated_position = self.position_manager.get_position(market_id)
        self.assertEqual(updated_position.yes_balance, Decimal("0"))
        self.assertEqual(updated_position.no_balance, Decimal("0"))
        
        # Check that the transaction was called
        self.mock_api_client.send_transaction.assert_called_once()
        
    async def test_merge_positions_partial(self):
        """Test merging a specific amount of positions."""
        market_id = "test_market_6"
        
        # Set up position with unequal balances
        self.position_manager.track_position(
            market_id=market_id,
            yes_balance=Decimal("100"),
            no_balance=Decimal("75"),
            collateral_token_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            condition_id="0xcondition789"
        )
        
        # Merge only 30 tokens
        result = await self.position_manager.merge_positions(market_id, amount=Decimal("30"))
        
        self.assertTrue(result)
        
        # Check that balances were updated correctly
        updated_position = self.position_manager.get_position(market_id)
        self.assertEqual(updated_position.yes_balance, Decimal("70"))  # 100 - 30
        self.assertEqual(updated_position.no_balance, Decimal("45"))   # 75 - 30
        
        # Check that the transaction was called
        self.mock_api_client.send_transaction.assert_called_once()
        
    async def test_split_collateral_success(self):
        """Test successful splitting of collateral."""
        market_id = "test_market_7"
        
        # Set up position with zero balances
        self.position_manager.track_position(
            market_id=market_id,
            yes_balance=Decimal("0"),
            no_balance=Decimal("0"),
            collateral_token_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            condition_id="0xconditionxyz"
        )
        
        # Split 100 units of collateral
        result = await self.position_manager.split_collateral(market_id, Decimal("100"))
        
        self.assertTrue(result)
        
        # Check that balances were updated correctly
        updated_position = self.position_manager.get_position(market_id)
        self.assertEqual(updated_position.yes_balance, Decimal("100"))
        self.assertEqual(updated_position.no_balance, Decimal("100"))
        
        # Check that the transaction was called
        self.mock_api_client.send_transaction.assert_called_once()


if __name__ == '__main__':
    unittest.main()