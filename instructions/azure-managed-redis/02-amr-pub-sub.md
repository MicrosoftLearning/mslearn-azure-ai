---
lab:
  topic: Azure Managed Redis
  title: Publish and subscribe to events in Azure Managed Redis
  description: Learn how to build a Flask web app that implements pub/sub messaging patterns in Azure Managed Redis using the redis-py Python library and Microsoft Entra ID.
  level: 300
  duration: 30
  islab: true
  primarytopics:
    - Azure
    - Azure Managed Redis
---

# Publish and subscribe to events in Azure Managed Redis

In this exercise, you deploy an Azure Managed Redis resource and complete a Python Flask web app that publishes and subscribes to Redis channels from a single page. You add code to connect to Redis with Microsoft Entra ID, publish event messages, broadcast to every channel, format received messages, listen for messages on a background thread, and subscribe to channels and patterns. You then run the app and watch messages arrive live as you publish them.

Tasks performed in this exercise:

- Download the project starter files
- Create an Azure Managed Redis resource
- Add code to the starter files to complete the app
- Run the app to publish and subscribe to messages

This exercise takes approximately **30** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).
- The Azure CLI **redisenterprise** extension, version 2.75.0 or greater. A later step installs or upgrades the extension for you.

## Download project starter files and deploy Azure Managed Redis

In this section you download the starter files for the app and use a script to initialize the deployment of Azure Managed Redis to your subscription. The Azure Managed Redis deployment takes 5-10 minutes to complete, so you start the deployment first and add code to the app while it provisions.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/amr-pub-sub-python.zip
    ```

1. Copy, or move, the file to a location in your system where you want to work on the project. Then unzip the file into a folder.

1. Launch Visual Studio Code (VS Code) and select **File > Open Folder...** in the menu, then choose the folder containing the project files.

1. The project contains deployment scripts for both Bash (*azdeploy.sh*) and PowerShell (*azdeploy.ps1*). Open the appropriate file for your environment and change the two values at the top of the script to meet your needs, then save your changes. **Note:** Do not change anything else in the script.

    ```
    "<your-resource-group-name>" # Resource Group name
    "<your-azure-region>" # Azure region for the resources
    ```

1. In the menu bar select **Terminal > New Terminal** to open a terminal window in VS Code.

1. Run the following command to login to your Azure account. Answer the prompts to select your Azure account and subscription for the exercise.

    ```
    az login
    ```

1. Run the following command to ensure your subscription has the necessary resource provider for Azure Managed Redis.

    ```
    az provider register --namespace Microsoft.Cache
    ```

1. Run the following command to install or upgrade the **redisenterprise** extension for Azure CLI. Version 2.75.0 or greater is required to configure Microsoft Entra ID access on the database.

    ```
    az extension add --upgrade --name redisenterprise
    ```

1. Run the appropriate command in the terminal to launch the script.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

    > **Note:** If PowerShell blocks the script because it is not digitally signed, run the following command in the same terminal session, then run the deployment script again. This command changes the execution policy only for the current PowerShell process.

    ```powershell
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    ```

1. When the script is running, enter **1** to launch the **1. Create Azure Managed Redis resource** option.

    This option creates the resource group if it doesn't already exist, then deploys Azure Managed Redis. The script waits for the deployment to finish, which takes 5-10 minutes, and reports the result in the terminal. Leave the script running and continue to the next section to add code while the deployment provisions. Check back on the terminal periodically to watch for errors.

    When the deployment succeeds, a confirmation message like the following appears and the menu returns:

    *Azure Managed Redis resource created successfully: amr-exercise-\<hash>*

    > **Note:** If the deployment fails, it's most often due to a temporary lack of capacity for the SKU in your chosen region. Follow the on-screen guidance to exit the script, change the **location** variable near the top of the script to a different region such as eastus2, australiaeast, or canadacentral, then run the script again and choose option 1. The failed resource is deleted automatically before the next attempt.

## Complete the app

In this section you add code to the *pubsub_functions.py* file to complete the pub/sub functions. The Flask app in *app.py* calls these functions to publish messages, manage subscriptions, and stream received messages to the browser. You don't need to edit *app.py*. You run the app later in the exercise.

1. Open the *client/pubsub_functions.py* file to begin adding code.

>**Note:** The code blocks you add to the application should align with the comment for that section of the code.

### Add code to connect to Azure Managed Redis

In this section you add code to create a Redis client that authenticates with Microsoft Entra ID. Using Entra ID means the app never handles an access key.

The **get_client()** function reads the Redis endpoint from the **REDIS_HOST** environment variable and calls **create_from_default_azure_credential()** to build a credential provider. The provider uses **DefaultAzureCredential** to acquire a Microsoft Entra token and refreshes it automatically in the background, so the long-lived listener connection stays authenticated. The client connects over TLS on port 10000 and decodes responses to strings.

1. Locate the **# BEGIN CONNECTION CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
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
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to publish an event

In this section you add code to publish an order created event. This demonstrates the core publish operation that sends a message to a single channel.

The **publish_order_created()** function builds a dictionary describing the event, serializes it to JSON, and calls **publish()** on the **orders:created** channel. The **publish()** method returns the number of subscribers that received the message, which the app displays so you can confirm the message was delivered.

1. Locate the **# BEGIN PUBLISH MESSAGE CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
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
    ```

    > **Note:** The starter file already includes the **publish_order_shipped()**, **publish_inventory_alert()**, and **publish_notification()** functions so you have several event types to work with. Take a moment to review them.

