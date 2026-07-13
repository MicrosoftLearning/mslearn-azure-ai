# Publish and subscribe with Azure Managed Redis

This is the completed Flask app for the Azure Managed Redis publish/subscribe exercise. A single web page lets you publish event messages to Redis channels and subscribe to channels or patterns, with received messages displayed live.

## How it works

The app runs a background listener thread that reads messages from the channels and patterns you subscribe to. The web page polls the `/messages` endpoint about once per second and appends any new messages to the **Received Messages** panel, so publishing and subscribing happen together on one page.

- **Publish Events** — send sample order, inventory, and notification events, or broadcast to every channel.
- **Subscriptions** — subscribe to a specific channel (for example, `orders:created`) or a pattern (for example, `orders:*`), then unsubscribe as needed.
- **Activity** — shows the result of the last publish and the live stream of received messages.

## Channels

- `orders:created` — new order notifications
- `orders:shipped` — shipping updates
- `inventory:alerts` — stock level warnings
- `notifications` — customer notifications

## Authentication

The app authenticates to Azure Managed Redis with Microsoft Entra ID using `DefaultAzureCredential`. The `redis-entraid` credential provider acquires an access token and refreshes it in the background, so the long-lived listener connection stays authenticated. Only the Redis endpoint is read from the environment (`REDIS_HOST`); no access key is used.

## Run the app

1. Deploy the resource and create the environment file by running the *azdeploy.sh* (Bash) or *azdeploy.ps1* (PowerShell) script, then load the endpoint into your session:

   **Bash**
   ```bash
   source .env
   ```

   **PowerShell**
   ```powershell
   . .\.env.ps1
   ```

2. Create the Python environment and install the dependencies:

   ```bash
   cd client
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Start the app and open http://localhost:5000 in a browser:

   ```bash
   flask run
   ```
