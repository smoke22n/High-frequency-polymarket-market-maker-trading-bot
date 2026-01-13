"""
Connection Manager for WebSocket connections
Handles heartbeats and auto-reconnects on disconnection
"""
import asyncio
import logging
from typing import Optional
from .client import PolymarketWsClient, Credentials


class ConnectionManager:
    """
    Manages WebSocket connection with heartbeat and auto-reconnect capabilities
    """
    
    def __init__(self, credentials: Credentials, ws_url: str = "wss://clob.polymarket.com/ws"):
        self.credentials = credentials
        self.ws_url = ws_url
        self.ws_client: Optional[PolymarketWsClient] = None
        self.is_running = False
        self.heartbeat_interval = 30  # seconds
        self.reconnect_delay = 5  # seconds
        self.max_reconnect_attempts = 10
        self.current_reconnect_attempt = 0
        
        self.logger = logging.getLogger(__name__)
        
    async def start(self):
        """Start the connection manager"""
        self.is_running = True
        await self._connect_with_retry()
        
        # Start heartbeat task
        asyncio.create_task(self._heartbeat_loop())
        
    async def stop(self):
        """Stop the connection manager"""
        self.is_running = False
        if self.ws_client:
            await self.ws_client.disconnect()
    
    async def _connect_with_retry(self):
        """Attempt to connect with retry logic"""
        while self.is_running and self.current_reconnect_attempt < self.max_reconnect_attempts:
            try:
                self.logger.info(f"Attempting to connect (attempt {self.current_reconnect_attempt + 1})")
                
                # Create new client instance
                self.ws_client = PolymarketWsClient(self.credentials, self.ws_url)
                
                # Connect to WebSocket
                await self.ws_client.connect()
                
                # Reset reconnect attempts on successful connection
                self.current_reconnect_attempt = 0
                
                self.logger.info("Connected successfully")
                break
                
            except Exception as e:
                self.logger.error(f"Connection failed: {e}")
                self.current_reconnect_attempt += 1
                
                if self.current_reconnect_attempt >= self.max_reconnect_attempts:
                    self.logger.error("Max reconnect attempts reached")
                    raise Exception("Could not establish connection after max attempts")
                
                # Wait before retrying
                await asyncio.sleep(self.reconnect_delay)
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeat messages to maintain connection"""
        while self.is_running:
            try:
                if self.ws_client and self.ws_client.is_connected:
                    # Send heartbeat/ping message
                    heartbeat_msg = {"type": "PING"}
                    await self.ws_client.websocket.send(str(heartbeat_msg))
                    
                    self.logger.debug("Heartbeat sent")
                else:
                    self.logger.warning("WebSocket not connected, attempting to reconnect...")
                    await self._connect_with_retry()
                    
            except Exception as e:
                self.logger.error(f"Heartbeat failed: {e}")
                # Attempt to reconnect if heartbeat fails
                await self._connect_with_retry()
            
            # Wait for next heartbeat
            await asyncio.sleep(self.heartbeat_interval)
    
    async def subscribe_to_orderbook(self, market_ids: list):
        """Subscribe to orderbook updates for specific markets"""
        if not self.ws_client or not self.ws_client.is_connected:
            self.logger.warning("Not connected, attempting to reconnect...")
            await self._connect_with_retry()
        
        await self.ws_client.subscribe_to_orderbook(market_ids)
    
    async def unsubscribe_from_orderbook(self, market_ids: list):
        """Unsubscribe from orderbook updates for specific markets"""
        if self.ws_client and self.ws_client.is_connected:
            await self.ws_client.unsubscribe_from_orderbook(market_ids)
    
    def register_handler(self, event_type: str, handler):
        """Register a handler for specific event types"""
        if self.ws_client:
            self.ws_client.register_handler(event_type, handler)