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
    return httpx.AsyncClient(
        base_url=API_ENDPOINT,
        timeout=httpx.Timeout(TIMEOUT),
        headers={"Content-Type": "application/json"}
    )

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
    try:
        async with initialize_client() as client:
            response = await client.get("/healthz")
            if response.status_code == 200:
                print("✓ API is healthy")
                print(f"  Response: {response.json()}")
                return True
            else:
                print(f"✗ API health check failed: {response.status_code}")
                return False
    except Exception as e:
        print(f"✗ Failed to connect to API: {e}")
        return False

async def check_api_readiness() -> bool:
    """
    Check if the API is ready and Foundry connectivity is established (readiness probe).

    Returns:
        bool: True if API is ready, False otherwise
    """
    try:
        async with initialize_client() as client:
            response = await client.get("/readyz")
            if response.status_code == 200:
                print("✓ API is ready and Foundry is connected")
                print(f"  Response: {response.json()}")
                return True
            else:
                print(f"✗ API readiness check failed: {response.status_code}")
                return False
    except Exception as e:
        print(f"✗ Failed to connect to API: {e}")
        return False

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
    try:
        payload = {
            "inputs": {"prompt": prompt},
            "parameters": {"temperature": 0.7}
        }

        async with initialize_client() as client:
            response = await client.post("/v1/inference", json=payload)

            if response.status_code == 200:
                result = response.json()
                print("\n✓ Inference successful")
                print(f"Response: {json.dumps(result, indent=2)}")
                return result
            else:
                print(f"✗ Inference request failed: {response.status_code}")
                print(f"  Error: {response.text}")
                raise Exception(f"API error: {response.status_code}")
    except Exception as e:
        print(f"✗ Failed to send inference request: {e}")
        raise

async def send_streaming_inference_request(prompt: str):
    """
    Send a streaming inference request to the API and print tokens as they arrive.

    Args:
        prompt: The user's prompt/question

    Raises:
        Exception: If the streaming request fails
    """
    try:
        payload = {
            "inputs": {"prompt": prompt},
            "parameters": {"temperature": 0.7, "max_tokens": 500}
        }

        async with initialize_client() as client:
            print("\n[Streaming response]:")
            async with client.stream("POST", "/v1/inference/stream", json=payload) as response:
                if response.status_code == 200:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if "choices" in data:
                                    delta = data.get("choices", [{}])[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        print(content, end="", flush=True)
                            except json.JSONDecodeError:
                                pass
                    print("\n")
                else:
                    print(f"✗ Streaming request failed: {response.status_code}")
                    print(f"  Error: {response.text}")
    except Exception as e:
        print(f"✗ Failed to send streaming request: {e}")

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
            print("\n[*] Checking API health...")
            await check_api_health()

        elif choice == "2":
            print("\n[*] Checking API readiness...")
            await check_api_readiness()

        elif choice == "3":
            print("\n[*] Sending inference request...")
            prompt = input("Enter your prompt: ").strip()
            if prompt:
                try:
                    await send_inference_request(prompt)
                except Exception:
                    pass
            else:
                print("Prompt cannot be empty.")

        elif choice == "4":
            print("\n[*] Starting chat session (streaming)...")
            prompt = input("Enter your prompt: ").strip()
            if prompt:
                await send_streaming_inference_request(prompt)
            else:
                print("Prompt cannot be empty.")

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
