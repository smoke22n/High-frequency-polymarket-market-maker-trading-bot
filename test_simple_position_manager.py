#!/usr/bin/env python3
"""
Simple test script to verify the PositionManager functionality works.
"""

from decimal import Decimal
from unittest.mock import AsyncMock
from polymarket_mm_bot.utils.position_manager import PositionManager, Position
from polymarket_mm_bot.api.blockchain_client import PolymarketCTFApiClient


async def test_basic_functionality():
    """Test basic PositionManager functionality."""
    print("Testing PositionManager functionality...")
    
    # Create a mock API client
    mock_api_client = AsyncMock()
    mock_api_client.wallet_address = "0x1234567890123456789012345678901234567890"
    mock_api_client.ctf_exchange_contract_address = "0xabcdef1234567890abcdef1234567890abcdef12"
    mock_api_client.send_transaction = AsyncMock(return_value="0xtxhash123456789")
    
    # Create PositionManager
    position_manager = PositionManager(api_client=mock_api_client)
    
    # Test 1: Track a position
    print("\n1. Testing position tracking...")
    market_id = "test_market_1"
    position_manager.track_position(
        market_id=market_id,
        yes_balance=Decimal("100"),
        no_balance=Decimal("50"),
        collateral_token_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        condition_id="0xcondition123"
    )
    
    position = position_manager.get_position(market_id)
    print(f"   Position tracked: YES={position.yes_balance}, NO={position.no_balance}")
    assert position.yes_balance == Decimal("100")
    assert position.no_balance == Decimal("50")
    
    # Test 2: Update balances
    print("\n2. Testing balance updates...")
    position_manager.update_position_balances(
        market_id=market_id,
        yes_delta=Decimal("-20"),
        no_delta=Decimal("30")
    )
    
    updated_position = position_manager.get_position(market_id)
    print(f"   Updated position: YES={updated_position.yes_balance}, NO={updated_position.no_balance}")
    assert updated_position.yes_balance == Decimal("80")  # 100 - 20
    assert updated_position.no_balance == Decimal("80")   # 50 + 30
    
    # Test 3: Get hedgeable amount
    print("\n3. Testing hedgeable amount calculation...")
    hedgeable = position_manager.get_hedgeable_amount(market_id)
    print(f"   Hedgeable amount: {hedgeable}")
    assert hedgeable == Decimal("80")  # min(80, 80)
    
    # Test 4: Get net exposure
    print("\n4. Testing net exposure calculation...")
    exposure, direction = position_manager.get_net_exposure(market_id)
    print(f"   Net exposure: {exposure}, Direction: {direction}")
    assert exposure == Decimal("0")  # Equal balances = no net exposure
    assert direction == "NO"  # Neutral case
    
    # Test 5: Create unequal position and test net exposure
    print("\n5. Testing net exposure with unequal balances...")
    market_id_2 = "test_market_2"
    position_manager.track_position(
        market_id=market_id_2,
        yes_balance=Decimal("120"),
        no_balance=Decimal("80"),
        collateral_token_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        condition_id="0xcondition456"
    )
    
    exposure, direction = position_manager.get_net_exposure(market_id_2)
    print(f"   Net exposure: {exposure}, Direction: {direction}")
    assert exposure == Decimal("40")  # 120 - 80
    assert direction == "YES"  # More YES than NO
    
    # Test 6: Test merge positions (simulation)
    print("\n6. Testing merge positions (simulation)...")
    result = await position_manager.merge_positions(market_id, amount=Decimal("50"))
    print(f"   Merge result: {result}")
    assert result == True
    
    # Check that balances were updated
    merged_position = position_manager.get_position(market_id)
    print(f"   After merge: YES={merged_position.yes_balance}, NO={merged_position.no_balance}")
    assert merged_position.yes_balance == Decimal("30")  # 80 - 50
    assert merged_position.no_balance == Decimal("30")   # 80 - 50
    
    # Test 7: Test split collateral (simulation)
    print("\n7. Testing split collateral (simulation)...")
    result = await position_manager.split_collateral(market_id_2, Decimal("25"))
    print(f"   Split result: {result}")
    assert result == True
    
    # Check that balances were updated
    split_position = position_manager.get_position(market_id_2)
    print(f"   After split: YES={split_position.yes_balance}, NO={split_position.no_balance}")
    # Original: YES=120, NO=80. After split: YES=120+25=145, NO=80+25=105
    assert split_position.yes_balance == Decimal("145")
    assert split_position.no_balance == Decimal("105")
    
    print("\n✅ All tests passed! PositionManager is working correctly.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_basic_functionality())