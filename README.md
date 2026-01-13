# Polymarket Market Maker Bot

A high-frequency market maker bot for Polymarket's CLOB (Central Limit Order Book).

## Architecture

The bot is structured as follows:

- `api/` - Contains API clients for REST and WebSocket connections
- `utils/` - Utility functions including rate limiting and risk management
- `config/` - Configuration management
- `models/` - Data models (to be implemented)
- `strategies/` - Trading strategies (to be implemented)

## Features

- **REST Client**: For placing/cancelling orders and fetching market data
- **WebSocket Client**: For streaming real-time orderbook data
- **Connection Manager**: Handles WebSocket heartbeats and auto-reconnects
- **Rate Limiter**: Ensures compliance with Polymarket's API limits (500 requests/10s)
- **Authentication**: Secure API authentication using L2 API key and private key
- **Risk Manager**: Implements safety guardrails to protect capital

## Risk Management

The bot includes a comprehensive Risk Manager module with three key safety features:

### 1. Max Exposure Guard
- Limits total inventory exposure to $1000 by default
- Calculates exposure as: (YES + NO tokens) - Hedged sets across all markets
- Rejects new orders if the exposure threshold would be exceeded

### 2. Kill Switch
- Monitors account balance losses over rolling 1-hour periods
- Triggers immediate shutdown if losses exceed 10% of starting balance by default
- Cancels all active orders and stops the bot when activated

### 3. Fat Finger Protection
- Prevents orders that deviate more than 5% from reference prices by default
- Compares against last traded price or best external reference price
- Protects against erroneous pricing due to market anomalies or bugs

### Configuration
The risk parameters can be customized during RiskManager initialization:
```python
risk_manager = RiskManager(
    position_manager=position_manager,
    max_exposure=Decimal('1000'),           # Max $1000 exposure
    kill_switch_threshold=Decimal('0.10'),  # 10% loss threshold
    fat_finger_threshold=Decimal('0.05'),   # 5% price deviation
    starting_balance=Decimal('10000')       # Starting balance assumption
)
```

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up environment variables:
   ```bash
   export POLYMARKET_API_KEY="your_api_key"
   export POLYMARKET_SECRET_KEY="your_secret_key"
   export POLYMARKET_WALLET_ADDRESS="your_wallet_address"
   ```

3. Run the bot:
   ```bash
   python -m polymarket_mm_bot.main
   ```

## Configuration

The bot can be configured using environment variables:

- `POLYMARKET_API_KEY`: Your Polymarket API key
- `POLYMARKET_SECRET_KEY`: Your Polymarket secret key
- `POLYMARKET_WALLET_ADDRESS`: Your wallet address
- `POLYMARKET_BASE_URL`: REST API base URL (default: https://clob.polymarket.com)
- `POLYMARKET_WS_URL`: WebSocket API URL (default: wss://clob.polymarket.com/ws)
- `RATE_LIMIT_MAX_REQUESTS`: Max requests per time window (default: 500)
- `RATE_LIMIT_TIME_WINDOW`: Time window in seconds (default: 10)
- `HEARTBEAT_INTERVAL`: WebSocket heartbeat interval (default: 30s)
- `RECONNECT_DELAY`: Delay between reconnection attempts (default: 5s)
- `MAX_RECONNECT_ATTEMPTS`: Max reconnection attempts (default: 10)

## API Clients

### REST Client
The REST client handles all synchronous operations:
- `get_markets()`: Fetch all available markets
- `get_market(market_id)`: Get specific market details
- `get_orderbook(market_id)`: Get orderbook for a market
- `place_order(order_params)`: Place a new order
- `cancel_order(order_id)`: Cancel an existing order
- `get_orders()`: Get list of orders
- `get_balances()`: Get account balances

### WebSocket Client
The WebSocket client provides real-time data:
- `subscribe_to_orderbook(market_ids)`: Subscribe to orderbook updates
- `unsubscribe_from_orderbook(market_ids)`: Unsubscribe from orderbook updates
- Event handlers for processing incoming data

## Rate Limiting

The bot implements a sliding window rate limiter to ensure compliance with Polymarket's API limits of 500 requests per 10 seconds.

## Connection Management

The ConnectionManager handles:
- Automatic reconnection on disconnection
- Heartbeat messages to maintain connection
- Error handling and logging