"""
Example usage of the Market Data Ingestion Engine
"""
import asyncio
import os
from decimal import Decimal

from polymarket_mm_bot.market_data.order_book_engine import MarketDataIngestionEngine
from polymarket_mm_bot.api.client import Credentials


async def main():
    # Create credentials (these would normally come from environment variables)
    credentials = Credentials(
        api_key=os.getenv("POLYMARKET_API_KEY", "your_api_key_here"),
        secret_key=os.getenv("POLYMARKET_SECRET_KEY", "your_secret_key_here"),
        wallet_address=os.getenv("POLYMARKET_WALLET_ADDRESS", "your_wallet_address_here")
    )
    
    # Initialize the market data ingestion engine
    engine = MarketDataIngestionEngine(credentials)
    
    # Define market ID to track (this would be a real market ID from Polymarket)
    market_id = "Will Bitcoin hit $100k?"  # Example market ID
    
    # Register callbacks for different types of updates
    def on_order_book_update(local_book):
        print(f"Order book updated for {local_book.market_id}")
        best_bid = local_book.get_best_bid()
        best_ask = local_book.get_best_ask()
        if best_bid and best_ask:
            print(f"Best Bid: {best_bid.price} @ {best_bid.size}, Best Ask: {best_ask.price} @ {best_ask.size}")
    
    def on_mid_price_update(mid_price: Decimal):
        print(f"Mid-price updated: {mid_price}")
    
    def on_spread_update(spread: Decimal):
        print(f"Spread updated: {spread}")
    
    # Register the callbacks
    engine.register_update_callback(market_id, on_order_book_update)
    engine.register_mid_price_callback(market_id, on_mid_price_update)
    engine.register_spread_callback(market_id, on_spread_update)
    
    # Start the engine
    await engine.start()
    
    # Subscribe to the market
    engine.subscribe_to_market(market_id)
    print(f"Subscribed to market: {market_id}")
    
    try:
        # Keep the engine running
        while True:
            await asyncio.sleep(1)
            # You can access the current state at any time:
            current_mid_price = engine.get_current_mid_price(market_id)
            current_spread = engine.get_current_spread(market_id)
            
            if current_mid_price:
                print(f"Current mid-price from external access: {current_mid_price}")
            if current_spread:
                print(f"Current spread from external access: {current_spread}")
                
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())