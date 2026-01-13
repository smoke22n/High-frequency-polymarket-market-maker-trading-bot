"""
Example usage of the HFMM Strategy
"""
from decimal import Decimal
from unittest.mock import Mock
from polymarket_mm_bot.strategies.hfmm_strategy import HFMStrategy, OrderBatcher
from polymarket_mm_bot.market_data.order_book_engine import LocalOrderBook, OrderBookSnapshot, OrderBookEntry
from polymarket_mm_bot.utils.position_manager import PositionManager


def main():
    print("HFMM Strategy Example")
    print("=" * 50)
    
    # Create mock API client and position manager
    mock_api_client = Mock()
    position_manager = PositionManager(mock_api_client)
    
    # Add a position that's NO-heavy (more NO than YES tokens)
    position_manager.track_position(
        market_id="test_market_1",
        yes_balance=Decimal('30'),
        no_balance=Decimal('70'),
        collateral_token_address="0x...",
        condition_id="test_condition_1"
    )
    
    print(f"Initial position: YES={position_manager.get_position('test_market_1').yes_balance}, "
          f"NO={position_manager.get_position('test_market_1').no_balance}")
    
    # Create the strategy with custom parameters
    strategy = HFMStrategy(
        position_manager=position_manager,
        target_spread=Decimal('0.0020'),  # 20 bps
        min_order_size=Decimal('10'),
        max_order_size=Decimal('100'),
        num_levels=3
    )
    
    # Create a local order book with current market data
    local_book = LocalOrderBook("test_market_1")
    snapshot = OrderBookSnapshot(
        bids=[
            OrderBookEntry(Decimal('0.49'), Decimal('100')),
            OrderBookEntry(Decimal('0.48'), Decimal('150'))
        ],
        asks=[
            OrderBookEntry(Decimal('0.51'), Decimal('100')),
            OrderBookEntry(Decimal('0.52'), Decimal('150'))
        ]
    )
    local_book.apply_snapshot(snapshot)
    
    print(f"Current mid-price: {local_book.get_mid_price()}")
    
    # Calculate skew
    skew = strategy.calculate_skew("test_market_1")
    print(f"Position skew: {skew}")
    
    # Adjust prices for skew
    mid_price = local_book.get_mid_price()
    bid_price, ask_price = strategy.adjust_prices_for_skew(mid_price, skew)
    print(f"Adjusted bid price: {bid_price}")
    print(f"Adjusted ask price: {ask_price}")
    
    # Calculate order sizes
    bid_size, ask_size = strategy.calculate_order_sizes("test_market_1")
    print(f"Suggested bid size: {bid_size}")
    print(f"Suggested ask size: {ask_size}")
    
    # Generate orders
    orders = strategy.generate_orders("test_market_1", local_book)
    print(f"\nGenerated {len(orders)} orders:")
    
    for i, order in enumerate(orders):
        print(f"  {i+1}. {order.side.upper()} {order.size} @ {order.price} (Market: {order.market_id})")
    
    # Batch the orders for API submission
    batcher = OrderBatcher(max_batch_size=5)
    batches = batcher.batch_orders(orders)
    
    print(f"\nOrders batched into {len(batches)} batch(es) for API submission")
    for i, batch in enumerate(batches):
        print(f"  Batch {i+1}: {len(batch)} orders")
        for order_dict in batch:
            print(f"    - {order_dict['side'].upper()} {order_dict['size']} @ {order_dict['price']}")
    
    print("\n" + "=" * 50)
    print("Strategy demonstration completed!")


if __name__ == "__main__":
    main()