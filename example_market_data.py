"""
Example usage of the Market Data Ingestion Engine
"""
import asyncio
import os
from dotenv import load_dotenv

from polymarket_mm_bot.api.client import Credentials
from polymarket_mm_bot.market_data.service import MarketDataService
from polymarket_mm_bot.config.settings import load_config


async def example_usage():
    """Example of how to use the Market Data Ingestion Engine"""
    # Load environment variables
    load_dotenv()
    
    # Load config
    config = load_config()
    
    # Validate configuration
    if not config.api_key or not config.secret_key or not config.wallet_address:
        print("ERROR: Missing required environment variables:")
        print("- POLYMARKET_API_KEY")
        print("- POLYMARKET_SECRET_KEY") 
        print("- POLYMARKET_WALLET_ADDRESS")
        print("\nPlease set these environment variables before running the example.")
        return

    # Create credentials
    credentials = Credentials(
        api_key=config.api_key,
        secret_key=config.secret_key,
        wallet_address=config.wallet_address
    )

    # Create market data service
    service = MarketDataService(credentials)

    # Define a callback to handle order book updates
    def on_orderbook_update(market_id: str, order_book):
        metrics = service.get_market_metrics(market_id)
        print(f"Order book updated for {market_id}")
        print(f"  Mid-price: {metrics.get('mid_price')}")
        print(f"  Spread: {metrics.get('spread')}")
        print(f"  Spread %: {metrics.get('spread_percentage')}")

    try:
        # Start the service
        await service.start()
        print("Market data service started")

        # Example market ID - replace with an actual market ID from Polymarket
        market_id = "will-bitcoin-hit-100k-by-2024"  # Example market ID
        
        # Register the callback
        service.register_update_callback(market_id, on_orderbook_update)

        # Subscribe to the market
        await service.subscribe_to_market(market_id)
        print(f"Subscribed to market: {market_id}")

        # Keep the service running and periodically print metrics
        for i in range(100):  # Run for 10 seconds (100 * 0.1s)
            all_metrics = service.get_all_markets_metrics()
            if market_id in all_metrics:
                metrics = all_metrics[market_id]
                mid_price = metrics.get('mid_price')
                spread = metrics.get('spread')
                if mid_price is not None and spread is not None:
                    print(f"Market: {market_id}, Mid-price: {mid_price:.4f}, Spread: {spread:.4f}")
            
            await asyncio.sleep(0.1)  # Wait 100ms

    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await service.stop()
        print("Market data service stopped")


if __name__ == "__main__":
    asyncio.run(example_usage())