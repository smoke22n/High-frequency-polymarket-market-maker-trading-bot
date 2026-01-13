"""
Test suite for the HFMM Strategy implementation
"""
import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock
from polymarket_mm_bot.strategies.hfmm_strategy import HFMStrategy, Order, SkewParameters
from polymarket_mm_bot.market_data.order_book_engine import LocalOrderBook
from polymarket_mm_bot.utils.position_manager import PositionManager, Position


def test_skew_calculation_yes_heavy():
    """Test skew calculation when holding more YES tokens"""
    # Create mock position manager
    mock_api_client = Mock()
    position_manager = PositionManager(mock_api_client)
    
    # Add a position with more YES tokens than NO tokens
    position_manager.track_position(
        market_id="test_market",
        yes_balance=Decimal('70'),
        no_balance=Decimal('30'),
        collateral_token_address="0x...",
        condition_id="test_condition"
    )
    
    strategy = HFMStrategy(position_manager)
    skew = strategy.calculate_skew("test_market")
    
    # Should be positive since YES-heavy
    assert skew > 0
    assert abs(skew) <= Decimal('0.1')  # Max skew is 0.1 by default


def test_skew_calculation_no_heavy():
    """Test skew calculation when holding more NO tokens"""
    # Create mock position manager
    mock_api_client = Mock()
    position_manager = PositionManager(mock_api_client)
    
    # Add a position with more NO tokens than YES tokens
    position_manager.track_position(
        market_id="test_market",
        yes_balance=Decimal('30'),
        no_balance=Decimal('70'),
        collateral_token_address="0x...",
        condition_id="test_condition"
    )
    
    strategy = HFMStrategy(position_manager)
    skew = strategy.calculate_skew("test_market")
    
    # Should be negative since NO-heavy
    assert skew < 0
    assert abs(skew) <= Decimal('0.1')  # Max skew is 0.1 by default


def test_skew_calculation_neutral():
    """Test skew calculation when holding equal YES and NO tokens"""
    # Create mock position manager
    mock_api_client = Mock()
    position_manager = PositionManager(mock_api_client)
    
    # Add a position with equal YES and NO tokens
    position_manager.track_position(
        market_id="test_market",
        yes_balance=Decimal('50'),
        no_balance=Decimal('50'),
        collateral_token_address="0x...",
        condition_id="test_condition"
    )
    
    strategy = HFMStrategy(position_manager)
    skew = strategy.calculate_skew("test_market")
    
    # Should be approximately 0 since balanced
    assert skew == Decimal('0')


def test_adjust_prices_for_skew_yes_heavy():
    """Test price adjustment when YES-heavy (should lower bid, raise ask)"""
    # Create mock position manager
    mock_api_client = Mock()
    position_manager = PositionManager(mock_api_client)
    
    # Add a position with more YES tokens than NO tokens
    position_manager.track_position(
        market_id="test_market",
        yes_balance=Decimal('80'),
        no_balance=Decimal('20'),
        collateral_token_address="0x...",
        condition_id="test_condition"
    )
    
    strategy = HFMStrategy(position_manager)
    mid_price = Decimal('0.50')
    
    # Calculate skew
    skew = strategy.calculate_skew("test_market")
    assert skew > 0  # YES-heavy
    
    # Adjust prices for skew
    bid_price, ask_price = strategy.adjust_prices_for_skew(mid_price, skew)
    
    # With YES-heavy position, should lower bid and raise ask
    assert bid_price < mid_price
    assert ask_price > mid_price
    assert bid_price < ask_price


def test_adjust_prices_for_skew_no_heavy():
    """Test price adjustment when NO-heavy (should raise bid, lower ask)"""
    # Create mock position manager
    mock_api_client = Mock()
    position_manager = PositionManager(mock_api_client)

    # Add a position with more NO tokens than YES tokens
    position_manager.track_position(
        market_id="test_market",
        yes_balance=Decimal('20'),
        no_balance=Decimal('80'),
        collateral_token_address="0x...",
        condition_id="test_condition"
    )

    strategy = HFMStrategy(position_manager)
    mid_price = Decimal('0.50')

    # Calculate skew
    skew = strategy.calculate_skew("test_market")
    assert skew < 0  # NO-heavy

    # Adjust prices for skew
    bid_price, ask_price = strategy.adjust_prices_for_skew(mid_price, skew)

    # With NO-heavy position, should raise bid (compared to neutral) and lower ask (compared to neutral)
    # But still maintain bid < ask and typically bid < mid < ask
    neutral_half_spread = strategy.target_spread / 2
    neutral_bid = mid_price - neutral_half_spread
    neutral_ask = mid_price + neutral_half_spread

    # With NO-heavy position, bid should be higher than neutral bid and ask should be lower than neutral ask
    assert bid_price > neutral_bid  # More aggressive buying (higher bid)
    assert ask_price < neutral_ask  # Less aggressive selling (lower ask)
    assert bid_price < ask_price  # Still maintain bid < ask


