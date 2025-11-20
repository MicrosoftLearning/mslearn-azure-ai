# Redis Pub/Sub Demo - Azure Managed Redis

This demo demonstrates publish/subscribe messaging patterns using Azure Managed Redis with Python.

## Overview

This application uses a **dual-terminal approach** to showcase real-time messaging:
- **Terminal 1**: Runs the **subscriber** to listen for messages
- **Terminal 2**: Runs the **publisher** to send messages

## What You'll Learn

- Subscribe to specific Redis channels
- Use pattern-based subscriptions (e.g., `orders:*`)
- Publish messages to channels
- Broadcast messages to multiple channels
- View active subscriber counts
- Handle real-time message delivery

## Prerequisites

- Azure Managed Redis resource deployed
- Python 3.12 or greater
- `.env` file with Redis connection details:
  ```
  REDIS_HOST=your-redis-host.redis.azure.net
  REDIS_KEY=your-access-key
  ```

## Setup

1. Create and activate a Python virtual environment:

   **Bash:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

   **PowerShell:**
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Demo

### Step 1: Start the Subscriber (Terminal 1)

```bash
python subscriber.py
```

**Menu Options:**
1. **Subscribe to Channel** - Listen to a specific channel (e.g., `orders:created`)
2. **Subscribe with Pattern** - Use wildcards (e.g., `orders:*` to catch all order events)
3. **Unsubscribe from Channel** - Stop listening to a channel
4. **View Active Subscriptions** - See what you're subscribed to
5. **Stop Listening** - Pause the message listener
6. **Exit** - Close the subscriber

**Recommended first steps:**
- Select option `1` and subscribe to `orders:created`
- Or select option `2` and subscribe to pattern `orders:*`

The subscriber will start listening and display messages in real-time.

### Step 2: Start the Publisher (Terminal 2)

Open a **new terminal window** and activate the virtual environment, then:

```bash
python publisher.py
```

**Menu Options:**
1. **Publish Order Created event** - Send a sample order creation message
2. **Publish Order Shipped event** - Send a shipping notification
3. **Publish Inventory Alert** - Send a low stock alert
4. **Publish Customer Notification** - Send a promotional message
5. **Broadcast to All Channels** - Send a system announcement to multiple channels
6. **Publish Custom Message** - Send your own message to any channel
7. **Exit** - Close the publisher

**Try this:**
- Select option `1` to publish an order created event
- Watch Terminal 1 (subscriber) receive the message in real-time!

## Example Channels

The demo includes these pre-configured channels:

- `orders:created` - New order notifications
- `orders:shipped` - Shipping updates
- `inventory:alerts` - Stock level warnings
- `notifications` - Customer notifications

## Key Concepts Demonstrated

### Channel Subscriptions
```python
pubsub.subscribe('orders:created')
```
Subscribe to a specific channel to receive only those messages.

### Pattern Subscriptions
```python
pubsub.psubscribe('orders:*')
```
Use wildcards to subscribe to multiple related channels at once.

### Publishing Messages
```python
r.publish('orders:created', message)
```
Send a message to a channel. Returns the number of active subscribers.

### Message Listening
```python
for message in pubsub.listen():
    if message['type'] == 'message':
        # Handle the message
```
Continuously listen for incoming messages on subscribed channels.

## Tips

- **Multiple Subscribers**: You can run multiple subscriber instances to see how messages are delivered to all subscribers
- **Pattern Matching**: Patterns like `*` subscribe to ALL channels - useful for debugging
- **Subscriber Count**: The publisher shows how many subscribers received each message
- **Threading**: The subscriber uses a background thread so you can interact with the menu while listening

## Troubleshooting

**No messages appearing?**
- Ensure the subscriber is listening (check status at bottom of menu)
- Verify you've subscribed to the correct channel
- Confirm the publisher is sending to the same channel name

**Connection errors?**
- Check your `.env` file has correct `REDIS_HOST` and `REDIS_KEY`
- Verify Azure Managed Redis resource is running
- Ensure public network access is enabled on your Redis resource

**Listener won't stop?**
- Press Ctrl+C to interrupt
- Select option `5` from the subscriber menu

## Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Publisher     │         │  Azure Managed   │         │   Subscriber    │
│  (Terminal 2)   │────────>│      Redis       │────────>│  (Terminal 1)   │
│                 │         │   (Channels)     │         │                 │
└─────────────────┘         └──────────────────┘         └─────────────────┘
     Publishes                 Distributes                   Receives
     messages                  to subscribers                messages
```

## Next Steps

- Experiment with custom channels and messages
- Try running multiple subscriber instances
- Implement your own event types
- Integrate pub/sub into a larger application architecture
