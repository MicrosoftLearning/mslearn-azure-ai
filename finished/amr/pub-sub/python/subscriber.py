import os
import redis
import json
import threading
import time
from datetime import datetime
from queue import Queue
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

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
        raise
    except redis.AuthenticationError as e:
        print(f"[x] Authentication error: {e}")
        print("Make sure the access key is correct")
        raise
    except Exception as e:
        print(f"[x] Unexpected error: {e}")
        raise

def format_message_gui(message_data: dict) -> str:
    """Format message data for GUI display"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    channel = message_data.get('channel', 'unknown')
    
    try:
        data = json.loads(message_data['data'])
        event_type = data.get('event', 'unknown')
        
        formatted = f"[{timestamp}] Message on '{channel}'\n"
        formatted += f"{'─' * 50}\n"
        formatted += f"Event: {event_type}\n"
        
        # Display relevant fields based on event type
        if 'order_id' in data:
            formatted += f"Order ID: {data['order_id']}\n"
        if 'customer' in data:
            formatted += f"Customer: {data['customer']}\n"
        if 'total' in data:
            formatted += f"Total: ${data['total']}\n"
        if 'tracking_number' in data:
            formatted += f"Tracking: {data['tracking_number']}\n"
        if 'product_name' in data:
            formatted += f"Product: {data['product_name']}\n"
        if 'current_stock' in data:
            formatted += f"Stock Level: {data['current_stock']}\n"
        if 'message' in data:
            formatted += f"Message: {data['message']}\n"
        
        formatted += f"{'─' * 50}\n"
        return formatted
        
    except json.JSONDecodeError:
        return f"[{timestamp}] {channel}: {message_data['data']}\n"

class PubSubManager:
    """Manages Redis pub/sub operations and message listening"""
    
    def __init__(self):
        """Initialize the pub/sub manager"""
        self.r = connect_to_redis()
        self.pubsub = self.r.pubsub(ignore_subscribe_messages=True)
        self.message_queue = Queue()
        self.listening = False
        self.listener_active = False
        self.listener_thread = None
    
    def listen_messages(self):
        """Background thread to listen for messages"""
        self.listener_active = True
        
        try:
            for message in self.pubsub.listen():
                if not self.listening:
                    break
                    
                if message['type'] == 'message':
                    formatted = format_message_gui(message)
                    self.message_queue.put(formatted)
                    
                elif message['type'] == 'pmessage':
                    # Pattern-based subscription
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    pattern = message['pattern']
                    channel = message['channel']
                    try:
                        data = json.loads(message['data'])
                        event_type = data.get('event', 'unknown')
                        msg = f"[{timestamp}] Pattern '{pattern}' matched '{channel}'\n"
                        msg += f"{'-' * 50}\n"
                        msg += f"Event: {event_type}\n"
                        msg += f"Full message: {json.dumps(data, indent=2)}\n"
                        msg += f"{'-' * 50}\n"
                        self.message_queue.put(msg)
                    except json.JSONDecodeError:
                        self.message_queue.put(f"[{timestamp}] Pattern '{pattern}': {message['data']}\n")
                        
        except Exception as e:
            if self.listening:
                self.message_queue.put(f"[x] Listener error: {e}\n")
        finally:
            self.listener_active = False
    
    def restart_listener(self, clear_subs=False):
        """Restart the listener thread after subscription changes"""
        
        # Save current subscriptions before closing
        channels = list(self.pubsub.channels.keys()) if self.pubsub.channels else []
        patterns = list(self.pubsub.patterns.keys()) if self.pubsub.patterns else []
        
        # If clear_subs is True, don't restore subscriptions
        if clear_subs:
            channels = []
            patterns = []
        
        # Stop the old listener if it's running
        if self.listener_thread and self.listener_thread.is_alive():
            self.listening = False
            # Wait for listener to fully stop
            max_wait = 10
            while self.listener_active and max_wait > 0:
                time.sleep(0.1)
                max_wait -= 1
        
        # Close old pubsub
        try:
            self.pubsub.close()
        except:
            pass
        
        time.sleep(0.1)
        
        # Create new pubsub
        self.pubsub = self.r.pubsub(ignore_subscribe_messages=True)
        
        # Restore subscriptions
        if channels:
            self.pubsub.subscribe(*channels)
        if patterns:
            self.pubsub.psubscribe(*patterns)
        
        # Start fresh listener
        self.listening = True
        self.listener_thread = threading.Thread(target=self.listen_messages, daemon=True)
        self.listener_thread.start()
    
    def subscribe_to_channel(self, channel: str) -> str:
        """Subscribe to a specific channel"""
        try:
            self.pubsub.subscribe(channel)
            self.restart_listener()
            return f"[+] Subscribed to channel: '{channel}'"
        except Exception as e:
            return f"[x] Error subscribing: {e}"
    
    def subscribe_to_pattern(self, pattern: str) -> str:
        """Subscribe using a pattern"""
        try:
            self.pubsub.psubscribe(pattern)
            self.restart_listener()
            return f"[+] Subscribed to pattern: '{pattern}'"
        except Exception as e:
            return f"[x] Error subscribing: {e}"
    
    def unsubscribe_from_channel(self, channel: str) -> str:
        """Unsubscribe from a channel"""
        try:
            self.pubsub.unsubscribe(channel)
            self.restart_listener()
            return f"[+] Unsubscribed from channel: '{channel}'"
        except Exception as e:
            return f"[x] Error unsubscribing: {e}"
    
    def unsubscribe_all(self) -> str:
        """Unsubscribe from all channels and patterns"""
        try:
            channels = list(self.pubsub.channels.keys()) if self.pubsub.channels else []
            patterns = list(self.pubsub.patterns.keys()) if self.pubsub.patterns else []
            
            unsubscribed_channels = 0
            unsubscribed_patterns = 0
            
            if channels:
                for channel in channels:
                    self.pubsub.unsubscribe(channel)
                    unsubscribed_channels += 1
            
            if patterns:
                for pattern in patterns:
                    self.pubsub.punsubscribe(pattern)
                    unsubscribed_patterns += 1
            
            self.restart_listener(clear_subs=True)
            return f"[+] Unsubscribed from {unsubscribed_channels} channel(s) and {unsubscribed_patterns} pattern(s)"
        except Exception as e:
            return f"[x] Error unsubscribing: {e}"
    
    def get_subscriptions(self) -> dict:
        """Get current active subscriptions"""
        channels = self.pubsub.channels
        patterns = self.pubsub.patterns
        
        return {
            'channels': list(channels.keys()) if channels else [],
            'patterns': list(patterns.keys()) if patterns else [],
            'listening': self.listening
        }
    
    def get_message(self, timeout=0.1):
        """Get next message from queue (non-blocking)"""
        try:
            return self.message_queue.get(timeout=timeout)
        except:
            return None
    
    def close(self):
        """Close connections and stop listener"""
        self.listening = False
        try:
            self.pubsub.close()
            self.r.close()
        except:
            pass

if __name__ == "__main__":
    from subscriber_gui import run_gui
    run_gui()
