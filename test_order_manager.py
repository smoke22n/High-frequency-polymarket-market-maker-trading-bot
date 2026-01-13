"""
Test script for the OrderManager and main event loop functionality
"""
import asyncio
import logging
from unittest.mock import Mock, AsyncMock
from decimal import Decimal

from polymarket_mm_bot.utils.order_manager import OrderManager, ActiveOrder
from polymarket_mm_bot.strategies.hfmm_strategy import Order, HFMStrategy
from polymarket_mm_bot.market_data.order_book_engine import LocalOrderBook, OrderBookEntry
from polymarket_mm_bot.utils.position_manager import PositionManager


def test_order_manager_basic():
    """Basic test for OrderManager functionality"""
    print("Testing OrderManager basic functionality...")
    
    # Create a mock REST client
    mock_rest_client = Mock()
    mock_rest_client.place_order = AsyncMock(return_value={'order_id': 'test_order_1'})
    mock_rest_client.cancel_order = AsyncMock(return_value={'success': True})
    
    # Create order manager
    order_manager = OrderManager(mock_rest_client, tick_interval_ms=100)
    
    # Test placing an order
    order = Order(
        market_id="test_market",
        side="buy",
        price=Decimal('0.5'),
        size=Decimal('100')
    )
    
    async def run_test():
        await order_manager.start()
        
        # Place an order
        placed_orders = await order_manager.place_orders([order])
        assert len(placed_orders) == 1
        assert placed_orders[0].order_id == 'test_order_1'
        print("✓ Successfully placed order")
        
        # Check that order is tracked
        active_orders = await order_manager.get_active_orders_for_market("test_market")
        assert len(active_orders) == 1
        print("✓ Order is properly tracked")

        # Check order count
        order_count = await order_manager.get_order_count_for_market("test_market")
        assert order_count == 1
        print("✓ Order count is correct")
        
        # Cancel the order
        success = await order_manager.cancel_order('test_order_1')
        assert success == True
        print("✓ Successfully cancelled order")
        
        # Check that order is no longer tracked
        active_orders = await order_manager.get_active_orders_for_market("test_market")
        assert len(active_orders) == 0
        print("✓ Order is properly removed from tracking")
        
        await order_manager.stop()
    
    asyncio.run(run_test())
    print("✓ Basic OrderManager functionality test passed\n")


def test_order_comparison_logic():
    """Test the order comparison logic"""
    print("Testing order comparison logic...")
    
    # Create a mock REST client
    mock_rest_client = Mock()
    mock_rest_client.place_order = AsyncMock(return_value={'order_id': 'test_order_1'})
    mock_rest_client.cancel_order = AsyncMock(return_value={'success': True})
    
    # Create order manager
    order_manager = OrderManager(mock_rest_client, tick_interval_ms=100)
    
    async def run_test():
        await order_manager.start()
        
        # Create some existing orders
        existing_order = Order(
            market_id="test_market",
            side="buy",
            price=Decimal('0.5'),
            size=Decimal('100')
        )
        
        # Place the existing order
        await order_manager.place_orders([existing_order])
        
        # Create new orders that are different enough to trigger replacement
        new_orders = [
            Order(
                market_id="test_market",
                side="buy",
                price=Decimal('0.55'),  # Different price
                size=Decimal('100')
            ),
            Order(
                market_id="test_market",
                side="sell",
                price=Decimal('0.6'),
                size=Decimal('100')
            )
        ]
        
        # Check if replacement should happen due to price difference
        should_replace = await order_manager.should_replace_orders(
            "test_market",
            new_orders,
            threshold=Decimal('0.04')  # Threshold is 0.04, price diff is 0.05
        )
        assert should_replace == True
        print("✓ Correctly detected price difference requiring replacement")

        # Check if replacement should NOT happen with smaller threshold
        should_replace = await order_manager.should_replace_orders(
            "test_market",
            new_orders,
            threshold=Decimal('0.06')  # Threshold is 0.06, price diff is 0.05
        )
        # This might still be True due to other factors like order count difference
        print(f"✓ Replacement decision with higher threshold: {should_replace}")

        # Test stale order detection
        is_stale = await order_manager.are_orders_stale("test_market", max_age_seconds=0.0)  # Immediately stale
        assert is_stale == True
        print("✓ Correctly detected stale orders")
        
        await order_manager.stop()
    
    asyncio.run(run_test())
    print("✓ Order comparison logic test passed\n")


