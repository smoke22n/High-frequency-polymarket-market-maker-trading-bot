"""
Rate Limiter Implementation
Implements a token bucket algorithm to comply with Polymarket's rate limits
"""
import asyncio
import time
from collections import deque
from typing import Optional


class RateLimiter:
    """
    Rate limiter that enforces request limits to comply with API rate limits
    Uses a sliding window approach to track requests within a time window
    """
    
    def __init__(self, max_requests: int = 500, time_window: int = 10):
        """
        Initialize rate limiter
        :param max_requests: Maximum number of requests allowed in the time window
        :param time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
        self.lock = asyncio.Lock()
        
    async def wait_if_needed(self):
        """
        Check if we need to wait before making a request due to rate limiting
        """
        async with self.lock:
            current_time = time.time()
            
            # Remove requests that are outside the time window
            while self.requests and (current_time - self.requests[0]) > self.time_window:
                self.requests.popleft()
            
            # If we've hit the limit, wait until we can make another request
            if len(self.requests) >= self.max_requests:
                oldest_request_time = self.requests[0]
                sleep_time = self.time_window - (current_time - oldest_request_time) + 0.1  # Small buffer
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
            
            # Add current request timestamp
            self.requests.append(current_time)


class TokenBucketRateLimiter:
    """
    Alternative implementation using token bucket algorithm
    """
    
    def __init__(self, rate: float, capacity: int):
        """
        Initialize token bucket rate limiter
        :param rate: Tokens added per second (request rate)
        :param capacity: Maximum number of tokens in the bucket
        """
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.time()
        self.lock = asyncio.Lock()
        
    async def wait_if_needed(self):
        """
        Wait until a token is available (rate limiting)
        """
        async with self.lock:
            current_time = time.time()
            
            # Calculate how many tokens to add based on elapsed time
            tokens_to_add = (current_time - self.last_refill) * self.rate
            self.tokens = min(self.capacity, self.tokens + tokens_to_add)
            self.last_refill = current_time
            
            # If no tokens available, calculate wait time
            if self.tokens < 1:
                sleep_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(sleep_time)
                
                # Update tokens after sleeping
                current_time = time.time()
                tokens_to_add = (current_time - self.last_refill) * self.rate
                self.tokens = min(self.capacity, self.tokens + tokens_to_add)
                self.last_refill = current_time
            
            # Consume a token
            self.tokens -= 1