1. Save your changes and take a few minutes to review the code.

### Add code to broadcast to all channels

In this section you add code to broadcast a single message to every channel. Broadcasting is useful for system-wide announcements that all subscribers should receive regardless of the channel they subscribed to.

The **broadcast_to_all()** function loops over **AVAILABLE_CHANNELS** and calls **publish()** for each one with the same message. It totals the subscriber counts across all channels so the app can report how many subscribers were reached.

1. Locate the **# BEGIN BROADCAST CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
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
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to format received messages

In this section you add code to format incoming messages for display. The background listener calls this function for every message it receives so the web page can show a clean summary.

The **format_message()** function reads the channel, pattern, and data from the raw pub/sub message. It parses the JSON payload and extracts the event type along with a set of known fields such as **order_id** and **customer**. If the payload isn't valid JSON, it returns the raw value instead so nothing is lost.

1. Locate the **# BEGIN MESSAGE FORMATTING CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
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
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to listen for messages

In this section you add code to the **listen_messages()** method of the **PubSubManager** class. This method runs on a background thread so the app can receive messages continuously while still responding to web requests.

The method iterates over **pubsub.listen()**, which blocks and yields messages as they're published. It handles both **message** (direct channel) and **pmessage** (pattern) types, formats each one with **format_message()**, and adds it to a thread-safe buffer that the web page polls. Errors are captured and surfaced as a system message so failures are visible in the UI.

1. Locate the **# BEGIN MESSAGE LISTENER CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
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
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to subscribe to channels and patterns

In this section you add code to the **subscribe_to_channel()** and **subscribe_to_pattern()** methods. These are the two main subscription strategies in Redis pub/sub: direct channel subscriptions for a specific event and pattern subscriptions for wildcard matching.

The **subscribe_to_channel()** method calls **subscribe()** to register interest in a single channel, while **subscribe_to_pattern()** calls **psubscribe()** to match multiple channels with a pattern such as **orders:***. After each subscription change, the code restarts the listener so it begins receiving messages on the new channels.

1. Locate the **# BEGIN SUBSCRIBE CHANNEL/PATTERN CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
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
    ```

1. Save your changes and take a few minutes to review the code.

## Verify resource deployment

In this section you return to the running deployment script to confirm the Azure Managed Redis deployment finished, then create the database, configure Microsoft Entra ID access, and generate the *.env* file with the endpoint.

1. Return to the terminal where the deployment script is running. After a successful deployment, you see the confirmation message and the menu. If you exited the script, run the appropriate command to start it again.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

1. Enter **2** to run the **2. Create database and configure access** option. This creates the database with Microsoft Entra ID authentication, assigns a data access policy to your account so the app can connect using your identity, and creates the *.env* file with the **REDIS_HOST** endpoint.

1. (Optional) Enter **3** to run the **3. Check deployment status** option as a last-minute check.

1. Enter **4** to exit the deployment script.

1. Run the appropriate command to load the environment variables into your terminal session from the file created in the previous step.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

    >**Note:** Keep the terminal open. If you close it and create a new terminal, you need to run this command again to reload the environment variables.

## Configure the Python environment

In this section, you navigate to the client app directory, create the Python environment, and install the dependencies.

1. Run the following command in the VS Code terminal to navigate to the *client* directory.

    ```
    cd client
    ```

1. Run the following command to create the Python environment.

    ```
    python -m venv .venv
    ```

1. Run the following command to activate the Python environment. **Note:** On Linux/macOS, use the Bash command. On Windows, use the PowerShell command. If using Git Bash on Windows, use **source .venv/Scripts/activate**.

    **Bash**
    ```bash
    source .venv/bin/activate
    ```

    **PowerShell**
    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

1. Run the following command in the VS Code terminal to install the dependencies.

    ```
    pip install -r requirements.txt
    ```

## Run the app

In this section, you run the completed Flask application to publish and subscribe to messages from a single web page. The left panel publishes events and manages subscriptions, and the right panel shows the result of the last publish and a live stream of received messages.

1. Run the following command in the terminal to start the app. Refer to the commands from earlier in the exercise to activate the environment and load the environment variables, if needed, before running the command. If you navigated away from the *client* directory, run **cd client** first.

    ```
    python app.py
    ```

1. Open a browser and navigate to `http://localhost:5000` to access the app.

