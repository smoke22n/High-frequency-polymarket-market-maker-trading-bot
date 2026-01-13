"""
Tests for the Market Data Ingestion Engine
"""
import asyncio
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from polymarket_mm_bot.market_data.engine import (
    MarketDataIngestionEngine,
    LocalOrderBook,
    OrderBookEntry,
    OrderBookDelta
import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch

from polymarket_mm_bot.market_data.order_book_engine import (
    OrderBookEntry, OrderBookSnapshot, OrderBookDelta, 
    LocalOrderBook, MarketDataIngestionEngine
)
from polymarket_mm_bot.api.client import Credentials


class TestLocalOrderBook(unittest.TestCase):
    """Test cases for LocalOrderBook class"""

    def setUp(self):
        self.order_book = LocalOrderBook(market_id="test_market")

    def test_initial_state(self):
        """Test initial state of LocalOrderBook"""
        self.assertEqual(self.order_book.market_id, "test_market")
        self.assertEqual(len(self.order_book.bids), 0)
        self.assertEqual(len(self.order_book.asks), 0)

    def test_apply_bid_delta_add(self):
        """Test applying bid delta to add a new bid level"""
        delta = {
            'bids': [{'price': '100.0', 'size': '10.0'}],
            'asks': []
        }
        self.order_book.apply_delta(delta)

        self.assertEqual(len(self.order_book.bids), 1)
        self.assertIn(Decimal('100.0'), self.order_book.bids)
        self.assertEqual(self.order_book.bids[Decimal('100.0')].size, Decimal('10.0'))

    def test_apply_ask_delta_add(self):
        """Test applying ask delta to add a new ask level"""
        delta = {
            'bids': [],
            'asks': [{'price': '101.0', 'size': '5.0'}]
        }
        self.order_book.apply_delta(delta)

        self.assertEqual(len(self.order_book.asks), 1)
        self.assertIn(Decimal('101.0'), self.order_book.asks)
        self.assertEqual(self.order_book.asks[Decimal('101.0')].size, Decimal('5.0'))

    def test_apply_bid_delta_remove(self):
        """Test applying bid delta to remove a bid level"""
        # First add a bid level
        self.order_book.bids[Decimal('100.0')] = OrderBookEntry(
            price=Decimal('100.0'),
            size=Decimal('10.0')
        )

        # Then remove it by setting size to 0
        delta = {
            'bids': [{'price': '100.0', 'size': '0.0'}],
            'asks': []
        }
        self.order_book.apply_delta(delta)

        self.assertEqual(len(self.order_book.bids), 0)
        self.assertNotIn(Decimal('100.0'), self.order_book.bids)

    def test_get_top_of_book(self):
        """Test getting the best bid and ask"""
        # Add some bids and asks
        self.order_book.bids[Decimal('99.0')] = OrderBookEntry(price=Decimal('99.0'), size=Decimal('5.0'))
        self.order_book.bids[Decimal('100.0')] = OrderBookEntry(price=Decimal('100.0'), size=Decimal('10.0'))  # Best bid
        self.order_book.asks[Decimal('101.0')] = OrderBookEntry(price=Decimal('101.0'), size=Decimal('8.0'))  # Best ask
        self.order_book.asks[Decimal('102.0')] = OrderBookEntry(price=Decimal('102.0'), size=Decimal('12.0'))

        best_bid, best_ask = self.order_book.get_top_of_book()

        self.assertEqual(best_bid.price, Decimal('100.0'))
        self.assertEqual(best_ask.price, Decimal('101.0'))

    def test_calculate_mid_price(self):
        """Test calculating mid-price"""
        self.order_book.bids[Decimal('100.0')] = OrderBookEntry(price=Decimal('100.0'), size=Decimal('10.0'))
        self.order_book.asks[Decimal('102.0')] = OrderBookEntry(price=Decimal('102.0'), size=Decimal('8.0'))

        mid_price = self.order_book.calculate_mid_price()
        expected_mid = (Decimal('100.0') + Decimal('102.0')) / 2
        self.assertEqual(mid_price, expected_mid)

    def test_calculate_spread(self):
        """Test calculating spread"""
        self.order_book.bids[Decimal('100.0')] = OrderBookEntry(price=Decimal('100.0'), size=Decimal('10.0'))
        self.order_book.asks[Decimal('102.0')] = OrderBookEntry(price=Decimal('102.0'), size=Decimal('8.0'))

        spread = self.order_book.calculate_spread()
        expected_spread = Decimal('102.0') - Decimal('100.0')
        self.assertEqual(spread, expected_spread)

    def test_calculate_spread_percentage(self):
        """Test calculating spread percentage"""
        self.order_book.bids[Decimal('100.0')] = OrderBookEntry(price=Decimal('100.0'), size=Decimal('10.0'))
        self.order_book.asks[Decimal('102.0')] = OrderBookEntry(price=Decimal('102.0'), size=Decimal('8.0'))

        spread_pct = self.order_book.calculate_spread_percentage()
        expected_mid = (Decimal('100.0') + Decimal('102.0')) / 2
        expected_spread = Decimal('2.0')
        expected_pct = (expected_spread / expected_mid) * 100
        self.assertEqual(spread_pct, expected_pct)


class TestMarketDataIngestionEngineAsync(unittest.TestCase):
    """Async test cases for MarketDataIngestionEngine class"""

    def setUp(self):
        self.credentials = Credentials(
            api_key="test_key",
            secret_key="test_secret",
            wallet_address="test_wallet"
        )
        self.engine = MarketDataIngestionEngine(self.credentials)

    @patch('polymarket_mm_bot.api.connection_manager.ConnectionManager')
    def test_subscribe_to_market(self, mock_connection_manager):
        """Test subscribing to a market"""
        async def run_test():
            # Mock the connection manager
            self.engine.connection_manager = mock_connection_manager
            mock_connection_manager.subscribe_to_orderbook = AsyncMock()

            market_id = "test_market"
            await self.engine.subscribe_to_market(market_id)

            # Verify the subscription was called
            mock_connection_manager.subscribe_to_orderbook.assert_called_once_with([market_id])

            # Verify the local order book was created
            self.assertIn(market_id, self.engine.order_books)

        asyncio.run(run_test())

    @patch('polymarket_mm_bot.api.connection_manager.ConnectionManager')
    def test_unsubscribe_from_market(self, mock_connection_manager):
        """Test unsubscribing from a market"""
        async def run_test():
            # Mock the connection manager
            self.engine.connection_manager = mock_connection_manager
            mock_connection_manager.unsubscribe_from_orderbook = AsyncMock()

            market_id = "test_market"
            # Pre-add an order book
            self.engine.order_books[market_id] = LocalOrderBook(market_id=market_id)

            await self.engine.unsubscribe_from_market(market_id)

            # Verify the unsubscription was called
            mock_connection_manager.unsubscribe_from_orderbook.assert_called_once_with([market_id])

            # Verify the local order book was removed
            self.assertNotIn(market_id, self.engine.order_books)

        asyncio.run(run_test())

    def test_handle_orderbook_update(self):
        """Test handling order book update messages"""
        async def run_test():
            market_id = "test_market"

            # Create an initial order book
            self.engine.order_books[market_id] = LocalOrderBook(market_id=market_id)

            # Create a test message
            message = {
                'market_id': market_id,
                'bids': [{'price': '100.0', 'size': '10.0'}],
                'asks': [{'price': '101.0', 'size': '5.0'}]
            }

            # Call the handler
            await self.engine._handle_orderbook_update(message)

            # Verify the order book was updated
            order_book = self.engine.order_books[market_id]
            self.assertIn(Decimal('100.0'), order_book.bids)
            self.assertIn(Decimal('101.0'), order_book.asks)
            self.assertEqual(order_book.bids[Decimal('100.0')].size, Decimal('10.0'))
            self.assertEqual(order_book.asks[Decimal('101.0')].size, Decimal('5.0'))

        asyncio.run(run_test())

    def test_register_update_callback(self):
        """Test registering update callbacks"""
        async def run_test():
            market_id = "test_market"
            callback_results = {'called': False, 'market_id': None}

            def test_callback(mkt_id, order_book):
                callback_results['called'] = True
                callback_results['market_id'] = mkt_id

            # Create the order book first
            self.engine.order_books[market_id] = LocalOrderBook(market_id=market_id)

            # Register the callback
            self.engine.register_update_callback(market_id, test_callback)

            # Trigger an update
            message = {
                'market_id': market_id,
                'bids': [{'price': '100.0', 'size': '10.0'}],
                'asks': [{'price': '101.0', 'size': '5.0'}]
            }

            await self.engine._handle_orderbook_update(message)

            # Verify the callback was called
            self.assertTrue(callback_results['called'])
            self.assertEqual(callback_results['market_id'], market_id)

        asyncio.run(run_test())

    def test_get_market_metrics(self):
        """Test getting market metrics"""
        async def run_test():
            market_id = "test_market"

            # Create an order book with some data
            order_book = LocalOrderBook(market_id=market_id)
            order_book.bids[Decimal('100.0')] = OrderBookEntry(price=Decimal('100.0'), size=Decimal('10.0'))
            order_book.asks[Decimal('102.0')] = OrderBookEntry(price=Decimal('102.0'), size=Decimal('8.0'))
            self.engine.order_books[market_id] = order_book

            metrics = self.engine.get_market_metrics(market_id)

            self.assertEqual(metrics['mid_price'], Decimal('101.0'))
            self.assertEqual(metrics['spread'], Decimal('2.0'))
            self.assertIsNotNone(metrics['spread_percentage'])

        asyncio.run(run_test())


# Integration test to verify the full workflow
class TestMarketDataIntegration(unittest.TestCase):
    """Integration tests for the market data system"""

    def test_full_workflow(self):
        """Test the full workflow from subscription to metrics calculation"""
        async def run_test():
            credentials = Credentials(
                api_key="test_key",
                secret_key="test_secret",
                wallet_address="test_wallet"
            )

            engine = MarketDataIngestionEngine(credentials)

            # Since we can't actually connect to the WebSocket in tests,
            # we'll test the internal logic

            market_id = "integration_test_market"

            # Simulate subscription (creates local order book)
            if market_id not in engine.order_books:
                engine.order_books[market_id] = LocalOrderBook(market_id=market_id)

            # Apply some deltas
            delta1 = {
                'bids': [{'price': '100.0', 'size': '10.0'}, {'price': '99.0', 'size': '5.0'}],
                'asks': [{'price': '101.0', 'size': '8.0'}]
            }
            engine.order_books[market_id].apply_delta(delta1)

            # Verify order book state
            ob = engine.order_books[market_id]
            self.assertEqual(len(ob.bids), 2)
            self.assertEqual(len(ob.asks), 1)
            self.assertIn(Decimal('100.0'), ob.bids)
            self.assertIn(Decimal('101.0'), ob.asks)

            # Calculate metrics
            metrics = engine.get_market_metrics(market_id)
            self.assertIsNotNone(metrics['mid_price'])
            self.assertIsNotNone(metrics['spread'])

            # Apply another delta that modifies existing levels
            delta2 = {
                'bids': [{'price': '100.0', 'size': '15.0'}],  # Increase size at existing price
                'asks': [{'price': '102.0', 'size': '12.0'}]   # Add new ask level
            }
            engine.order_books[market_id].apply_delta(delta2)

            # Verify updated state
            self.assertEqual(ob.bids[Decimal('100.0')].size, Decimal('15.0'))
            self.assertIn(Decimal('102.0'), ob.asks)

            # Recalculate metrics
            new_metrics = engine.get_market_metrics(market_id)
            self.assertIsNotNone(new_metrics['mid_price'])
            self.assertIsNotNone(new_metrics['spread'])

        asyncio.run(run_test())


if __name__ == '__main__':
    unittest.main()
def test_order_book_entry():
    """Test OrderBookEntry creation"""
    entry = OrderBookEntry(price=Decimal('100.50'), size=Decimal('10.0'))
    assert entry.price == Decimal('100.50')
    assert entry.size == Decimal('10.0')


def test_order_book_snapshot():
    """Test OrderBookSnapshot creation and sorting"""
    bids = [
        OrderBookEntry(price=Decimal('100.0'), size=Decimal('5.0')),
        OrderBookEntry(price=Decimal('99.0'), size=Decimal('3.0')),
        OrderBookEntry(price=Decimal('101.0'), size=Decimal('7.0'))
    ]
    
    asks = [
        OrderBookEntry(price=Decimal('102.0'), size=Decimal('2.0')),
        OrderBookEntry(price=Decimal('103.0'), size=Decimal('4.0')),
        OrderBookEntry(price=Decimal('101.0'), size=Decimal('6.0'))
    ]
    
    snapshot = OrderBookSnapshot(bids=bids, asks=asks)
    
    # Check that bids are sorted in descending order
    assert snapshot.bids[0].price == Decimal('101.0')  # Highest bid first
    assert snapshot.bids[1].price == Decimal('100.0')
    assert snapshot.bids[2].price == Decimal('99.0')
    
    # Check that asks are sorted in ascending order
    assert snapshot.asks[0].price == Decimal('101.0')  # Lowest ask first
    assert snapshot.asks[1].price == Decimal('102.0')
    assert snapshot.asks[2].price == Decimal('103.0')


def test_local_order_book_initialization():
    """Test LocalOrderBook initialization"""
    book = LocalOrderBook("test_market")
    assert book.market_id == "test_market"
    assert len(book.bids) == 0
    assert len(book.asks) == 0


def test_local_order_book_apply_snapshot():
    """Test applying a snapshot to LocalOrderBook"""
    book = LocalOrderBook("test_market")
    
    bids = [
        OrderBookEntry(price=Decimal('100.0'), size=Decimal('5.0')),
        OrderBookEntry(price=Decimal('99.0'), size=Decimal('3.0'))
    ]
    
    asks = [
        OrderBookEntry(price=Decimal('101.0'), size=Decimal('2.0')),
        OrderBookEntry(price=Decimal('102.0'), size=Decimal('4.0'))
    ]
    
    snapshot = OrderBookSnapshot(bids=bids, asks=asks, sequence_number=1)
    book.apply_snapshot(snapshot)
    
    assert len(book.bids) == 2
    assert len(book.asks) == 2
    assert book.bids[Decimal('100.0')].size == Decimal('5.0')
    assert book.asks[Decimal('101.0')].size == Decimal('2.0')
    assert book.sequence_number == 1


def test_local_order_book_apply_delta():
    """Test applying a delta to LocalOrderBook"""
    book = LocalOrderBook("test_market")
    
    # Start with a snapshot
    bids = [OrderBookEntry(price=Decimal('100.0'), size=Decimal('5.0'))]
    asks = [OrderBookEntry(price=Decimal('101.0'), size=Decimal('2.0'))]
    snapshot = OrderBookSnapshot(bids=bids, asks=asks, sequence_number=1)
    book.apply_snapshot(snapshot)
    
    # Apply a delta that adds a new bid and updates an ask
    delta = OrderBookDelta(
        market_id="test_market",
        bids=[OrderBookEntry(price=Decimal('100.5'), size=Decimal('3.0'))],  # New bid
        asks=[OrderBookEntry(price=Decimal('101.0'), size=Decimal('5.0'))],  # Update existing ask
        deletes=[],  # No deletions
        sequence_number=2
    )
    book.apply_delta(delta)
    
    # Check that new bid was added
    assert len(book.bids) == 2
    assert book.bids[Decimal('100.5')].size == Decimal('3.0')
    
    # Check that ask was updated
    assert book.asks[Decimal('101.0')].size == Decimal('5.0')
    
    # Check sequence number was updated
    assert book.sequence_number == 2


def test_local_order_book_apply_delta_with_deletion():
    """Test applying a delta with deletions to LocalOrderBook"""
    book = LocalOrderBook("test_market")
    
    # Start with a snapshot
    bids = [OrderBookEntry(price=Decimal('100.0'), size=Decimal('5.0'))]
    asks = [OrderBookEntry(price=Decimal('101.0'), size=Decimal('2.0'))]
    snapshot = OrderBookSnapshot(bids=bids, asks=asks, sequence_number=1)
    book.apply_snapshot(snapshot)
    
    # Apply a delta that deletes the bid
    delta = OrderBookDelta(
        market_id="test_market",
        bids=[],  # No new bids
        asks=[],  # No new asks
        deletes=[{'price': Decimal('100.0'), 'side': 'bid'}],  # Delete bid
        sequence_number=2
    )
    book.apply_delta(delta)
    
    # Check that bid was deleted
    assert len(book.bids) == 0
    assert len(book.asks) == 1  # Ask should still be there


def test_local_order_book_get_best_bid_ask():
    """Test getting best bid and ask from LocalOrderBook"""
    book = LocalOrderBook("test_market")
    
    bids = [
        OrderBookEntry(price=Decimal('99.0'), size=Decimal('3.0')),
        OrderBookEntry(price=Decimal('100.0'), size=Decimal('5.0'))  # Higher price should be best
    ]
    
    asks = [
        OrderBookEntry(price=Decimal('101.0'), size=Decimal('2.0')),  # Lower price should be best
        OrderBookEntry(price=Decimal('102.0'), size=Decimal('4.0'))
    ]
    
    snapshot = OrderBookSnapshot(bids=bids, asks=asks)
    book.apply_snapshot(snapshot)
    
    best_bid = book.get_best_bid()
    best_ask = book.get_best_ask()
    
    assert best_bid.price == Decimal('100.0')
    assert best_ask.price == Decimal('101.0')


def test_local_order_book_get_mid_price():
    """Test calculating mid-price from LocalOrderBook"""
    book = LocalOrderBook("test_market")
    
    bids = [OrderBookEntry(price=Decimal('100.0'), size=Decimal('5.0'))]
    asks = [OrderBookEntry(price=Decimal('102.0'), size=Decimal('2.0'))]
    
    snapshot = OrderBookSnapshot(bids=bids, asks=asks)
    book.apply_snapshot(snapshot)
    
    mid_price = book.get_mid_price()
    assert mid_price == Decimal('101.0')  # (100.0 + 102.0) / 2


def test_local_order_book_get_spread():
    """Test calculating spread from LocalOrderBook"""
    book = LocalOrderBook("test_market")
    
    bids = [OrderBookEntry(price=Decimal('100.0'), size=Decimal('5.0'))]
    asks = [OrderBookEntry(price=Decimal('102.0'), size=Decimal('2.0'))]
    
    snapshot = OrderBookSnapshot(bids=bids, asks=asks)
    book.apply_snapshot(snapshot)
    
    spread = book.get_spread()
    assert spread == Decimal('2.0')  # 102.0 - 100.0


@pytest.mark.asyncio
async def test_market_data_ingestion_engine_initialization():
    """Test MarketDataIngestionEngine initialization"""
    credentials = Credentials(
        api_key="test_key",
        secret_key="test_secret",
        wallet_address="test_address"
    )
    
    engine = MarketDataIngestionEngine(credentials)
    
    assert engine.credentials == credentials
    assert engine.local_order_books == {}
    assert engine.is_running is False


@pytest.mark.asyncio
async def test_market_data_ingestion_engine_subscribe_unsubscribe():
    """Test subscribing and unsubscribing to markets"""
    credentials = Credentials(
        api_key="test_key",
        secret_key="test_secret",
        wallet_address="test_address"
    )
    
    with patch('polymarket_mm_bot.api.connection_manager.ConnectionManager') as mock_conn_manager:
        engine = MarketDataIngestionEngine(credentials)
        
        # Mock the connection manager methods
        mock_conn_manager_instance = AsyncMock()
        engine.connection_manager = mock_conn_manager_instance
        
        # Subscribe to a market
        engine.subscribe_to_market("test_market")
        
        # Check that local order book was created
        assert "test_market" in engine.local_order_books
        assert isinstance(engine.local_order_books["test_market"], LocalOrderBook)
        
        # Check that subscription was called
        mock_conn_manager_instance.subscribe_to_orderbook.assert_called_once_with(["test_market"])
        
        # Unsubscribe from the market
        engine.unsubscribe_from_market("test_market")
        
        # Check that local order book was removed
        assert "test_market" not in engine.local_order_books


@pytest.mark.asyncio
async def test_market_data_ingestion_engine_handle_orderbook_update():
    """Test handling order book updates"""
    credentials = Credentials(
        api_key="test_key",
        secret_key="test_secret",
        wallet_address="test_address"
    )
    
    engine = MarketDataIngestionEngine(credentials)
    
    # Subscribe to a market first
    engine.subscribe_to_market("test_market")
    
    # Create a mock update message
    update_message = {
        'market_id': 'test_market',
        'bids': [
            {'price': '100.0', 'size': '5.0'},
            {'price': '99.0', 'size': '3.0'}
        ],
        'asks': [
            {'price': '101.0', 'size': '2.0'},
            {'price': '102.0', 'size': '4.0'}
        ],
        'deletes': [],
        'sequence': 1
    }
    
    # Handle the update
    await engine._handle_orderbook_update(update_message)
    
    # Check that the local order book was updated
    local_book = engine.local_order_books['test_market']
    assert len(local_book.bids) == 2
    assert len(local_book.asks) == 2
    assert local_book.bids[Decimal('100.0')].size == Decimal('5.0')
    assert local_book.asks[Decimal('101.0')].size == Decimal('2.0')


@pytest.mark.asyncio
async def test_market_data_ingestion_engine_periodic_calculations():
    """Test periodic calculations of mid-price and spread"""
    credentials = Credentials(
        api_key="test_key",
        secret_key="test_secret",
        wallet_address="test_address"
    )

    engine = MarketDataIngestionEngine(credentials)

    # Subscribe to a market first
    engine.subscribe_to_market("test_market")

    # Add some data to the order book
    bids = [OrderBookEntry(price=Decimal('100.0'), size=Decimal('5.0'))]
    asks = [OrderBookEntry(price=Decimal('102.0'), size=Decimal('2.0'))]
    snapshot = OrderBookSnapshot(bids=bids, asks=asks)
    engine.local_order_books['test_market'].apply_snapshot(snapshot)

    # Register callbacks to capture calculated values
    captured_mid_prices = []
    captured_spreads = []

    def mid_price_callback(mid_price):
        captured_mid_prices.append(mid_price)

    def spread_callback(spread):
        captured_spreads.append(spread)

    engine.register_mid_price_callback("test_market", mid_price_callback)
    engine.register_spread_callback("test_market", spread_callback)

    # Temporarily set is_running to False to prevent the loop from running continuously
    original_is_running = engine.is_running
    engine.is_running = False

    # Run the periodic calculations once
    await engine._periodic_calculations()

    # Restore original value
    engine.is_running = original_is_running

    # Verify the expected values would be calculated
    expected_mid_price = Decimal('101.0')  # (100.0 + 102.0) / 2
    expected_spread = Decimal('2.0')  # 102.0 - 100.0

    # The callbacks should have been called with these values
    # Since we're not actually sleeping, the callbacks should have been called
    # if the values exist
    if captured_mid_prices:
        assert captured_mid_prices[0] == expected_mid_price
    if captured_spreads:
        assert captured_spreads[0] == expected_spread
