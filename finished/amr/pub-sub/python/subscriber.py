import os
import sys
import redis
import json
import threading
import time
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Global flag to control listener thread
listening = False
listener_thread = None

def clear_screen():
    """Clear console screen (cross-platform)"""
    os.system('cls' if os.name == 'nt' else 'clear')

clear_screen()

def connect_to_redis() -> redis.Redis:
    """Establish connection to Azure Managed Redis"""
    
    try:
        redis_host = os.getenv("REDIS_HOST")
        redis_key = os.getenv("REDIS_KEY")
        
        r = redis.Redis(
            host=redis_host,
            port=10000,
            ssl=True,
            decode_responses=True,
            password=redis_key,
            socket_timeout=30,
            socket_connect_timeout=30,
        )
        
        # Test connection
        r.ping()
        print(f"✓ Connected to Redis at {redis_host}")
        return r
        
    except redis.ConnectionError as e:
        print(f"✗ Connection error: {e}")
        print("Check if Redis host and port are correct, and ensure network connectivity")
        sys.exit(1)
    except redis.AuthenticationError as e:
        print(f"✗ Authentication error: {e}")
        print("Make sure the access key is correct")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        sys.exit(1)

def format_message(message_data: dict) -> str:
    """Format message data for display"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    channel = message_data.get('channel', 'unknown')
    
    try:
        data = json.loads(message_data['data'])
        event_type = data.get('event', 'unknown')
        
        formatted = f"\n[{timestamp}] 📨 Message received on '{channel}'"
        formatted += f"\n{'─' * 60}"
        formatted += f"\n  Event: {event_type}"
        
        # Display relevant fields based on event type
        if 'order_id' in data:
            formatted += f"\n  Order ID: {data['order_id']}"
        if 'customer' in data:
            formatted += f"\n  Customer: {data['customer']}"
        if 'total' in data:
            formatted += f"\n  Total: ${data['total']}"
        if 'tracking_number' in data:
            formatted += f"\n  Tracking: {data['tracking_number']}"
        if 'product_name' in data:
            formatted += f"\n  Product: {data['product_name']}"
        if 'current_stock' in data:
            formatted += f"\n  Stock Level: {data['current_stock']}"
        if 'message' in data:
            formatted += f"\n  Message: {data['message']}"
        
        formatted += f"\n{'─' * 60}\n"
        return formatted
        
    except json.JSONDecodeError:
        return f"\n[{timestamp}] 📨 {channel}: {message_data['data']}\n"

def message_listener(pubsub: redis.client.PubSub):
    """Background thread to listen for messages"""
    global listening
    
    print("\n🎧 Listener started. Waiting for messages...")
    print("   (Press Ctrl+C or select option 5 to stop listening)\n")
    
    try:
        for message in pubsub.listen():
            if not listening:
                break
                
            if message['type'] == 'message':
                print(format_message(message))
                
            elif message['type'] == 'pmessage':
                # Pattern-based subscription
                timestamp = datetime.now().strftime("%H:%M:%S")
                pattern = message['pattern']
                channel = message['channel']
                try:
                    data = json.loads(message['data'])
                    event_type = data.get('event', 'unknown')
                    print(f"\n[{timestamp}] 📨 Pattern '{pattern}' matched channel '{channel}'")
                    print(f"{'─' * 60}")
                    print(f"  Event: {event_type}")
                    print(f"  Full message: {json.dumps(data, indent=2)}")
                    print(f"{'─' * 60}\n")
                except json.JSONDecodeError:
                    print(f"\n[{timestamp}] 📨 Pattern '{pattern}': {message['data']}\n")
                    
    except Exception as e:
        if listening:
            print(f"\n✗ Listener error: {e}")

def subscribe_to_channel(r: redis.Redis, pubsub: redis.client.PubSub) -> None:
    """Subscribe to a specific channel"""
    global listening, listener_thread
    
    clear_screen()
    print("=" * 60)
    print("Subscribe to Channel")
    print("=" * 60)
    
    print("\n📋 Available channels:")
    print("  • orders:created")
    print("  • orders:shipped")
    print("  • inventory:alerts")
    print("  • notifications")
    
    channel = input("\nEnter channel name (or custom): ").strip()
    
    if not channel:
        print("\n✗ Channel name cannot be empty")
        input("\nPress Enter to continue...")
        return
    
    try:
        pubsub.subscribe(channel)
        print(f"\n✓ Subscribed to channel: '{channel}'")
        
        if not listening:
            listening = True
            listener_thread = threading.Thread(target=message_listener, args=(pubsub,), daemon=True)
            listener_thread.start()
        
        input("\nPress Enter to continue...")
        
    except Exception as e:
        print(f"\n✗ Error subscribing: {e}")
        input("\nPress Enter to continue...")

def subscribe_with_pattern(r: redis.Redis, pubsub: redis.client.PubSub) -> None:
    """Subscribe using a pattern"""
    global listening, listener_thread
    
    clear_screen()
    print("=" * 60)
    print("Subscribe with Pattern")
    print("=" * 60)
    
    print("\n📋 Pattern examples:")
    print("  • orders:*       (matches orders:created, orders:shipped, etc.)")
    print("  • inventory:*    (matches all inventory channels)")
    print("  • *              (matches all channels)")
    
    pattern = input("\nEnter pattern: ").strip()
    
    if not pattern:
        print("\n✗ Pattern cannot be empty")
        input("\nPress Enter to continue...")
        return
    
    try:
        pubsub.psubscribe(pattern)
        print(f"\n✓ Subscribed to pattern: '{pattern}'")
        
        if not listening:
            listening = True
            listener_thread = threading.Thread(target=message_listener, args=(pubsub,), daemon=True)
            listener_thread.start()
        
        input("\nPress Enter to continue...")
        
    except Exception as e:
        print(f"\n✗ Error subscribing: {e}")
        input("\nPress Enter to continue...")

def unsubscribe_from_channel(pubsub: redis.client.PubSub) -> None:
    """Unsubscribe from a channel"""
    clear_screen()
    print("=" * 60)
    print("Unsubscribe from Channel")
    print("=" * 60)
    
    channel = input("\nEnter channel name to unsubscribe: ").strip()
    
    if not channel:
        print("\n✗ Channel name cannot be empty")
        input("\nPress Enter to continue...")
        return
    
    try:
        pubsub.unsubscribe(channel)
        print(f"\n✓ Unsubscribed from channel: '{channel}'")
        input("\nPress Enter to continue...")
        
    except Exception as e:
        print(f"\n✗ Error unsubscribing: {e}")
        input("\nPress Enter to continue...")

def view_active_subscriptions(pubsub: redis.client.PubSub) -> None:
    """View current active subscriptions"""
    clear_screen()
    print("=" * 60)
    print("Active Subscriptions")
    print("=" * 60)
    
    channels = pubsub.channels
    patterns = pubsub.patterns
    
    if channels:
        print("\n📌 Subscribed channels:")
        for channel in channels:
            print(f"  • {channel.decode() if isinstance(channel, bytes) else channel}")
    else:
        print("\n  No channel subscriptions")
    
    if patterns:
        print("\n📌 Subscribed patterns:")
        for pattern in patterns:
            print(f"  • {pattern.decode() if isinstance(pattern, bytes) else pattern}")
    else:
        print("\n  No pattern subscriptions")
    
    print(f"\n🎧 Listener status: {'Active' if listening else 'Stopped'}")
    
    input("\nPress Enter to continue...")

def stop_listening() -> None:
    """Stop the message listener"""
    global listening, listener_thread
    
    clear_screen()
    print("=" * 60)
    print("Stop Listening")
    print("=" * 60)
    
    if listening:
        listening = False
        if listener_thread:
            print("\n🛑 Stopping listener...")
            listener_thread.join(timeout=2)
        print("✓ Listener stopped")
    else:
        print("\n⚠️  Listener is not currently running")
    
    input("\nPress Enter to continue...")

def show_menu():
    """Display the subscriber menu"""
    clear_screen()
    print("=" * 60)
    print("         Redis Pub/Sub - MESSAGE SUBSCRIBER")
    print("=" * 60)
    print("\n🎧 Subscription Options:\n")
    print("  1. Subscribe to Channel")
    print("  2. Subscribe with Pattern")
    print("  3. Unsubscribe from Channel")
    print("  4. View Active Subscriptions")
    print("  5. Stop Listening")
    print("  6. Exit")
    print("=" * 60)
    
    if listening:
        print("\n🟢 Listener: ACTIVE")
    else:
        print("\n🔴 Listener: STOPPED")

def main() -> None:
    """Main application loop"""
    global listening
    
    print("\n🔄 Initializing Redis Subscriber...\n")
    r = connect_to_redis()
    pubsub = r.pubsub()
    
    print("\n💡 TIP: Subscribe to channels, then run publisher.py in another terminal!")
    input("\nPress Enter to continue...")
    
    try:
        while True:
            show_menu()
            choice = input("\nSelect an option (1-6): ").strip()
            
            if choice == "1":
                subscribe_to_channel(r, pubsub)
            elif choice == "2":
                subscribe_with_pattern(r, pubsub)
            elif choice == "3":
                unsubscribe_from_channel(pubsub)
            elif choice == "4":
                view_active_subscriptions(pubsub)
            elif choice == "5":
                stop_listening()
            elif choice == "6":
                clear_screen()
                print("\n👋 Exiting subscriber...")
                listening = False
                break
            else:
                print("\n✗ Invalid option. Please select 1-6.")
                input("\nPress Enter to continue...")
        
    except KeyboardInterrupt:
        clear_screen()
        print("\n\n👋 Subscriber interrupted by user")
        listening = False
    finally:
        try:
            listening = False
            pubsub.close()
            r.close()
            print("✓ Redis connection closed\n")
        except Exception as e:
            print(f"✗ Error closing connection: {e}\n")

if __name__ == "__main__":
    main()
