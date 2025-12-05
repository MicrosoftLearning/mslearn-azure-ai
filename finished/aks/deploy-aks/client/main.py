"""
Console application client for interacting with the AKS Foundry Gateway API.

This client provides a menu-driven interface for students to:
1. Check the health and readiness of the deployed API
2. Verify connectivity to the Foundry model
3. Send inference requests to the API
4. Start an interactive chat session with the model
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

# ============================================================================
# BEGIN CLIENT INITIALIZATION CODE SECTION
# Students should implement API client initialization here
# ============================================================================

def initialize_client() -> httpx.AsyncClient:
    """
    Initialize an async HTTP client for communicating with the API.

    Returns:
        httpx.AsyncClient: Configured HTTP client
    """
    # TODO: Implement client initialization
    # Create an AsyncClient with appropriate timeout and headers
    pass

# ============================================================================
# END CLIENT INITIALIZATION CODE SECTION
# ============================================================================

# ============================================================================
# BEGIN HEALTH CHECK CODE SECTION
# Students should implement health check functions here
# ============================================================================

async def check_api_health() -> bool:
    """
    Check if the API is alive (liveness probe).

    Returns:
        bool: True if API is healthy, False otherwise
    """
    # TODO: Implement health check
    # Call GET /healthz endpoint
    # Return True if status is 200, False otherwise
    pass

async def check_api_readiness() -> bool:
    """
    Check if the API is ready and Foundry connectivity is established (readiness probe).

    Returns:
        bool: True if API is ready, False otherwise
    """
    # TODO: Implement readiness check
    # Call GET /readyz endpoint
    # Return True if status is 200 and Foundry is connected, False otherwise
    pass

# ============================================================================
# END HEALTH CHECK CODE SECTION
# ============================================================================

# ============================================================================
# BEGIN INFERENCE CODE SECTION
# Students should implement inference functions here
# ============================================================================

async def send_inference_request(prompt: str) -> dict:
    """
    Send a synchronous inference request to the API.

    Args:
        prompt: The user's prompt/question

    Returns:
        dict: The model's response

    Raises:
        Exception: If the inference request fails
    """
    # TODO: Implement inference request
    # Build request body with prompt
    # Call POST /v1/inference endpoint
    # Return parsed JSON response
    pass

async def send_streaming_inference_request(prompt: str):
    """
    Send a streaming inference request to the API and print tokens as they arrive.

    Args:
        prompt: The user's prompt/question

    Raises:
        Exception: If the streaming request fails
    """
    # TODO: Implement streaming inference
    # Build request body with prompt
    # Call POST /v1/inference/stream endpoint
    # Stream and print tokens as they arrive
    pass

# ============================================================================
# END INFERENCE CODE SECTION
# ============================================================================

# ============================================================================
# BEGIN MENU CODE SECTION
# Students should implement the menu system here
# ============================================================================

def display_menu():
    """Display the main menu to the user."""
    print("\n" + "="*60)
    print("  AKS Foundry Gateway API - Client Menu")
    print("="*60)
    print("API Endpoint: {}".format(API_ENDPOINT))
    print("="*60)
    print("1. Check API Health (Liveness)")
    print("2. Check API Readiness (Foundry Connectivity)")
    print("3. Send Inference Request")
    print("4. Start Chat Session (Streaming)")
    print("5. Exit")
    print("="*60)

async def main():
    """Main client loop."""
    print("Initializing client...")
    print("API Endpoint: {}".format(API_ENDPOINT))

    while True:
        display_menu()
        choice = input("Select option (1-5): ").strip()

        if choice == "1":
            # TODO: Implement health check menu option
            print("\n[*] Checking API health...")
            pass

        elif choice == "2":
            # TODO: Implement readiness check menu option
            print("\n[*] Checking API readiness...")
            pass

        elif choice == "3":
            # TODO: Implement inference request menu option
            print("\n[*] Sending inference request...")
            pass

        elif choice == "4":
            # TODO: Implement chat session menu option
            print("\n[*] Starting chat session...")
            pass

        elif choice == "5":
            print("\nExiting...")
            sys.exit(0)

        else:
            print("Invalid option. Please select 1-5.")

# ============================================================================
# END MENU CODE SECTION
# ============================================================================

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
