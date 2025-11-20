import os
import sys
import redis
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def clear_screen():
    """Clear console screen (cross-platform)"""
    os.system('cls' if os.name == 'nt' else 'clear')

def connect_to_redis() -> redis.Redis:
    """Establish connection to Azure Managed Redis"""
    clear_screen()

    # BEGIN CONNECTION CODE SECTION


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



# END STORE AND RETRIEVE CODE SECTION

# BEGIN EXPIRATION CODE SECTION


# END EXPIRATION CODE SECTION

# BEGIN DELETE CODE SECTION


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
    clear_screen()
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