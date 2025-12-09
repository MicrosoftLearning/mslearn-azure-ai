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

def clear_screen():
    """Clear the terminal screen (works on both Windows and Linux)."""
    os.system('cls' if os.name == 'nt' else 'clear')

def pause_and_continue():
    """Pause and wait for user to press Enter before continuing."""
    input("\nPress Enter to continue...")
    clear_screen()

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
                # Extract and display the response text
                try:
                    # Handle OpenAI format response with choices
                    if "choices" in result and len(result["choices"]) > 0:
                        content = result["choices"][0].get("message", {}).get("content", "")
                        if content:
                            print(f"Response: {content}")
                        else:
                            print(f"Response: {json.dumps(result, indent=2)}")
                    else:
                        print(f"Response: {json.dumps(result, indent=2)}")
                except (KeyError, IndexError, TypeError):
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
                    has_content = False
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if line.startswith("data: "):
                            try:
                                json_str = line[6:]  # Remove "data: " prefix
                                data = json.loads(json_str)

                                if isinstance(data, dict):
                                    # Check for error
                                    if "error" in data:
                                        print(f"\n✗ Error: {data['error']}")
                                        return

                                    # Extract content from OpenAI format
                                    if "choices" in data and isinstance(data["choices"], list):
                                        for choice in data["choices"]:
                                            if isinstance(choice, dict) and "delta" in choice:
                                                delta = choice["delta"]
                                                if isinstance(delta, dict) and "content" in delta:
                                                    content = delta["content"]
                                                    if content:
                                                        print(content, end="", flush=True)
                                                        has_content = True
                            except json.JSONDecodeError as e:
                                # Skip malformed JSON lines (e.g., [DONE])
                                pass

                    if has_content:
                        print("\n")
                    else:
                        print("(no content received)")
                else:
                    print(f"✗ Streaming request failed: {response.status_code}")
                    print(f"  Error: {response.text}")
    except Exception as e:
        print(f"✗ Failed to send streaming request: {e}")

async def start_chat_session():
    """
    Start an interactive chat session with streaming responses.

    The session continues until the user types 'exit'.
    """
    print("\n[*] Starting chat session...")
    print("="*60)

    while True:
        prompt = input("\nYou (type 'exit' to end): ").strip()

        if prompt.lower() == "exit":
            print("\n[*] Ending chat session...")
            break

        if not prompt:
            print("Please enter a message.")
            continue

        try:
            payload = {
                "inputs": {"prompt": prompt},
                "parameters": {"temperature": 0.7, "max_tokens": 500}
            }

            async with initialize_client() as client:
                print("Assistant: ", end="", flush=True)
                async with client.stream("POST", "/v1/inference/stream", json=payload) as response:
                    if response.status_code == 200:
                        has_content = False
                        async for line in response.aiter_lines():
                            line = line.strip()
                            if line.startswith("data: "):
                                try:
                                    json_str = line[6:]  # Remove "data: " prefix
                                    data = json.loads(json_str)

                                    if isinstance(data, dict):
                                        # Check for error
                                        if "error" in data:
                                            print(f"\n✗ Error: {data['error']}")
                                            break

                                        # Extract content from OpenAI format
                                        if "choices" in data and isinstance(data["choices"], list):
                                            for choice in data["choices"]:
                                                if isinstance(choice, dict) and "delta" in choice:
                                                    delta = choice["delta"]
                                                    if isinstance(delta, dict) and "content" in delta:
                                                        content = delta["content"]
                                                        if content:
                                                            print(content, end="", flush=True)
                                                            has_content = True
                                except json.JSONDecodeError:
                                    # Skip malformed JSON lines (e.g., [DONE])
                                    pass

                        if has_content:
                            print("\n")
                    else:
                        print(f"\n✗ Request failed: {response.status_code}")
                        print(f"  Error: {response.text}")
        except Exception as e:
            print(f"\n✗ Chat error: {e}")

    pause_and_continue()

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
            pause_and_continue()

        elif choice == "2":
            print("\n[*] Checking API readiness...")
            await check_api_readiness()
            pause_and_continue()

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
            pause_and_continue()

        elif choice == "4":
            await start_chat_session()

        elif choice == "5":
            print("\nExiting...")
            sys.exit(0)

        else:
            print("Invalid option. Please select 1-5.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
