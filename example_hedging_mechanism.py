"""
Example usage of the PositionManager with hedging functionality.
Demonstrates the primary hedging mechanism using the Gnosis Conditional Tokens Framework (CTF).
"""

import asyncio
from decimal import Decimal
from polymarket_mm_bot.utils.position_manager import PositionManager
from polymarket_mm_bot.api.blockchain_client import PolymarketCTFApiClient
from polymarket_mm_bot.utils.proxy_wallet import ProxyWallet


async def example_hedging_workflow():
    """
    Example workflow demonstrating the hedging mechanism:
    1. Track positions in a market
    2. Monitor hedgeable amount
    3. Merge equal YES/NO tokens to hedge risk
    4. Split collateral back to inventory when needed
    """
    print("🚀 Starting Polymarket Hedging Example")
    print("=" * 50)
    
    # Initialize API client (in production, you'd use real credentials)
    api_client = PolymarketCTFApiClient(
        wallet_address="0xYourWalletAddressHere",
        ctf_exchange_contract_address="0xCTFExchangeContractAddress",
        rpc_url="https://polygon-rpc.com/"
    )
    
    # Initialize proxy wallet for gas-efficient transactions (optional)
    # Using a dummy private key for demonstration - in production use a real key
    dummy_private_key = "0x56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d82cc"
    proxy_wallet = ProxyWallet(
        private_key=dummy_private_key,  # In production, store securely
        rpc_url="https://polygon-rpc.com/",
        # Commenting out relayer for demo purposes - uncomment when you have a real relayer
        # relayer_url="https://your-relayer-service.com/api/v1/relay"  # Optional
    )
    
    # Create PositionManager
    # For this example, we'll use the API client directly without proxy for simplicity
    position_manager = PositionManager(
        api_client=api_client,
        # proxy_wallet=proxy_wallet  # Optional, for gas efficiency - commented out for demo
    )
    
    # Market details (these would come from Polymarket API in real usage)
    market_id = "0xMarketId123456789"
    condition_id = "0xConditionId987654321"
    usdc_address = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"  # USDC on Polygon
    
    print(f"\n📊 Setting up position tracking for market: {market_id}")
    
    # 1. Start with some inventory positions
    position_manager.track_position(
        market_id=market_id,
        yes_balance=Decimal("1000"),  # Holding 1000 YES tokens
        no_balance=Decimal("800"),   # Holding 800 NO tokens
        collateral_token_address=usdc_address,
        condition_id=condition_id
    )
    
    # Check current position
    position = position_manager.get_position(market_id)
    print(f"   Initial position: YES={position.yes_balance}, NO={position.no_balance}")
    
    # 2. Calculate net exposure
    exposure, direction = position_manager.get_net_exposure(market_id)
    print(f"   Net exposure: {exposure} {direction} tokens")
    
    # 3. Calculate hedgeable amount (minimum of YES/NO balances)
    hedgeable = position_manager.get_hedgeable_amount(market_id)
    print(f"   Hedgeable amount: {hedgeable} tokens (can hedge this amount)")
    
    # 4. Perform hedging by merging equal YES/NO tokens
    print(f"\n⚖️  Initiating hedge: merging {hedgeable} YES and {hedgeable} NO tokens")
    
    # This will merge 800 YES and 800 NO tokens into 800 USDC
    merge_success = await position_manager.merge_positions(market_id)
    
    if merge_success:
        print("   ✅ Hedge successful!")
        
        # Check updated position
        updated_pos = position_manager.get_position(market_id)
        print(f"   Post-hedge position: YES={updated_pos.yes_balance}, NO={updated_pos.no_balance}")
        
        # Net exposure after hedge
        exposure, direction = position_manager.get_net_exposure(market_id)
        print(f"   Post-hedge exposure: {exposure} {direction} tokens")
        
        # 5. Optionally, split some collateral back to replenish inventory
        print(f"\n🔄 Replenishing inventory: splitting 200 USDC back to YES/NO tokens")
        
        split_success = await position_manager.split_collateral(market_id, Decimal("200"))
        
        if split_success:
            print("   ✅ Inventory replenishment successful!")
            
            # Check final position
            final_pos = position_manager.get_position(market_id)
            print(f"   Final position: YES={final_pos.yes_balance}, NO={final_pos.no_balance}")
            
            final_exposure, final_direction = position_manager.get_net_exposure(market_id)
            print(f"   Final exposure: {final_exposure} {final_direction} tokens")
        else:
            print("   ❌ Inventory replenishment failed")
    else:
        print("   ❌ Hedge failed")
    
    print("\n🎯 Hedging workflow completed!")
    print("=" * 50)


