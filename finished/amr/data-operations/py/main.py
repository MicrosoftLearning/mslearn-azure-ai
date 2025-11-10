import os
import redis
from dotnenv import load_dotenv

try:
    # Create credential provider using the official Microsoft syntax
    #credential_provider = create_from_default_azure_credential("https://redis.azure.com/.default")


    conn = redis.Redis(
        host=os.getenv("REDIS_HOST"),
        port=6380,
        ssl=True,
        decode_responses=True,
        password=os.getenv("REDIS_KEY"),
        #credential_provider=credential_provider,
        socket_timeout=10,
        socket_connect_timeout=10
    )

    # Test connection
    result = conn.set('user:1001:name', 'Alice Smith')
    print(f"SET operation successful: {result}")  # Returns True

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


