"""
Console application client for interacting with the AKS Configuration API.

This client provides a menu-driven interface for students to:
1. Check the health and readiness of the deployed API
2. View mock secrets loaded from Kubernetes Secrets
3. Retrieve a single product by ID
4. List all available products
5. View log summary from persistent storage
"""

import os
import sys
import httpx
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API endpoint from environment
API_ENDPOINT = os.getenv("API_ENDPOINT", "http://localhost:8000")
TIMEOUT = 30

def clear_screen():
    """Clear the terminal screen (works on both Windows and Linux)."""
    os.system('cls' if os.name == 'nt' else 'clear')

def pause_and_continue():
    """Pause and wait for user to press Enter before continuing."""
    input("\nPress Enter to continue...")
    clear_screen()

def initialize_client() -> httpx.Client:
    """
    Initialize an HTTP client for communicating with the API.

    Returns:
        httpx.Client: Configured HTTP client
    """
    return httpx.Client(
        base_url=API_ENDPOINT,
        timeout=httpx.Timeout(TIMEOUT),
        headers={"Content-Type": "application/json"}
    )

def check_api_health() -> bool:
    """
    Check if the API is alive (liveness probe).

    Returns:
        bool: True if API is healthy, False otherwise
    """
    try:
        with initialize_client() as client:
            response = client.get("/healthz")
            if response.status_code == 200:
                result = response.json()
                print("✓ API is healthy")
                print(f"  Service: {result.get('service', 'unknown')}")
                print(f"  Version: {result.get('version', 'unknown')}")
                print(f"  Student: {result.get('student', 'unknown')}")
                return True
            else:
                print(f"✗ API health check failed: {response.status_code}")
                return False
    except Exception as e:
        print(f"✗ Failed to connect to API: {e}")
        return False

def check_api_readiness() -> bool:
    """
    Check if the API is ready (readiness probe).

    Returns:
        bool: True if API is ready, False otherwise
    """
    try:
        with initialize_client() as client:
            response = client.get("/readyz")
            if response.status_code == 200:
                result = response.json()
                print("✓ API is ready")
                print("\nConfiguration:")
                config = result.get('configuration', {})
                for key, value in config.items():
                    print(f"  {key}: {value}")

                print(f"\nSecrets loaded: {result.get('secrets_loaded', False)}")
                print(f"Persistent storage ready: {result.get('persistent_storage_ready', False)}")
                print(f"Log path: {result.get('log_path', 'unknown')}")
                return True
            else:
                print(f"✗ API readiness check failed: {response.status_code}")
                print(f"  Error: {response.text}")
                return False
    except Exception as e:
        print(f"✗ Failed to connect to API: {e}")
        return False

def view_secrets():
    """
    View information about loaded secrets (values are masked for security).
    """
    try:
        with initialize_client() as client:
            response = client.get("/secrets")
            if response.status_code == 200:
                result = response.json()
                print("✓ Secrets information retrieved")
                print(f"\n{result.get('message', '')}")
                print(f"\nNote: {result.get('note', '')}")

                secrets = result.get('secrets', {})
                print("\nSecret Details:")
                for secret_name, secret_info in secrets.items():
                    print(f"\n  {secret_name}:")
                    print(f"    Loaded: {secret_info.get('loaded', False)}")
                    print(f"    Value: {secret_info.get('value', 'Not Set')}")
                    print(f"    Length: {secret_info.get('length', 0)} characters")
            else:
                print(f"✗ Failed to retrieve secrets: {response.status_code}")
                print(f"  Error: {response.text}")
    except Exception as e:
        print(f"✗ Failed to connect to API: {e}")

def get_single_product():
    """
    Retrieve information about a single product by ID.
    """
    try:
        product_id = input("\nEnter product ID (1-10): ").strip()

        if not product_id.isdigit():
            print("Invalid product ID. Please enter a number.")
            return

        product_id = int(product_id)

        with initialize_client() as client:
            response = client.get(f"/product/{product_id}")
            if response.status_code == 200:
                result = response.json()
                print(f"\n✓ Product retrieved (requested by {result.get('requested_by', 'unknown')})")

                product = result.get('product', {})
                print("\nProduct Information:")
                print(f"  ID: {product.get('id', 'N/A')}")
                print(f"  Name: {product.get('name', 'N/A')}")
                print(f"  Category: {product.get('category', 'N/A')}")
                print(f"  Price: ${product.get('price', 0):.2f}")
                print(f"  Stock: {product.get('stock', 0)} units")
                print(f"\nAPI Version: {result.get('api_version', 'unknown')}")
            elif response.status_code == 404:
                print(f"✗ Product not found: {response.json().get('detail', 'Unknown error')}")
            else:
                print(f"✗ Failed to retrieve product: {response.status_code}")
                print(f"  Error: {response.text}")
    except Exception as e:
        print(f"✗ Failed to connect to API: {e}")