async def example_risk_management():
    """
    Example of ongoing risk management using the hedging mechanism.
    """
    print("\n🔍 Risk Management Example")
    print("=" * 50)
    
    # Initialize with mock client
    api_client = PolymarketCTFApiClient(
        wallet_address="0xYourWalletAddressHere",
        ctf_exchange_contract_address="0xCTFExchangeContractAddress",
        rpc_url="https://polygon-rpc.com/"
    )
    
    position_manager = PositionManager(api_client=api_client)
    
    market_id = "0xRiskManagementMarket"
    condition_id = "0xConditionIdRisk"
    usdc_address = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    
    # Simulate market making activity that creates imbalanced positions
    position_manager.track_position(
        market_id=market_id,
        yes_balance=Decimal("500"),
        no_balance=Decimal("300"),
        collateral_token_address=usdc_address,
        condition_id=condition_id
    )
    
    print(f"Starting position: YES=500, NO=300")
    
    # Risk management loop
    max_exposure_threshold = Decimal("100")  # Max acceptable exposure
    
    while True:
        exposure, direction = position_manager.get_net_exposure(market_id)
        print(f"Current exposure: {exposure} {direction}")
        
        if exposure > max_exposure_threshold:
            print(f"⚠️  Exposure ({exposure}) exceeds threshold ({max_exposure_threshold})")
            
            # Calculate how much to hedge
            hedge_amount = exposure - max_exposure_threshold
            print(f"   Calculated hedge amount: {hedge_amount}")
            
            # Get current position to determine what we can hedge
            pos = position_manager.get_position(market_id)
            hedgeable = position_manager.get_hedgeable_amount(market_id)
            actual_hedge = min(hedge_amount, hedgeable)
            
            if actual_hedge > 0:
                print(f"   Attempting to hedge: {actual_hedge} tokens")
                
                # Perform hedge
                success = await position_manager.merge_positions(market_id, actual_hedge)
                
                if success:
                    print(f"   ✅ Hedged {actual_hedge} tokens")
                    exposure, direction = position_manager.get_net_exposure(market_id)
                    
                    if exposure <= max_exposure_threshold:
                        print(f"   🎯 Risk reduced to acceptable level: {exposure} {direction}")
                        break
                else:
                    print("   ❌ Hedge failed")
                    break
            else:
                print("   ⚠️  Insufficient hedgeable tokens")
                break
        else:
            print("   ✅ Risk is within acceptable limits")
            break
    
    print("\n🎯 Risk management completed!")


if __name__ == "__main__":
    print("Welcome to the Polymarket Hedging Mechanism Demo!")
    print("This demonstrates the core functionality of the PositionManager class.")
    
    # Run the main hedging example
    asyncio.run(example_hedging_workflow())
    
    # Run the risk management example
    asyncio.run(example_risk_management())
    
    print("\n💡 Key Features Demonstrated:")
    print("   • Position tracking for YES/NO tokens")
    print("   • Net exposure calculation")
    print("   • Hedgeable amount determination")
    print("   • Merging positions to hedge risk")
    print("   • Splitting collateral to replenish inventory")
    print("   • Gas-efficient transactions via proxy wallet")
    print("   • Automated risk management workflows")