1. In the **Subscriptions** area of the left panel, select the channel box to open the drop-down list, choose **notifications**, and select **Subscribe**. A success message confirms the subscription, and the **Active subscriptions** list updates to include the channel. You must subscribe to a channel before you can receive its messages.

1. In the **Publish Events** area, select **Notification**. The right panel shows the publish result, including the channel and the number of subscribers reached. Within a second or two, the message appears in the **Received Messages** list because the background listener delivered it to your subscription.

1. Select **Inventory Alert**. The publish result shows the message was sent to the **inventory:alerts** channel, but it does not appear in **Received Messages** because you only subscribed to **notifications**.

1. In the **Subscriptions** area, enter **orders:\*** in the pattern box and select **Subscribe to Pattern**. This subscribes to every channel that begins with **orders:**, and the pattern appears in the **Active subscriptions** list alongside **notifications**.

1. Select **Order Created**, then select **Order Shipped**. Both messages appear in the **Received Messages** list because the **orders:*** pattern matches both the **orders:created** and **orders:shipped** channels.

1. Select **Broadcast to All** to send a single announcement to every channel. Watch the **Received Messages** list update live for each message that matches your current subscriptions.

1. Select **Unsubscribe from All** to clear your subscriptions, then select **Broadcast to All** again. Confirm that no new messages arrive in **Received Messages** because you no longer have any active subscriptions.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues while completing this exercise, try the following troubleshooting steps:

**Verify Azure Managed Redis resource deployment**
- Navigate to the [Azure portal](https://portal.azure.com) and locate your resource group.
- Confirm that the Azure Managed Redis resource shows a **Provisioning State** of **Succeeded**.
- Run the deployment script's **Check deployment status** option and confirm the cluster and database are ready before creating the database and configuring access.

**Check authentication and access**
- Confirm you are logged in to Azure CLI by running **az account show**.
- Ensure the deployment script's **Create database and configure access** option completed successfully so your account has a data access policy on the database.
- If the app reports an authentication error, wait a moment and try again, as the access policy assignment can take a short time to take effect.

**Check code completeness and indentation**
- Ensure all code blocks were added to the correct sections in *pubsub_functions.py* between the appropriate BEGIN/END comment markers.
- Verify that Python indentation is consistent (use spaces, not tabs). The **listen_messages()**, **subscribe_to_channel()**, and **subscribe_to_pattern()** methods are inside the **PubSubManager** class, so their code must be indented one level.
- Confirm that no code was accidentally removed or modified outside the designated sections.

**Verify environment variables**
- Check that the *.env* file exists in the project root and contains the **REDIS_HOST** value.
- Ensure you ran **source .env** (Bash) or **. .\.env.ps1** (PowerShell) to load environment variables into your terminal session.
- If variables are empty, re-run **source .env** (Bash) or **. .\.env.ps1** (PowerShell).

**No messages appearing?**
- Confirm you subscribed to the channel you're publishing to. Messages only arrive on channels or patterns you're subscribed to.
- Check the **Active Subscriptions** list in the browser to verify your current subscriptions.
- Confirm the app is still running in the terminal and the page shows the message stream updating.

**Check Python environment and dependencies**
- Confirm the virtual environment is activated before running the app.
- Verify that all packages from *requirements.txt* were installed successfully by running **pip list**.