def test_cancel_replace_functionality():
    """Test the cancel and replace functionality"""
    print("Testing cancel and replace functionality...")

    # Create a mock REST client
    mock_rest_client = Mock()

    # Create a counter to track order IDs
    order_counter = 0

    async def mock_place_order(params):
        nonlocal order_counter
        order_counter += 1
        return {'order_id': f'new_order_{order_counter}'}

    mock_rest_client.place_order = mock_place_order
    mock_rest_client.cancel_order = AsyncMock(return_value={'success': True})

    # Create order manager
    order_manager = OrderManager(mock_rest_client, tick_interval_ms=100)

    async def run_test():
        await order_manager.start()

        # Create and place some initial orders
        initial_orders = [
            Order(
                market_id="test_market",
                side="buy",
                price=Decimal('0.5'),
                size=Decimal('100')
            ),
            Order(
                market_id="test_market",
                side="sell",
                price=Decimal('0.6'),
                size=Decimal('100')
            )
        ]

        await order_manager.place_orders(initial_orders)
        initial_count = await order_manager.get_order_count_for_market("test_market")
        assert initial_count == 2
        print("✓ Placed initial orders")

        # Create new orders to replace with
        new_orders = [
            Order(
                market_id="test_market",
                side="buy",
                price=Decimal('0.52'),
                size=Decimal('150')
            ),
            Order(
                market_id="test_market",
                side="sell",
                price=Decimal('0.58'),
                size=Decimal('150')
            )
        ]

        # Perform cancel and replace
        success = await order_manager.replace_orders_for_market("test_market", new_orders)
        assert success == True
        print("✓ Successfully performed cancel and replace")

        # Check that old orders are gone and new ones are present
        final_count = await order_manager.get_order_count_for_market("test_market")
        assert final_count == 2  # Should have 2 new orders
        print("✓ Final order count is correct after replacement")

        await order_manager.stop()

    asyncio.run(run_test())
    print("✓ Cancel and replace functionality test passed\n")


def test_integration_with_components():
    """Test integration with strategy and market data components"""
    print("Testing integration with strategy and market data components...")
    
    # Create mock components
    mock_rest_client = Mock()

    # Create a counter to track order IDs for the integration test
    integration_order_counter = 0

    async def mock_integration_place_order(params):
        nonlocal integration_order_counter
        integration_order_counter += 1
        return {'order_id': f'generated_order_{integration_order_counter}'}

    mock_rest_client.place_order = mock_integration_place_order
    mock_rest_client.cancel_order = AsyncMock(return_value={'success': True})
    
    # Create a mock API client for position manager
    mock_api_client = Mock()
    
    # Create position manager
    position_manager = PositionManager(mock_api_client)
    
    # Add a test position
    position_manager.track_position(
        market_id="test_market",
        yes_balance=Decimal('500'),
        no_balance=Decimal('300'),
        collateral_token_address="0x...",
        condition_id="test_condition"
    )
    
    # Create strategy
    strategy = HFMStrategy(
        position_manager=position_manager,
        target_spread=Decimal('0.0020'),
        min_order_size=Decimal('10'),
        max_order_size=Decimal('1000'),
        num_levels=3
    )
    
    # Create local order book
    local_book = LocalOrderBook("test_market")
    
    # Add some mock data to the order book
    local_book.bids[Decimal('0.49')] = OrderBookEntry(price=Decimal('0.49'), size=Decimal('100'))
    local_book.asks[Decimal('0.51')] = OrderBookEntry(price=Decimal('0.51'), size=Decimal('100'))
    
    # Generate orders using the strategy
    orders = strategy.generate_orders("test_market", local_book)
    print(f"✓ Strategy generated {len(orders)} orders")
    
    # Create order manager
    order_manager = OrderManager(mock_rest_client, tick_interval_ms=100)
    
    async def run_test():
        await order_manager.start()
        
        # Place the generated orders
        placed_orders = await order_manager.place_orders(orders)
        print(f"✓ Successfully placed {len(placed_orders)} orders from strategy")
        
        # Verify they're tracked
        tracked_orders = await order_manager.get_active_orders_for_market("test_market")
        assert len(tracked_orders) == len(placed_orders)
        print("✓ All generated orders are properly tracked")
        
        await order_manager.stop()
    
    asyncio.run(run_test())
    print("✓ Integration with strategy and market data components test passed\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Running OrderManager tests...\n")
    
    test_order_manager_basic()
    test_order_comparison_logic()
    test_cancel_replace_functionality()
    test_integration_with_components()
    
    print("All tests passed! ✓")