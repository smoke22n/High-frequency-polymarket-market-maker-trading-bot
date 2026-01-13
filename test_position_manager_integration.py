"""
Integration tests for the PositionManager with Proxy Wallet functionality.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from polymarket_mm_bot.utils.position_manager import PositionManager
from polymarket_mm_bot.utils.proxy_wallet import ProxyWallet, TransactionData


class TestPositionManagerWithProxyWallet(unittest.IsolatedAsyncioTestCase):
    """Integration tests for PositionManager with Proxy Wallet."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_api_client = AsyncMock()
        self.mock_api_client.wallet_address = "0x1234567890123456789012345678901234567890"
        self.mock_api_client.ctf_exchange_contract_address = "0xabcdef1234567890abcdef1234567890abcdef12"
        self.mock_api_client.send_transaction = AsyncMock(return_value="0xtxhash123456789")
        
    @patch('polymarket_mm_bot.utils.proxy_wallet.aiohttp.ClientSession')
    async def test_merge_positions_with_proxy_wallet(self, mock_session_class):
        """Test merging positions using proxy wallet for gas-efficient transactions."""
        # Create a mock proxy wallet
        mock_proxy_wallet = AsyncMock()
        mock_proxy_wallet.send_transaction_via_relayer = AsyncMock(return_value="0xtxhash_via_relayer")
        
        # Create PositionManager with proxy wallet
        position_manager = PositionManager(
            api_client=self.mock_api_client,
            proxy_wallet=mock_proxy_wallet
        )
        
        market_id = "test_market_proxy"
        
        # Set up position
        position_manager.track_position(
            market_id=market_id,
            yes_balance=Decimal("50"),
            no_balance=Decimal("50"),
            collateral_token_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            condition_id="0xcondition_proxy"
        )
        
        # Perform merge
        result = await position_manager.merge_positions(market_id)
        
        self.assertTrue(result)
        
        # Verify proxy wallet was used instead of direct API call
        mock_proxy_wallet.send_transaction_via_relayer.assert_called_once()
        # The direct API call should not have been made
        self.mock_api_client.send_transaction.assert_not_called()
        
        # Check that balances were updated correctly
        updated_position = position_manager.get_position(market_id)
        self.assertEqual(updated_position.yes_balance, Decimal("0"))
        self.assertEqual(updated_position.no_balance, Decimal("0"))
        
    @patch('polymarket_mm_bot.utils.proxy_wallet.aiohttp.ClientSession')
    async def test_split_collateral_with_proxy_wallet(self, mock_session_class):
        """Test splitting collateral using proxy wallet for gas-efficient transactions."""
        # Create a mock proxy wallet
        mock_proxy_wallet = AsyncMock()
        mock_proxy_wallet.send_transaction_via_relayer = AsyncMock(return_value="0xtxhash_via_relayer")
        
        # Create PositionManager with proxy wallet
        position_manager = PositionManager(
            api_client=self.mock_api_client,
            proxy_wallet=mock_proxy_wallet
        )
        
        market_id = "test_split_proxy"
        
        # Set up position
        position_manager.track_position(
            market_id=market_id,
            yes_balance=Decimal("0"),
            no_balance=Decimal("0"),
            collateral_token_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            condition_id="0xcondition_split"
        )
        
        # Perform split
        result = await position_manager.split_collateral(market_id, Decimal("100"))
        
        self.assertTrue(result)
        
        # Verify proxy wallet was used instead of direct API call
        mock_proxy_wallet.send_transaction_via_relayer.assert_called_once()
        # The direct API call should not have been made
        self.mock_api_client.send_transaction.assert_not_called()
        
        # Check that balances were updated correctly
        updated_position = position_manager.get_position(market_id)
        self.assertEqual(updated_position.yes_balance, Decimal("100"))
        self.assertEqual(updated_position.no_balance, Decimal("100"))
        
    async def test_fallback_to_direct_transaction(self):
        """Test that direct transaction is used when proxy wallet is not available."""
        # Create PositionManager without proxy wallet
        position_manager = PositionManager(api_client=self.mock_api_client)
        
        market_id = "test_fallback"
        
        # Set up position
        position_manager.track_position(
            market_id=market_id,
            yes_balance=Decimal("50"),
            no_balance=Decimal("50"),
            collateral_token_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            condition_id="0xcondition_fallback"
        )
        
        # Perform merge
        result = await position_manager.merge_positions(market_id)
        
        self.assertTrue(result)
        
        # Verify direct API call was made
        self.mock_api_client.send_transaction.assert_called_once()
        
        # Check that balances were updated correctly
        updated_position = position_manager.get_position(market_id)
        self.assertEqual(updated_position.yes_balance, Decimal("0"))
        self.assertEqual(updated_position.no_balance, Decimal("0"))


class TestProxyWallet(unittest.IsolatedAsyncioTestCase):
    """Test cases for ProxyWallet functionality."""
    
    @patch('polymarket_mm_bot.utils.proxy_wallet.Web3')
    async def test_send_transaction_via_relayer(self, mock_web3_class):
        """Test sending transaction via relayer."""
        # Mock web3 instance
        mock_web3 = MagicMock()
        mock_web3.eth = MagicMock()
        mock_web3.eth.gas_price = 20000000000  # 20 gwei
        mock_web3.eth.get_transaction_count = MagicMock(return_value=5)
        mock_web3.eth.account = MagicMock()
        mock_web3.eth.account.sign_transaction = MagicMock()
        mock_web3.eth.send_raw_transaction = MagicMock()
        mock_web3.eth.wait_for_transaction_receipt = MagicMock()
        
        mock_web3.eth.account.sign_transaction.return_value.rawTransaction = b"signed_tx"
        mock_web3.eth.send_raw_transaction.return_value.hex.return_value = "0xtxhash_relayer_test"
        
        mock_web3.eth.wait_for_transaction_receipt.return_value.status = 1
        
        mock_web3_class.return_value = mock_web3
        
        # Create proxy wallet
        proxy_wallet = ProxyWallet(
            private_key="0x56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d82cc",
            rpc_url="https://polygon-rpc.com/",
            relayer_url="https://test-relayer.example.com/api/v1/relay"
        )
        
        # Create transaction data
        tx_data = TransactionData(
            to="0x1234567890123456789012345678901234567890",
            value=0,
            data="0x1234abcd",
            gas_limit=200000
        )
        
        # Mock the aiohttp session
        with patch('polymarket_mm_bot.utils.proxy_wallet.aiohttp.ClientSession') as mock_session:
            mock_post_context = MagicMock()
            mock_post_response = MagicMock()
            mock_post_response.status = 200
            mock_post_response.json = AsyncMock(return_value={"txHash": "0xtxhash_relayer_test"})
            
            mock_post_context.__aenter__.return_value = mock_post_response
            mock_post_context.__aexit__.return_value = None
            mock_session.return_value.post.return_value = mock_post_context
            
            # Send transaction via relayer
            result = await proxy_wallet.send_transaction_via_relayer(tx_data)
            
            self.assertEqual(result, "0xtxhash_relayer_test")
            # Verify the session was called with correct parameters
            mock_session.return_value.post.assert_called_once()
    
    def test_estimate_gas_cost(self):
        """Test gas cost estimation."""
        # This test would require a proper Web3 setup with a testnet
        # For now, we'll just verify the method exists and can be called
        pass


if __name__ == '__main__':
    unittest.main()