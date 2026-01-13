# Market Data Ingestion Engine

The Market Data Ingestion Engine is a real-time market data processing system that maintains a local, synchronized mirror of Polymarket order books.

## Features

- **Real-time Order Book Mirroring**: Maintains a local copy of the order book for specific market IDs that stays synchronized with the exchange
- **WebSocket Subscription**: Automatically subscribes to relevant WebSocket channels for market token IDs
- **Delta Processing**: Efficiently buffers and applies incoming delta updates to the local order book
- **Metrics Calculation**: Dynamically calculates mid-price and spread every 100ms
- **Callback System**: Provides hooks for custom logic when order books are updated

## Architecture

```
┌─────────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│   Polymarket    │───▶│  Market Data Engine  │───▶│  Local Order     │
│   WebSocket     │    │                      │    │  Books           │
└─────────────────┘    └──────────────────────┘    └──────────────────┘
                              │
                       ┌──────────────────────┐
                       │  Metrics Calculator  │
                       │  (every 100ms)       │
                       └──────────────────────┘
```

### Key Components

1. **MarketDataIngestionEngine**: Core engine that manages WebSocket connections, processes updates, and maintains order book state
2. **LocalOrderBook**: Represents a single market's order book with bid/ask levels
3. **OrderBookDelta**: Represents incremental changes to the order book
4. **MarketDataService**: High-level service layer for easy integration

## Usage

### Basic Example

```python
import asyncio
from polymarket_mm_bot.api.client import Credentials
from polymarket_mm_bot.market_data.service import MarketDataService

async def main():
    # Initialize credentials
    credentials = Credentials(
        api_key="your_api_key",
        secret_key="your_secret_key", 
        wallet_address="your_wallet_address"
    )
    
    # Create market data service
    service = MarketDataService(credentials)
    
    # Define a callback for order book updates
    def on_orderbook_update(market_id: str, order_book):
        metrics = service.get_market_metrics(market_id)
        print(f"Updated {market_id}: Mid-price: {metrics['mid_price']}, Spread: {metrics['spread']}")
    
    try:
        # Start the service
        await service.start()
        
        # Register callback
        service.register_update_callback("your-market-id", on_orderbook_update)
        
        # Subscribe to market
        await service.subscribe_to_market("your-market-id")
        
        # Access metrics anytime
        while True:
            metrics = service.get_market_metrics("your-market-id")
            print(f"Current metrics: {metrics}")
            await asyncio.sleep(1)
            
    finally:
        await service.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### Advanced Usage

```python
# Get top of book (best bid and ask)
best_bid, best_ask = service.get_top_of_book("your-market-id")

# Get all market metrics
all_metrics = service.get_all_markets_metrics()

# Unsubscribe from a market
await service.unsubscribe_from_market("your-market-id")
```

## Data Model

### OrderBookEntry
- `price`: Price level (Decimal)
- `size`: Quantity at that price level (Decimal)
- `timestamp`: When the entry was last updated

### LocalOrderBook
- `market_id`: Identifier for the market
- `bids`: Dictionary of bid levels (price -> OrderBookEntry)
- `asks`: Dictionary of ask levels (price -> OrderBookEntry)
- `last_update_time`: Timestamp of last update

### Calculated Metrics
- `mid_price`: (Best Bid + Best Ask) / 2
- `spread`: Best Ask - Best Bid  
- `spread_percentage`: (Spread / Mid-price) * 100

## Error Handling

The engine includes robust error handling:
- Automatic reconnection to WebSocket
- Graceful degradation when individual market subscriptions fail
- Detailed logging for debugging
- Isolated failure handling (one market failure doesn't affect others)

## Performance Characteristics

- Delta updates applied in O(1) time complexity
- Efficient memory usage with bounded buffers
- 100ms refresh rate for metrics calculation
- Concurrent processing of multiple markets