def test_generate_orders_basic():
    """Test basic order generation"""
    # Create mock position manager
    mock_api_client = Mock()
    position_manager = PositionManager(mock_api_client)
    
    # Add a neutral position
    position_manager.track_position(
        market_id="test_market",
        yes_balance=Decimal('50'),
        no_balance=Decimal('50'),
        collateral_token_address="0x...",
        condition_id="test_condition"
    )
    
    strategy = HFMStrategy(position_manager, num_levels=2)
    
    # Create a local order book with a mid-price
    local_book = LocalOrderBook("test_market")
    from polymarket_mm_bot.market_data.order_book_engine import OrderBookSnapshot, OrderBookEntry
    snapshot = OrderBookSnapshot(
        bids=[OrderBookEntry(Decimal('0.49'), Decimal('100'))],
        asks=[OrderBookEntry(Decimal('0.51'), Decimal('100'))]
    )
    local_book.apply_snapshot(snapshot)
    
    # Generate orders
    orders = strategy.generate_orders("test_market", local_book)
    
    # Should have some orders generated
    assert len(orders) > 0
    assert all(isinstance(order, Order) for order in orders)
    
    # Check that orders have appropriate properties
    for order in orders:
        assert order.market_id == "test_market"
        assert order.side in ['buy', 'sell']
        assert order.price > 0 and order.price < 1
        assert order.size > 0


def test_generate_orders_with_skew():
    """Test order generation with position skew"""
    # Create mock position manager
    mock_api_client = Mock()
    position_manager = PositionManager(mock_api_client)
    
    # Add a YES-heavy position
    position_manager.track_position(
        market_id="test_market",
        yes_balance=Decimal('90'),
        no_balance=Decimal('10'),
        collateral_token_address="0x...",
        condition_id="test_condition"
    )
    
    strategy = HFMStrategy(position_manager, num_levels=1)
    
    # Create a local order book with a mid-price
    local_book = LocalOrderBook("test_market")
    from polymarket_mm_bot.market_data.order_book_engine import OrderBookSnapshot, OrderBookEntry
    snapshot = OrderBookSnapshot(
        bids=[OrderBookEntry(Decimal('0.49'), Decimal('100'))],
        asks=[OrderBookEntry(Decimal('0.51'), Decimal('100'))]
    )
    local_book.apply_snapshot(snapshot)
    
    # Generate orders
    orders = strategy.generate_orders("test_market", local_book)
    
    # Should have some orders generated
    assert len(orders) > 0
    
    # With YES-heavy position, should see more sell orders or higher ask prices
    sell_orders = [o for o in orders if o.side == 'sell']
    buy_orders = [o for o in orders if o.side == 'buy']
    
    # The strategy should generate both buy and sell orders, but prices should reflect the skew


def test_order_batcher():
    """Test the OrderBatcher functionality"""
    from polymarket_mm_bot.strategies.hfmm_strategy import OrderBatcher
    
    # Create some sample orders
    orders = [
        Order("market1", "buy", Decimal('0.49'), Decimal('100')),
        Order("market1", "sell", Decimal('0.51'), Decimal('100')),
        Order("market2", "buy", Decimal('0.48'), Decimal('200')),
    ]
    
    batcher = OrderBatcher(max_batch_size=2)
    batches = batcher.batch_orders(orders)
    
    # Should have 2 batches since max batch size is 2 and we have 3 orders
    assert len(batches) == 2
    assert len(batches[0]) == 2  # First batch has 2 orders
    assert len(batches[1]) == 1  # Second batch has 1 order
    
    # Check that the batched orders have the correct structure
    for batch in batches:
        for order_dict in batch:
            assert 'market_id' in order_dict
            assert 'side' in order_dict
            assert 'price' in order_dict
            assert 'size' in order_dict


if __name__ == "__main__":
    pytest.main([__file__])