import os
import sys
import redis
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def clear_screen():
    """Clear console screen (cross-platform)"""
    os.system('cls' if os.name == 'nt' else 'clear')

# BEGIN CONNECTION CODE SECTION

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
        return r
        
    except redis.ConnectionError as e:
        print(f"[x] Connection error: {e}")
        print("Check if Redis host and port are correct, and ensure network connectivity")
        sys.exit(1)
    except redis.AuthenticationError as e:
        print(f"[x] Authentication error: {e}")
        print("Make sure the access key is correct")
        sys.exit(1)
    except Exception as e:
        print(f"[x] Unexpected error: {e}")
        sys.exit(1)

# END CONNECTION CODE SECTION

# BEGIN PUBLISH MESSAGE CODE SECTION

def publish_order_created(r: redis.Redis) -> None:
    """Publish an order created event"""
    clear_screen()
    print("=" * 60)
    print("Publishing: Order Created Event")
    print("=" * 60)
    
    order_data = {
        "event": "order_created",
        "order_id": f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "customer": "Jane Doe",
        "total": 129.99,
        "timestamp": datetime.now().isoformat()
    }
    
    message = json.dumps(order_data)
    channel = "orders:created"
    
    # Publish message and get subscriber count
    subscribers = r.publish(channel, message)
    
    print(f"\n[>] Published to channel: '{channel}'")
    print(f"[#] Active subscribers: {subscribers}")
    print(f"\n[i] Message content:")
    print(json.dumps(order_data, indent=2))
    
    input("\n[+] Press Enter to continue...")

# END PUBLISH MESSAGE CODE SECTION

def publish_order_shipped(r: redis.Redis) -> None:
    """Publish an order shipped event"""
    clear_screen()
    print("=" * 60)
    print("Publishing: Order Shipped Event")
    print("=" * 60)
    
    order_data = {
        "event": "order_shipped",
        "order_id": f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "tracking_number": f"TRK-{datetime.now().strftime('%H%M%S')}",
        "carrier": "FastShip",
        "timestamp": datetime.now().isoformat()
    }
    
    message = json.dumps(order_data)
    channel = "orders:shipped"
    
    subscribers = r.publish(channel, message)
    
    print(f"\n[>] Published to channel: '{channel}'")
    print(f"[#] Active subscribers: {subscribers}")
    print(f"\n[i] Message content:")
    print(json.dumps(order_data, indent=2))
    
    input("\n[+] Press Enter to continue...")

def publish_inventory_alert(r: redis.Redis) -> None:
    """Publish an inventory low alert"""
    clear_screen()
    print("=" * 60)
    print("Publishing: Inventory Alert")
    print("=" * 60)
    
    alert_data = {
        "event": "inventory_low",
        "product_id": "PROD-12345",
        "product_name": "Wireless Headphones",
        "current_stock": 5,
        "threshold": 10,
        "timestamp": datetime.now().isoformat()
    }
    
    message = json.dumps(alert_data)
    channel = "inventory:alerts"
    
    subscribers = r.publish(channel, message)
    
    print(f"\n[>] Published to channel: '{channel}'")
    print(f"[#] Active subscribers: {subscribers}")
    print(f"\n[i] Message content:")
    print(json.dumps(alert_data, indent=2))
    
    input("\n[+] Press Enter to continue...")

def publish_notification(r: redis.Redis) -> None:
    """Publish a customer notification"""
    clear_screen()
    print("=" * 60)
    print("Publishing: Customer Notification")
    print("=" * 60)
    
    notification_data = {
        "event": "customer_notification",
        "notification_id": f"NOT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "customer_id": "CUST-789",
        "type": "promotional",
        "message": "Flash sale: 20% off on selected items!",
        "timestamp": datetime.now().isoformat()
    }
    
    message = json.dumps(notification_data)
    channel = "notifications"
    
    subscribers = r.publish(channel, message)
    
    print(f"\n[>] Published to channel: '{channel}'")
    print(f"[#] Active subscribers: {subscribers}")
    print(f"\n[i] Message content:")
    print(json.dumps(notification_data, indent=2))
    
    input("\n[+] Press Enter to continue...")

# BEGIN BROADCAST CODE SECTION

def broadcast_to_all(r: redis.Redis) -> None:
    """Broadcast a message to all channels"""
    clear_screen()
    print("=" * 60)
    print("Broadcasting: System Announcement")
    print("=" * 60)
    
    announcement = {
        "event": "system_announcement",
        "message": "System maintenance scheduled for 2 AM",
        "priority": "high",
        "timestamp": datetime.now().isoformat()
    }
    
    channels = ["orders:created", "orders:shipped", "inventory:alerts", "notifications"]
    message = json.dumps(announcement)
    
    print(f"\n[>] Broadcasting to {len(channels)} channels...")
    print(f"Channels: {', '.join(channels)}\n")
    
    total_subscribers = 0
    for channel in channels:
        count = r.publish(channel, message)
        total_subscribers += count
        print(f"  - {channel}: {count} subscriber(s)")
    
    print(f"\n[#] Total subscribers reached: {total_subscribers}")
    print(f"\n[i] Message content:")
    print(json.dumps(announcement, indent=2))
    
    input("\n[+] Press Enter to continue...")

# END BROADCAST CODE SECTION

def show_menu():
    """Display the publisher menu"""
    clear_screen()
    print("=" * 60)
    print("         Redis Pub/Sub - MESSAGE PUBLISHER")
    print("=" * 60)
    print("\n[>] Publish Messages:\n")
    print("  1. Publish Order Created event")
    print("  2. Publish Order Shipped event")
    print("  3. Publish Inventory Alert")
    print("  4. Publish Customer Notification")
    print("  5. Broadcast to All Channels")
    print("  6. Exit")
    print("=" * 60)

def main() -> None:
    """Main application loop"""
    clear_screen()
    print("\n[*] Initializing Redis Publisher...\n")
    r = connect_to_redis()
    
    clear_screen()
    print("[+] Connected to Redis")
    print("\n[i] TIP: Start the subscriber.py in another terminal to see messages!")
    input("\nPress Enter to continue...")
    
    try:
        while True:
            show_menu()
            choice = input("\nSelect an option (1-6): ").strip()
            
            if choice == "1":
                publish_order_created(r)
            elif choice == "2":
                publish_order_shipped(r)
            elif choice == "3":
                publish_inventory_alert(r)
            elif choice == "4":
                publish_notification(r)
            elif choice == "5":
                broadcast_to_all(r)
            elif choice == "6":
                clear_screen()
                print("\n[*] Exiting publisher...")
                break
            else:
                print("\n[x] Invalid option. Please select 1-6.")
                input("\nPress Enter to continue...")
        
    except KeyboardInterrupt:
        clear_screen()
        print("\n\n[*] Publisher interrupted by user")
    finally:
        try:
            r.close()
            print("[+] Redis connection closed\n")
        except Exception as e:
            print(f"[x] Error closing connection: {e}\n")

if __name__ == "__main__":
    main()
