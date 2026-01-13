#!/usr/bin/env python3
"""
Main entry point for Polymarket Market Maker Bot
"""
import asyncio
import logging
from typing import Dict, Any

from .api.client import PolymarketRestClient, PolymarketWsClient, Credentials
from .api.connection_manager import ConnectionManager
from .config.settings import load_config
from .market_data.service import MarketDataService


async def main():
    """Main function to run the market maker bot"""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger = logging.getLogger(__name__)

    # Load configuration
    config = load_config()

    # Validate configuration
    if not config.api_key or not config.secret_key or not config.wallet_address:
        raise ValueError("Missing required configuration: API key, secret key, or wallet address")

    # Create credentials object
    credentials = Credentials(
        api_key=config.api_key,
        secret_key=config.secret_key,
        wallet_address=config.wallet_address
    )

    # Initialize REST client
    async with PolymarketRestClient(credentials, config.base_url) as rest_client:
        logger.info("REST client initialized")

        # Test REST API connection
        try:
            markets = await rest_client.get_markets()
            logger.info(f"Successfully fetched {len(markets.get('data', []))} markets")
        except Exception as e:
            logger.error(f"Failed to connect to REST API: {e}")
            return

    # Initialize market data service (this includes WebSocket connection management)
    market_data_service = MarketDataService(
        credentials=credentials,
        ws_url=config.ws_url
    )

    # Define a callback for order book updates
    def on_orderbook_update(market_id: str, order_book):
        logger.info(f"Order book updated for {market_id}")
        metrics = market_data_service.get_market_metrics(market_id)
        logger.info(f"  Mid-price: {metrics.get('mid_price')}, Spread: {metrics.get('spread')}")

    try:
        # Start the market data service
        await market_data_service.start()
        logger.info("Market data service started")

        # Example market ID - in a real scenario, you would get this from your market selection logic
        example_market_id = "example-market-id"  # Replace with actual market ID

        # Register the callback
        market_data_service.register_update_callback(example_market_id, on_orderbook_update)

        # Subscribe to the market
        await market_data_service.subscribe_to_market(example_market_id)
        logger.info(f"Subscribed to market: {example_market_id}")

        # Keep the bot running
        while True:
            # You can access market metrics at any time
            all_metrics = market_data_service.get_all_markets_metrics()
            for market_id, metrics in all_metrics.items():
                mid_price = metrics.get('mid_price')
                spread = metrics.get('spread')
                if mid_price is not None and spread is not None:
                    logger.debug(f"Market {market_id}: Mid-price: {mid_price:.4f}, Spread: {spread:.4f}")

            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
    finally:
        await market_data_service.stop()


if __name__ == "__main__":
    asyncio.run(main())