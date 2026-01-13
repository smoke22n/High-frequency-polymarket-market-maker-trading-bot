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
    
    # Initialize WebSocket connection manager
    connection_manager = ConnectionManager(
        credentials=credentials,
        ws_url=config.ws_url
    )
    
    # Define a handler for orderbook updates
    async def handle_orderbook_update(data: Dict[str, Any]):
        logger.info(f"Received orderbook update: {data.get('market_id', 'unknown')}")
    
    # Register the handler
    connection_manager.register_handler("orderbook_update", handle_orderbook_update)
    
    try:
        # Start the connection manager
        await connection_manager.start()
        logger.info("Connection manager started")
        
        # Subscribe to some markets (replace with actual market IDs)
        # await connection_manager.subscribe_to_orderbook(["market1", "market2"])
        
        # Keep the bot running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
    finally:
        await connection_manager.stop()


if __name__ == "__main__":
    asyncio.run(main())