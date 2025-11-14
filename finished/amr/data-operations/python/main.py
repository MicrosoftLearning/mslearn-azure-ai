import os
import redis
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

try:
    # Azure Managed Redis with Non-Clustered policy uses standard Redis connection
    redis_host = os.getenv("REDIS_HOST")
    redis_key = os.getenv("REDIS_KEY")
    
    # Non-clustered policy uses standard Redis client connection
    conn = redis.Redis(
        host=redis_host,
        port=10000,  # Azure Managed Redis uses port 10000
        ssl=True,
        decode_responses=True,
        password=redis_key,
        socket_timeout=30,  # Add timeout for better reliability
        socket_connect_timeout=30,
    )

    # Test the connection
    print(f"Connecting to Redis (Non-Clustered) at {redis_host} on port 10000...")
    result = conn.ping()
    if result:
        print("Ping returned: " + str(result))
        print("Connected to Redis successfully!")
        
        # Test basic operations with non-clustered Redis
        test_key = "test_message"
        test_value = "Hello from Non-Clustered Redis!"
        conn.set(test_key, test_value)
        retrieved_value = conn.get(test_key)
        print(f"Set and retrieved test data: {retrieved_value}")
        
    else:
        print("Failed to ping Redis server")

except redis.ConnectionError as e:
    print(f"Connection error: {e}")
    print("Check if Redis host and port are correct, and ensure network connectivity")
except redis.AuthenticationError as e:
    print(f"Authentication error: {e}")
    print("Make sure you're logged in with 'az login' and added as a Redis user")
except redis.TimeoutError as e:
    print(f"Timeout error: {e}")
    print("Check network latency and Redis server performance")
except Exception as e:
    print(f"Unexpected error: {e}")
    if "999" in str(e):
        print("Error 999 typically indicates a network connectivity issue or firewall restriction")
finally:
    # Clean up connection if it exists
    if 'conn' in locals():
        try:
            conn.close()
            print("Redis connection closed")
        except Exception as e:
            print(f"Error closing connection: {e}")


