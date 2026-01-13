#!/usr/bin/env python3
"""
Main entry point for Polymarket Market Maker Bot
"""
import asyncio
import logging
from typing import Dict, Any
from decimal import Decimal

from .api.client import PolymarketRestClient, PolymarketWsClient, Credentials
from .api.connection_manager import ConnectionManager
from .config.settings import load_config
from .market_data.order_book_engine import MarketDataIngestionEngine
from .strategies.hfmm_strategy import HFMStrategy, OrderBatcher
from .utils.position_manager import PositionManager
from .utils.order_manager import OrderManager
from .utils.risk_manager import RiskManager


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

        # Initialize the market data ingestion engine
        market_data_engine = MarketDataIngestionEngine(
            credentials=credentials,
            ws_url=config.ws_url
        )

        # Initialize position manager
        from .api.blockchain_client import PolymarketCTFApiClient
        # Using mock for now - in production this would be a real API client
        mock_api_client = __import__('unittest.mock').Mock()
        position_manager = PositionManager(mock_api_client)

        # Initialize the RiskManager with safety parameters
        risk_manager = RiskManager(
            position_manager=position_manager,
            max_exposure=Decimal('1000'),           # Max $1000 exposure
            kill_switch_threshold=Decimal('0.10'),  # 10% loss threshold
            fat_finger_threshold=Decimal('0.05'),   # 5% price deviation
            starting_balance=Decimal('10000')       # Starting balance assumption
        )

        # Initialize the HFMM strategy
        strategy = HFMStrategy(
            position_manager=position_manager,
            target_spread=Decimal('0.0020'),  # 20 bps
            min_order_size=Decimal('10'),
            max_order_size=Decimal('1000'),
            num_levels=5
        )

        # Initialize the OrderManager with a 100ms tick interval and risk manager
        order_manager = OrderManager(
            rest_client=rest_client,
            tick_interval_ms=100,
            risk_manager=risk_manager
        )

        # Define market ID to track (this would be a real market ID from Polymarket)
        market_id = "Will Bitcoin hit $100k?"  # Example market ID

        # Register callbacks for different types of updates
        def on_order_book_update(local_book):
            logger.info(f"Order book updated for {local_book.market_id}")
            best_bid = local_book.get_best_bid()
            best_ask = local_book.get_best_ask()
            if best_bid and best_ask:
                logger.info(f"Best Bid: {best_bid.price} @ {best_bid.size}, Best Ask: {best_ask.price} @ {best_ask.size}")

                # Orders will be managed by the event loop, so we don't place them here directly

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

            # Start the order manager
            await order_manager.start()
            logger.info("Order manager started")

            # Subscribe to the market
            market_data_engine.subscribe_to_market(market_id)
            logger.info(f"Subscribed to market: {market_id}")

            # Simulate adding a position to demonstrate the strategy
            position_manager.track_position(
                market_id=market_id,
                yes_balance=Decimal('500'),
                no_balance=Decimal('300'),
                collateral_token_address="0x...",
                condition_id="test_condition"
            )
            logger.info("Added sample position for demonstration")

            # Start the main event loop for order management
            event_loop_task = asyncio.create_task(
                order_manager.run_event_loop(strategy, market_data_engine)
            )

            # Keep the bot running
            while True:
                await asyncio.sleep(1)

                # Check if the risk manager indicates immediate shutdown
                if risk_manager.should_shutdown_immediately():
                    logger.critical("Risk manager triggered immediate shutdown!")
                    break

                # You can access the current state at any time:
                current_mid_price = market_data_engine.get_current_mid_price(market_id)
                current_spread = market_data_engine.get_current_spread(market_id)

                if current_mid_price:
                    logger.info(f"Current mid-price from external access: {current_mid_price}")
                if current_spread:
                    logger.info(f"Current spread from external access: {current_spread}")

                # Log order status
                order_count = await order_manager.get_order_count_for_market(market_id)
                logger.info(f"Active orders for {market_id}: {order_count}")

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            # Cancel the event loop task
            if 'event_loop_task' in locals():
                event_loop_task.cancel()
                try:
                    await event_loop_task
                except asyncio.CancelledError:
                    pass

            # Stop the order manager
            await order_manager.stop()

            # Stop the market data engine
            await market_data_engine.stop()


if __name__ == "__main__":
    asyncio.run(main())