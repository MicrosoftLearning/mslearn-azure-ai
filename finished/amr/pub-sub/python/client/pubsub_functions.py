"""
Pub/sub functions for Azure Managed Redis. These functions serve as the
interface between the Flask app and Azure Managed Redis, handling the
connection, publishing events, subscribing to channels, and listening for
incoming messages on a background thread.
"""
import json
import os
import threading
import time
from collections import deque
from datetime import datetime

import redis
from redis_entraid.cred_provider import create_from_default_azure_credential

# Channels used by the demo events in this exercise.
AVAILABLE_CHANNELS = [
    "orders:created",
    "orders:shipped",
    "inventory:alerts",
    "notifications",
]


# BEGIN CONNECTION CODE SECTION
def get_client() -> redis.Redis:
    """Create a Redis client for Azure Managed Redis using Microsoft Entra ID."""
    redis_host = os.environ.get("REDIS_HOST")

    if not redis_host:
        raise ValueError("REDIS_HOST environment variable must be set")

    # create_from_default_azure_credential uses DefaultAzureCredential to
    # acquire a Microsoft Entra token for Redis. The credential provider
    # refreshes the token automatically in the background so long-lived
    # connections (like the pub/sub listener) stay authenticated.
    credential_provider = create_from_default_azure_credential(
        ("https://redis.azure.com/.default",),
    )

    return redis.Redis(
        host=redis_host,
        port=10000,
        ssl=True,
        decode_responses=True,
        credential_provider=credential_provider,
        socket_timeout=30,
        socket_connect_timeout=30,
    )
# END CONNECTION CODE SECTION


# BEGIN PUBLISH MESSAGE CODE SECTION
def publish_order_created(r: redis.Redis) -> dict:
    """Publish an order created event to the 'orders:created' channel."""
    order_data = {
        "event": "order_created",
        "order_id": f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "customer": "Jane Doe",
        "total": 129.99,
        "timestamp": datetime.now().isoformat(),
    }
    channel = "orders:created"

    # publish() sends the message to every subscriber of the channel and
    # returns the number of subscribers that received it.
    subscribers = r.publish(channel, json.dumps(order_data))

    return {"channel": channel, "subscribers": subscribers, "message": order_data}
# END PUBLISH MESSAGE CODE SECTION


def publish_order_shipped(r: redis.Redis) -> dict:
    """Publish an order shipped event to notify all subscribers."""
    order_data = {
        "event": "order_shipped",
        "order_id": f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "tracking_number": f"TRK-{datetime.now().strftime('%H%M%S')}",
        "carrier": "FastShip",
        "timestamp": datetime.now().isoformat(),
    }
    channel = "orders:shipped"
    subscribers = r.publish(channel, json.dumps(order_data))
    return {"channel": channel, "subscribers": subscribers, "message": order_data}


def publish_inventory_alert(r: redis.Redis) -> dict:
    """Publish an inventory low alert with JSON-formatted event data."""
    alert_data = {
        "event": "inventory_low",
        "product_id": "PROD-12345",
        "product_name": "Wireless Headphones",
        "current_stock": 5,
        "threshold": 10,
        "timestamp": datetime.now().isoformat(),
    }
    channel = "inventory:alerts"
    subscribers = r.publish(channel, json.dumps(alert_data))
    return {"channel": channel, "subscribers": subscribers, "message": alert_data}


def publish_notification(r: redis.Redis) -> dict:
    """Publish a customer notification to demonstrate one-to-many messaging."""
    notification_data = {
        "event": "customer_notification",
        "notification_id": f"NOT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "customer_id": "CUST-789",
        "type": "promotional",
        "message": "Flash sale: 20% off on selected items!",
        "timestamp": datetime.now().isoformat(),
    }
    channel = "notifications"
    subscribers = r.publish(channel, json.dumps(notification_data))
    return {"channel": channel, "subscribers": subscribers, "message": notification_data}


# BEGIN BROADCAST CODE SECTION
def broadcast_to_all(r: redis.Redis) -> dict:
    """Broadcast the same message to every channel using publish() in a loop."""
    announcement = {
        "event": "system_announcement",
        "message": "System maintenance scheduled for 2 AM",
        "priority": "high",
        "timestamp": datetime.now().isoformat(),
    }
    message = json.dumps(announcement)

    results = []
    total_subscribers = 0
    for channel in AVAILABLE_CHANNELS:
        # Send the same message to multiple channels for multi-channel delivery.
        count = r.publish(channel, message)
        total_subscribers += count
        results.append({"channel": channel, "subscribers": count})

    return {
        "channels": results,
        "total_subscribers": total_subscribers,
        "message": announcement,
    }
# END BROADCAST CODE SECTION


