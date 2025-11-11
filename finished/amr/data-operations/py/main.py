import os
import redis
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

try:
 
    conn = redis.Redis(
        host=os.getenv("REDIS_HOST"),
        port=6380,
        ssl=True,
        decode_responses=True,
        password=os.getenv("REDIS_KEY"),
        socket_timeout=30.0,  # Float value for timeout
        socket_connect_timeout=30.0,  # Float value for connection timeout
        socket_keepalive=True,  # Enable TCP keepalive
        max_connections=10,  # Connection pool size
        health_check_interval=30,  # Health check every 30 seconds
        retry_on_error=[redis.ConnectionError, redis.TimeoutError]  # Valid parameter
    )

    # Test the connection
    result = conn.ping()
    if result:
        print("Ping returned: " + str(result))
        print("Connected to Redis successfully!")
        
        # Optional: Test basic Redis operations
        conn.set("test", "Hello from Python!")
        value = conn.get("test")
        print(f"Test operation - SET/GET: {value}")
        
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


