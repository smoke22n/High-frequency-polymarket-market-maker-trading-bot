"""
Simple test script to verify API client functionality
"""
import asyncio
import os
from dotenv import load_dotenv

from polymarket_mm_bot.api.client import PolymarketRestClient, Credentials
from polymarket_mm_bot.config.settings import load_config


async def test_rest_client():
    """Test the REST client functionality"""
    print("Testing REST client...")
    
    # Load environment variables
    load_dotenv()
    
    # Load config
    config = load_config()
    
    # Check if credentials are available
    if not config.api_key or not config.secret_key or not config.wallet_address:
        print("ERROR: Missing required environment variables:")
        print("- POLYMARKET_API_KEY")
        print("- POLYMARKET_SECRET_KEY") 
        print("- POLYMARKET_WALLET_ADDRESS")
        print("\nPlease set these environment variables before running the test.")
        return False
    
    credentials = Credentials(
        api_key=config.api_key,
        secret_key=config.secret_key,
        wallet_address=config.wallet_address
    )
    
    try:
        async with PolymarketRestClient(credentials, config.base_url) as client:
            print("✓ REST client initialized successfully")
            
            # Test getting markets
            print("Fetching markets...")
            markets = await client.get_markets()
            print(f"✓ Fetched {len(markets.get('data', []))} markets")
            
            # Test getting balances
            print("Fetching balances...")
            balances = await client.get_balances()
            print("✓ Balances fetched successfully")
            
            # Test getting orderbook for a market (using a sample market ID)
            # Note: In a real scenario, you'd use an actual market ID from the markets list
            if markets.get('data'):
                sample_market_id = markets['data'][0].get('market_id') if isinstance(markets['data'][0], dict) else markets['data'][0]
                if sample_market_id:
                    print(f"Fetching orderbook for market: {sample_market_id}")
                    orderbook = await client.get_orderbook(sample_market_id)
                    print("✓ Orderbook fetched successfully")
            
            print("\n✓ All REST client tests passed!")
            return True
            
    except Exception as e:
        print(f"✗ REST client test failed: {e}")
        return False


def test_rate_limiter():
    """Test the rate limiter functionality"""
    print("\nTesting rate limiter...")
    
    from polymarket_mm_bot.utils.rate_limiter import RateLimiter
    
    # Test initialization
    try:
        rate_limiter = RateLimiter(max_requests=5, time_window=1)  # 5 requests per 1 second
        print("✓ Rate limiter initialized successfully")
        
        # Test that it doesn't block immediately
        import asyncio
        
        async def test_requests():
            for i in range(3):  # Less than limit, shouldn't block
                await rate_limiter.wait_if_needed()
                print(f"✓ Request {i+1} passed through rate limiter")
        
        asyncio.run(test_requests())
        
        print("✓ Rate limiter test passed!")
        return True
    except Exception as e:
        print(f"✗ Rate limiter test failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("Starting Polymarket API Client Tests\n")
    
    rest_success = await test_rest_client()
    rate_limiter_success = test_rate_limiter()
    
    print(f"\nTest Summary:")
    print(f"- REST Client: {'✓ PASSED' if rest_success else '✗ FAILED'}")
    print(f"- Rate Limiter: {'✓ PASSED' if rate_limiter_success else '✗ FAILED'}")
    
    if rest_success and rate_limiter_success:
        print("\n✓ All tests passed! The API clients are working correctly.")
    else:
        print("\n✗ Some tests failed. Please check the error messages above.")


if __name__ == "__main__":
    asyncio.run(main())