def list_all_products():
    """
    List all available products.
    """
    try:
        with initialize_client() as client:
            response = client.get("/products")
            if response.status_code == 200:
                result = response.json()
                print(f"\n✓ Products retrieved (requested by {result.get('requested_by', 'unknown')})")
                print(f"\nTotal products: {result.get('total_products', 0)}")
                print(f"Categories: {', '.join(result.get('categories', []))}")

                products = result.get('products', [])
                print("\nProduct List:")
                print("-" * 80)
                print(f"{'ID':<5} {'Name':<25} {'Category':<20} {'Price':<10} {'Stock':<10}")
                print("-" * 80)

                for product in products:
                    print(f"{product.get('id', 0):<5} "
                          f"{product.get('name', 'N/A'):<25} "
                          f"{product.get('category', 'N/A'):<20} "
                          f"${product.get('price', 0):<9.2f} "
                          f"{product.get('stock', 0):<10}")

                print("-" * 80)
                print(f"\nAPI Version: {result.get('api_version', 'unknown')}")
            else:
                print(f"✗ Failed to retrieve products: {response.status_code}")
                print(f"  Error: {response.text}")
    except Exception as e:
        print(f"✗ Failed to connect to API: {e}")

def view_log_summary():
    """
    View summary of logged requests from persistent storage.
    """
    try:
        with initialize_client() as client:
            response = client.get("/logs/summary")
            if response.status_code == 200:
                result = response.json()

                if result.get('message'):
                    print(f"\n{result.get('message')}")
                    print(f"Log path: {result.get('log_path', 'unknown')}")
                else:
                    print("\n✓ Log summary retrieved")
                    print(f"\nLog file: {result.get('log_path', 'unknown')}")
                    print(f"Total requests: {result.get('total_requests', 0)}")
                    print(f"Student: {result.get('student', 'unknown')}")

                    first = result.get('first_request')
                    last = result.get('last_request')
                    if first:
                        print(f"\nFirst request: {first}")
                    if last:
                        print(f"Last request: {last}")

                    endpoint_counts = result.get('endpoint_counts', {})
                    if endpoint_counts:
                        print("\nRequests by endpoint:")
                        for endpoint, count in sorted(endpoint_counts.items(), key=lambda x: x[1], reverse=True):
                            print(f"  {endpoint}: {count}")
            else:
                print(f"✗ Failed to retrieve log summary: {response.status_code}")
                print(f"  Error: {response.text}")
    except Exception as e:
        print(f"✗ Failed to connect to API: {e}")

def display_menu():
    """Display the main menu to the user."""
    print("\n" + "="*70)
    print("  AKS Configuration API - Client Menu")
    print("="*70)
    print("API Endpoint: {}".format(API_ENDPOINT))
    print("="*70)
    print("1. Check API Health (Liveness)")
    print("2. Check API Readiness")
    print("3. View Secrets Information")
    print("4. Get Single Product")
    print("5. List All Products")
    print("6. View Log Summary")
    print("7. Exit")
    print("="*70)

def main():
    """Main client loop."""
    print("Initializing client...")
    print("API Endpoint: {}".format(API_ENDPOINT))

    clear_screen()

    while True:
        display_menu()
        choice = input("Select option (1-7): ").strip()

        if choice == "1":
            print("\n[*] Checking API health...")
            check_api_health()
            pause_and_continue()

        elif choice == "2":
            print("\n[*] Checking API readiness...")
            check_api_readiness()
            pause_and_continue()

        elif choice == "3":
            print("\n[*] Retrieving secrets information...")
            view_secrets()
            pause_and_continue()

        elif choice == "4":
            print("\n[*] Retrieving single product...")
            get_single_product()
            pause_and_continue()

        elif choice == "5":
            print("\n[*] Listing all products...")
            list_all_products()
            pause_and_continue()

        elif choice == "6":
            print("\n[*] Retrieving log summary...")
            view_log_summary()
            pause_and_continue()

        elif choice == "7":
            print("\nExiting...")
            sys.exit(0)

        else:
            print("Invalid option. Please select 1-7.")
            pause_and_continue()

if __name__ == "__main__":
    main()
