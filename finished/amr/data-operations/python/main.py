import os
import sys
import redis
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def connect_to_redis():
    """Establish connection to Azure Managed Redis"""
    try:
        # Azure Managed Redis with Non-Clustered policy uses standard Redis connection
        redis_host = os.getenv("REDIS_HOST")
        redis_key = os.getenv("REDIS_KEY")
        
        # Non-clustered policy uses standard Redis client connection
        r = redis.Redis(
            host=redis_host,
            port=10000,  # Azure Managed Redis uses port 10000
            ssl=True,
            decode_responses=True, # Decode responses to strings
            password=redis_key,
            socket_timeout=30,  # Add timeout for better reliability
            socket_connect_timeout=30,
        )

        # Test the connection
        print(f"Connecting to Redis (Non-Clustered) at {redis_host} on port 10000...")
        result = r.ping()
        if result:
            print("Ping returned: " + str(result))
            print("Connected to Redis successfully!")
            return r
        else:
            print("Failed to ping Redis server")
            print("Ensure that the Redis server is running and accessible")
            sys.exit(1)

    except redis.ConnectionError as e:
        print(f"Connection error: {e}")
        print("Check if Redis host and port are correct, and ensure network connectivity")
        sys.exit(1)
    except redis.AuthenticationError as e:
        print(f"Authentication error: {e}")
        print("Make sure the access key is correct")
        sys.exit(1)
    except redis.TimeoutError as e:
        print(f"Timeout error: {e}")
        print("Check network latency and Redis server performance")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        if "999" in str(e):
            print("Error 999 typically indicates a network connectivity issue or firewall restriction")
        sys.exit(1)

def main() -> None:
    r = connect_to_redis()
    
    try:
        # Test basic operations with non-clustered Redis
        test_key = "test_message"
        test_value = "Hello from Non-Clustered Redis!"
        r.set(test_key, test_value)
        retrieved_value = r.get(test_key)
        print(f"Set and retrieved test data: {retrieved_value}")
        
        # Add your data operation functions here
        
    finally:
        # Clean up connection
        try:
            r.close()
            print("Redis connection closed")
        except Exception as e:
            print(f"Error closing connection: {e}")

if __name__ == "__main__":
    main()