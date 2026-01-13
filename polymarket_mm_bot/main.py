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
from .market_data.order_book_engine import MarketDataIngestionEngine


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
    # Initialize the market data ingestion engine
    market_data_engine = MarketDataIngestionEngine(
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
    # Define market ID to track (this would be a real market ID from Polymarket)
    market_id = "Will Bitcoin hit $100k?"  # Example market ID

    # Register callbacks for different types of updates
    def on_order_book_update(local_book):
        logger.info(f"Order book updated for {local_book.market_id}")
        best_bid = local_book.get_best_bid()
        best_ask = local_book.get_best_ask()
        if best_bid and best_ask:
            logger.info(f"Best Bid: {best_bid.price} @ {best_bid.size}, Best Ask: {best_ask.price} @ {best_ask.size}")

    def on_mid_price_update(mid_price):
        logger.info(f"Mid-price updated: {mid_price}")

    def on_spread_update(spread):
        logger.info(f"Spread updated: {spread}")

    # Register the callbacks
    market_data_engine.register_update_callback(market_id, on_order_book_update)
    market_data_engine.register_mid_price_callback(market_id, on_mid_price_update)
    market_data_engine.register_spread_callback(market_id, on_spread_update)

    try:
        # Start the market data ingestion engine
        await market_data_engine.start()
        logger.info("Market data ingestion engine started")

        # Subscribe to the market
        market_data_engine.subscribe_to_market(market_id)
        logger.info(f"Subscribed to market: {market_id}")

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
            # You can access the current state at any time:
            current_mid_price = market_data_engine.get_current_mid_price(market_id)
            current_spread = market_data_engine.get_current_spread(market_id)

            if current_mid_price:
                logger.info(f"Current mid-price from external access: {current_mid_price}")
            if current_spread:
                logger.info(f"Current spread from external access: {current_spread}")

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
    finally:
        await market_data_service.stop()
        await market_data_engine.stop()


if __name__ == "__main__":
    asyncio.run(main())