# BEGIN MESSAGE FORMATTING CODE SECTION
def format_message(message: dict) -> dict:
    """Parse a pub/sub message and extract relevant fields for display."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    channel = message.get("channel", "unknown")
    pattern = message.get("pattern")

    try:
        data = json.loads(message["data"])
    except (json.JSONDecodeError, TypeError):
        # Non-JSON payloads are returned as-is under a "raw" key.
        return {
            "timestamp": timestamp,
            "channel": channel,
            "pattern": pattern,
            "event": None,
            "details": {"raw": message.get("data")},
        }

    # Pull out the fields that the demo events include so the UI can
    # display a clean summary of each message.
    field_names = [
        "order_id", "customer", "total", "tracking_number",
        "product_name", "current_stock", "message",
    ]
    details = {name: data[name] for name in field_names if name in data}

    return {
        "timestamp": timestamp,
        "channel": channel,
        "pattern": pattern,
        "event": data.get("event", "unknown"),
        "details": details,
    }
# END MESSAGE FORMATTING CODE SECTION


class PubSubManager:
    """Manages the Redis pub/sub connection, subscriptions, and listener thread."""

    def __init__(self):
        """Connect to Redis and prepare the pub/sub listener state."""
        self.r = get_client()
        self.r.ping()  # Fail fast if the connection or authentication is invalid.
        self.pubsub = self.r.pubsub(ignore_subscribe_messages=True)

        # Thread-safe, bounded buffer of received messages. Each entry is
        # tagged with a monotonically increasing index so the web page can
        # poll for only the messages it hasn't seen yet.
        self._messages = deque(maxlen=500)
        self._counter = 0
        self._lock = threading.Lock()

        self.listening = False
        self.listener_active = False
        self.listener_thread = None

    def _add_message(self, message: dict) -> None:
        """Append a formatted message to the buffer with a unique index."""
        with self._lock:
            self._counter += 1
            entry = {"index": self._counter}
            entry.update(message)
            self._messages.append(entry)

    def get_messages(self, since: int = 0):
        """Return messages newer than the given index and the latest index."""
        with self._lock:
            new_messages = [m for m in self._messages if m["index"] > since]
            return new_messages, self._counter

    def clear_messages(self) -> None:
        """Empty the received-message buffer and reset the index counter.

        Resetting the counter to zero signals the web page to clear its
        displayed history, so stale messages don't linger after the set of
        active subscriptions changes.
        """
        with self._lock:
            self._messages.clear()
            self._counter = 0

    # BEGIN MESSAGE LISTENER CODE SECTION
    def listen_messages(self) -> None:
        """Background thread that reads messages from subscribed channels."""
        self.listener_active = True
        try:
            # listen() blocks and yields messages as they are published.
            for message in self.pubsub.listen():
                if not self.listening:
                    break

                # Handle both direct channel messages and pattern messages.
                if message["type"] in ("message", "pmessage"):
                    self._add_message(format_message(message))

        except Exception as e:
            if self.listening:
                self._add_message({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "channel": "system",
                    "pattern": None,
                    "event": "listener_error",
                    "details": {"error": str(e)},
                })
        finally:
            self.listener_active = False
    # END MESSAGE LISTENER CODE SECTION

    def restart_listener(self, clear_subs: bool = False) -> None:
        """Restart the listener thread after a subscription change."""
        # Capture the current subscriptions so they can be restored on the new
        # connection. redis-py removes a channel from pubsub.channels only after
        # it reads the UNSUBSCRIBE confirmation off the socket. Because we tear
        # down and recreate the pubsub here, that confirmation is never read, so
        # a just-unsubscribed channel would still appear in pubsub.channels and
        # get resubscribed. Exclude anything that is pending unsubscribe.
        pending_channels = self.pubsub.pending_unsubscribe_channels
        pending_patterns = self.pubsub.pending_unsubscribe_patterns
        channels = [c for c in (self.pubsub.channels or {}) if c not in pending_channels]
        patterns = [p for p in (self.pubsub.patterns or {}) if p not in pending_patterns]

        if clear_subs:
            channels = []
            patterns = []

        # Stop the old listener and wait for it to finish.
        if self.listener_thread and self.listener_thread.is_alive():
            self.listening = False
            max_wait = 10
            while self.listener_active and max_wait > 0:
                time.sleep(0.1)
                max_wait -= 1

        try:
            self.pubsub.close()
        except Exception:
            pass

        time.sleep(0.1)

        # Create a fresh pubsub object and restore the subscriptions.
        self.pubsub = self.r.pubsub(ignore_subscribe_messages=True)
        if channels:
            self.pubsub.subscribe(*channels)
        if patterns:
            self.pubsub.psubscribe(*patterns)

        # Start a new listener thread.
        self.listening = True
        self.listener_thread = threading.Thread(target=self.listen_messages, daemon=True)
        self.listener_thread.start()

    # BEGIN SUBSCRIBE CHANNEL/PATTERN CODE SECTION
    def subscribe_to_channel(self, channel: str) -> str:
        """Subscribe to a specific channel using subscribe()."""
        self.pubsub.subscribe(channel)  # Register interest in the channel.
        self.restart_listener()
        return f"Subscribed to channel: {channel}"

    def subscribe_to_pattern(self, pattern: str) -> str:
        """Subscribe using a pattern with psubscribe() (e.g. 'orders:*')."""
        self.pubsub.psubscribe(pattern)  # Register interest in matching channels.
        self.restart_listener()
        return f"Subscribed to pattern: {pattern}"
    # END SUBSCRIBE CHANNEL/PATTERN CODE SECTION

    def unsubscribe_from_channel(self, channel: str) -> str:
        """Unsubscribe from a single channel."""
        self.pubsub.unsubscribe(channel)
        self.restart_listener()
        self.clear_messages()
        return f"Unsubscribed from channel: {channel}"

    def unsubscribe_all(self) -> str:
        """Unsubscribe from all channels and patterns."""
        self.pubsub.unsubscribe()
        self.pubsub.punsubscribe()
        self.restart_listener(clear_subs=True)
        self.clear_messages()
        return "Unsubscribed from all channels and patterns"

    def get_subscriptions(self) -> dict:
        """Return the currently active channel and pattern subscriptions."""
        channels = self.pubsub.channels
        patterns = self.pubsub.patterns
        return {
            "channels": list(channels.keys()) if channels else [],
            "patterns": list(patterns.keys()) if patterns else [],
            "listening": self.listening,
        }

    def close(self) -> None:
        """Stop the listener and close the Redis connections."""
        self.listening = False
        try:
            self.pubsub.close()
            self.r.close()
        except Exception:
            pass
