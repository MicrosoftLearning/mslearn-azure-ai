import os
import sys
import redis
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def clear_screen():
    """Clear console screen (cross-platform)"""
    os.system('cls' if os.name == 'nt' else 'clear')

clear_screen()

def connect_to_redis():
    """Establish connection to Azure Managed Redis"""
    clear_screen()

    # BEGIN CONNECTION CODE SECTION

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

        print(f"Connected to Redis at {redis_host}")
        input("\nPress Enter to continue...")
        return r

    # END CONNECTION CODE SECTION

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

# BEGIN STORE AND RETRIEVE CODE SECTION

def store_hash_data(r, key, value) -> None:
    """Store a hash data in Redis"""
    clear_screen()
    print(f"Storing hash data for key: {key}")
    result = r.hset(key, mapping=value) # Store hash data
    if result > 0: # New fields were added
        print(f"Data stored successfully under key '{key}' ({result} new fields added)")
    else:
        print(f"Data updated successfully under key '{key}' (all fields already existed)")
    input("\nPress Enter to continue...")

def retrieve_hash_data(r, key) -> None:
    """Retrieve hash data from Redis"""
    clear_screen()
    print(f"Retrieving hash data for key: {key}")
    retrieved_value = r.hgetall(key) # Retrieve hash data
    if retrieved_value:
        print("\nRetrieved hash data:")
        for field, value in retrieved_value.items():
            print(f"  {field}: {value}")
    else:
        print(f"Key '{key}' does not exist.")

    input("\nPress Enter to continue...")

# END STORE AND RETRIEVE CODE SECTION

# BEGIN EXPIRATION CODE SECTION

def set_expiration(r, key) -> None:
    """Set an expiration time for a key"""
    clear_screen()
    print("Set expiration time for a key")
    # Set expiration time, 1 hour equals 3600 seconds
    expiration = int(input("Enter expiration time in seconds (default 3600): ") or 3600)
    result = r.expire(key, expiration) # Set expiration time
    if result:
        print(f"Expiration time of {expiration} seconds set for key '{key}'")
    else:
        print(f"Key '{key}' does not exist. Expiration not set.")

    input("\nPress Enter to continue...")

def retrieve_expiration(r, key) -> None:
    """Retrieve TTL of a key"""
    clear_screen()
    print(f"Retrieving the current TTL of {key}...")
    ttl = r.ttl(key) # Get current TTL
    if ttl == -2: # Key does not exist
        print(f"\nKey '{key}' does not exist.")
    elif ttl == -1: # No expiration set
        print(f"\nKey '{key}' has no expiration set (persists indefinitely).")
    else:
        print(f"\nCurrent TTL for '{key}': {ttl} seconds")
    input("\nPress Enter to continue...")

# END EXPIRATION CODE SECTION

# BEGIN DELETE CODE SECTION

def delete_key(r, key) -> None:
    """Delete a key"""
    clear_screen()
    print(f"Deleting key: {key}...")
    result = r.delete(key) # Delete the key
    if result == 1:
        print(f"Key '{key}' deleted successfully.")
    else:
        print(f"Key '{key}' does not exist.")
    input("\nPress Enter to continue...")

# END DELETE CODE SECTION

def show_menu():
    """Display the main menu"""
    clear_screen()
    print("=" * 50)
    print("    Redis Data Operations Menu")
    print("=" * 50)
    print("1. Store hash data")
    print("2. Retrieve hash data")
    print("3. Set expiration")
    print("4. Retrieve expiration (TTL)")
    print("5. Delete key")
    print("6. Exit")
    print("=" * 50)

def main() -> None:
    r = connect_to_redis() # Connect to Redis

    # Sample key and value for hash data, can be modified as needed
    key="user:1001"
    value={"name": "Jane", "age": "28", "email": "jane@example.com"}
    
    try:
        while True:
            show_menu()
            choice = input("\nPlease select an option (1-6): ")
            
            if choice == "1":
                store_hash_data(r, key, value)
            elif choice == "2":
                retrieve_hash_data(r, key)
            elif choice == "3":
                set_expiration(r, key)
            elif choice == "4":
                retrieve_expiration(r, key)
            elif choice == "5":
                delete_key(r, key)
            elif choice == "6":
                clear_screen()
                print("Exiting...")
                break
            else:
                print("\nInvalid option. Please select 1-6.")
                input("\nPress Enter to continue...")
        
    finally:
        # Clean up connection
        try:
            r.close()
            print("Redis connection closed")
        except Exception as e:
            print(f"Error closing connection: {e}")

if __name__ == "__main__":
    main()