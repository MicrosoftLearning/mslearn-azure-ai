---
lab:
    topic: Integrate backend services
    title: 'Publish and receive events with Azure Event Grid'
    description: 'Learn how to publish, receive, and route content moderation events using Azure Event Grid Namespaces with pull delivery and filtered subscriptions.'
    level: 200
    duration: 30
---

{% include under-construction.md %}

# Publish and receive events with Azure Event Grid

AI content moderation systems generate a high volume of events as they classify and review submissions. Azure Event Grid provides the routing layer that directs these events to the right downstream consumers based on event type, so each handler receives only the events it needs without polling or manual filtering.

In this exercise, you deploy an Event Grid Namespace with a namespace topic and filtered event subscriptions, then build a Python Flask application that publishes content moderation events and receives them using pull delivery. Event Grid subscriptions route flagged content, approved content, and all events to separate subscriptions so you can observe how filtering works in practice. You also use the receive, acknowledge, and reject operations that pull delivery provides to control how your application processes events.

Tasks performed in this exercise:

- Download the project starter files
- Deploy an Event Grid Namespace with a namespace topic
- Create event subscriptions with type filters
- Add code to the starter files to complete the app
- Run the app to publish, receive, and process moderation events

This exercise takes approximately **30** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli?view=azure-cli-latest).

## Download project starter files and deploy resources

In this section you download the starter files for the app and use a script to deploy an Event Grid Namespace to your subscription. The namespace contains a topic where your application publishes moderation events and event subscriptions that filter and hold events for pull delivery.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/event-grid-python.zip
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

1. Run the following command to ensure your subscription has the necessary resource provider for the exercise.

    ```
    az provider register --namespace Microsoft.EventGrid
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

1. When the script is running, enter **1** to launch the **1. Create Event Grid namespace and topic** option.

    This option creates the resource group if it doesn't already exist, deploys an Event Grid Namespace with the Standard SKU, and creates a namespace topic named **moderation-events** configured for CloudEvents v1.0 input. The namespace is the container for your topic and event subscriptions, and pull delivery lets your application connect directly to Event Grid to receive events without needing a separate messaging service.

1. Enter **2** to run the **2. Create event subscriptions** option.

    This option creates three event subscriptions on the namespace topic. The **sub-flagged** subscription uses an event type filter that delivers only **com.contoso.ai.ContentFlagged** events. The **sub-approved** subscription delivers only **com.contoso.ai.ContentApproved** events. The **sub-all-events** subscription has no filter and delivers every event published to the topic, serving as an audit log. Each subscription is configured with pull delivery mode, a 60-second receive lock duration, a maximum delivery count of 10, and a one-day event time-to-live.

1. Enter **3** to run the **3. Assign user roles** option. This assigns the EventGrid Data Sender role and the EventGrid Data Receiver role on the namespace so your account can publish events and receive events using Microsoft Entra authentication.

1. Enter **4** to run the **4. Retrieve connection info** option. This creates the environment variable files with the resource group name, namespace name, topic name, and namespace endpoint.

1. Enter **6** to exit the deployment script.

    > **Note:** If you encounter issues later in the exercise, you can rerun the script and enter **5** to run **5. Check deployment status**. This troubleshooting option verifies that the namespace shows **Succeeded**, the topic is created, roles are assigned, and all event subscriptions are provisioned.

1. Run the appropriate command to load the environment variables into your terminal session from the file created in a previous step.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

    >**Note:** Keep the terminal open. If you close it and create a new terminal, you need to run this command again to reload the environment variables.

## Complete the app

In this section you add code to the *event_grid_functions.py* file to complete the Event Grid publishing and pull delivery functions. The Flask app in *app.py* calls these functions and displays the results in the browser. You run the app later in the exercise.

1. Open the *client/event_grid_functions.py* file to begin adding code.

>**Note:** The code blocks you add to the application should align with the comment for that section of the code.

### Add code to publish moderation events

In this section, you add code to publish five content moderation events to the Event Grid namespace topic. The events use the CloudEvents v1.0 schema and represent different moderation outcomes — flagged content, approved content, and an escalated review — so you can observe how each subscription's event type filter determines which events it delivers.

The function loads event definitions from the *moderation_events.json* file, which contains the CloudEvent envelope fields (**type**, **source**, **subject**) and **data** payload for each event. At publish time, the function adds a unique **id** and a current UTC **timestamp** to each event, then creates **CloudEvent** objects and publishes them with the **send()** method in a single request. The **EventGridPublisherClient** is constructed with a **namespace_topic** parameter that targets the namespace topic endpoint, and uses **DefaultAzureCredential** for Microsoft Entra authentication.

1. Locate the **# BEGIN PUBLISH EVENTS FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def publish_moderation_events():
        """Publish content moderation events to the Event Grid namespace topic."""
        client = get_publisher_client()
        results = []

        # Load event definitions from the JSON file. Each entry contains the
        # CloudEvent envelope fields (type, source, subject) and the data
        # payload that mirrors a realistic AI content moderation pipeline.
        json_path = os.path.join(os.path.dirname(__file__), "moderation_events.json")
        with open(json_path, "r") as f:
            event_definitions = json.load(f)

        # Build CloudEvent objects from the definitions, adding a unique id
        # and a current UTC timestamp to each event at publish time.
        events = []
        for defn in event_definitions:
            defn["data"]["timestamp"] = datetime.now(timezone.utc).isoformat()
            events.append(
                CloudEvent(
                    type=defn["type"],
                    source=defn["source"],
                    subject=defn["subject"],
                    data=defn["data"],
                    id=str(uuid.uuid4())
                )
            )

        # send() publishes all events to the Event Grid namespace topic in a
        # single request. Event Grid then evaluates each subscription's
        # filters and routes matching events to the configured subscriptions.
        client.send(events)

        for event in events:
            results.append({
                "content_id": event.data["contentId"],
                "event_type": event.type.split(".")[-1],
                "category": event.data["category"],
                "confidence": event.data["confidence"],
                "status": "published"
            })

        return results
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to receive and acknowledge events

In this section, you add code to receive events from each subscription and acknowledge them to verify that filtering works. Pull delivery means your application connects to Event Grid and requests events rather than Event Grid pushing them to an endpoint. Each received event includes a lock token that you must acknowledge to permanently remove the event from the subscription, or the event is redelivered after the lock duration expires.

The function creates an **EventGridConsumerClient** for each of the three subscriptions. The **receive()** method returns a list of **ReceiveDetails** objects, each containing the **CloudEvent** (**.event**) and broker properties with a **lock_token**. After processing, the function calls **acknowledge()** with the collected lock tokens to confirm that the events were successfully handled.

1. Locate the **# BEGIN CHECK DELIVERY FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def check_filtered_delivery():
        """Receive and acknowledge events from each subscription to verify filtering."""
        flagged = []
        approved = []
        all_events = []

        # Receive from the sub-flagged subscription, which only delivers
        # events where the event type is com.contoso.ai.ContentFlagged.
        # receive() returns a list of ReceiveDetails, each containing
        # the CloudEvent and a lock token for acknowledgment.
        consumer = get_consumer_client(SUB_FLAGGED)
        details = consumer.receive(max_events=10, max_wait_time=5)
        tokens = []
        for detail in details:
            event = detail.event
            flagged.append({
                "content_id": event.data.get("contentId"),
                "category": event.data.get("category"),
                "severity": event.data.get("severity"),
                "confidence": event.data.get("confidence")
            })
            tokens.append(detail.broker_properties.lock_token)
        # acknowledge() removes the events from the subscription so they
        # are not delivered again on the next receive call.
        if tokens:
            consumer.acknowledge(lock_tokens=tokens)

        # Receive from the sub-approved subscription, which only delivers
        # events where the event type is com.contoso.ai.ContentApproved.
        consumer = get_consumer_client(SUB_APPROVED)
        details = consumer.receive(max_events=10, max_wait_time=5)
        tokens = []
        for detail in details:
            event = detail.event
            approved.append({
                "content_id": event.data.get("contentId"),
                "category": event.data.get("category"),
                "severity": event.data.get("severity"),
                "confidence": event.data.get("confidence")
            })
            tokens.append(detail.broker_properties.lock_token)
        if tokens:
            consumer.acknowledge(lock_tokens=tokens)

        # Receive from the sub-all-events subscription, which has no filter
        # and delivers every event published to the topic (audit log).
        consumer = get_consumer_client(SUB_ALL)
        details = consumer.receive(max_events=10, max_wait_time=5)
        tokens = []
        for detail in details:
            event = detail.event
            all_events.append({
                "content_id": event.data.get("contentId"),
                "event_type": event.data.get("modelName", "unknown"),
                "category": event.data.get("category"),
                "confidence": event.data.get("confidence")
            })
            tokens.append(detail.broker_properties.lock_token)
        if tokens:
            consumer.acknowledge(lock_tokens=tokens)

        return {
            "flagged": flagged,
            "approved": approved,
            "all_events": all_events
        }
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to inspect and reject an event

In this section, you add code that publishes a single test event, receives it, inspects the full CloudEvent envelope, and then rejects it. Rejecting an event tells Event Grid that the event cannot be processed. This is different from acknowledging, which confirms successful processing. Rejected events are discarded or moved to a dead-letter destination if one is configured.

The function first publishes a test event using the **EventGridPublisherClient** so there is always an event available regardless of whether earlier events were already acknowledged. It then receives the event from the **sub-flagged** subscription, extracts the CloudEvent attributes and broker properties (including **delivery_count**), and calls **reject()** with the lock token.

1. Locate the **# BEGIN INSPECT AND REJECT FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def inspect_and_reject():
        """Publish one event, receive it, inspect the CloudEvent envelope, then reject it."""
        publisher = get_publisher_client()

        # Publish a single test event so there is always something to inspect,
        # regardless of whether the student already acknowledged earlier events.
        test_event = CloudEvent(
            type="com.contoso.ai.ContentFlagged",
            source="/services/content-moderation",
            subject="/content/text/test-inspect",
            data={
                "contentId": "test-inspect",
                "contentType": "text",
                "modelName": "text-moderator-v2",
                "modelVersion": "2.4.0",
                "confidence": 0.76,
                "category": "misinformation",
                "severity": "medium",
                "reviewRequired": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            id=str(uuid.uuid4())
        )
        publisher.send([test_event])

        # Receive from the sub-flagged subscription to pick up the test event.
        consumer = get_consumer_client(SUB_FLAGGED)
        details = consumer.receive(max_events=1, max_wait_time=10)

        if not details:
            return None

        detail = details[0]
        event = detail.event
        lock_token = detail.broker_properties.lock_token
        delivery_count = detail.broker_properties.delivery_count

        # Capture the full CloudEvent envelope before rejecting.
        result = {
            "specversion": "1.0",
            "type": event.type,
            "source": event.source,
            "subject": event.subject,
            "id": event.id,
            "time": str(event.time) if event.time else "",
            "data": event.data,
            "delivery_count": delivery_count,
            "action": "rejected"
        }

        # reject() tells Event Grid this event cannot be processed. The event
        # is moved to the dead-letter location if configured, or discarded
        # if max delivery count has been reached.
        consumer.reject(lock_tokens=[lock_token])

        return result
    ```

1. Save your changes and take a few minutes to review the code.

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

In this section, you run the completed Flask application to publish content moderation events and verify that filtered subscriptions deliver them correctly. The app provides a web interface that lets you publish events, receive and acknowledge events from filtered subscriptions, and inspect and reject an event to explore the full CloudEvent structure and pull delivery operations.

1. Run the following command in the terminal to start the app. Refer to the commands from earlier in the exercise to activate the environment, if needed, before running the command. If you navigated away from the *client* directory, run **cd client** first.

    ```
    python app.py
    ```

1. Open a browser and navigate to `http://localhost:5000` to access the app.

1. Select **Publish Moderation Events** in the left panel. This publishes five content moderation events to the Event Grid namespace topic: two flagged content events, two approved content events, and one escalated review. The results in the right panel confirm each event was published along with its content ID, event type, and category.

1. Select **Receive & Acknowledge Events** in the left panel. This uses pull delivery to receive events from all three subscriptions and acknowledges them after processing. Verify the following delivery behavior based on the filters configured on each subscription:

    - **Flagged Subscription:** Should contain two events, both with category values indicating policy violations (violence and hate-speech). These are the **ContentFlagged** events.
    - **Approved Subscription:** Should contain two events, both with the category **safe**. These are the **ContentApproved** events.
    - **All Events Subscription:** Should contain all five events regardless of type, serving as the audit log.

    The escalated review event (**ReviewEscalated**) appears only in the all-events subscription because neither the flagged nor approved subscriptions include that event type in their filter. Because the events were acknowledged, selecting this button again will show zero events until you publish more.

1. Select **Inspect & Reject Event** in the left panel. This publishes a new test event, receives it from the flagged subscription, displays the full CloudEvent envelope including the **delivery_count** from the broker properties, and then rejects the event. The rejection tells Event Grid this event cannot be processed, so Event Grid either discards it or moves it to a dead-letter destination if one is configured.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues while completing this exercise, try the following troubleshooting steps:

**Verify Event Grid Namespace deployment**
- Navigate to the [Azure portal](https://portal.azure.com) and locate your resource group.
- Confirm that the Event Grid Namespace shows a **Provisioning State** of **Succeeded**.
- Verify the namespace topic **moderation-events** exists within the namespace.

**Check event subscriptions**
- Verify all three event subscriptions were created by running the deployment script status check (option 5).
- Confirm the subscriptions show **Succeeded** status: **sub-flagged**, **sub-approved**, and **sub-all-events**.
- If no events are received after publishing, ensure the subscriptions were created after the topic. Rerun the deployment script option 2 if needed.

**Check code completeness and indentation**
- Ensure all code blocks were added to the correct sections in *event_grid_functions.py* between the appropriate BEGIN/END comment markers.
- Verify that Python indentation is consistent (use spaces, not tabs) and that all code aligns properly within functions.
- Confirm that no code was accidentally removed or modified outside the designated sections.

**Verify environment variables**
- Check that the *.env* file exists in the project root and contains **EVENTGRID_ENDPOINT**, **EVENTGRID_TOPIC_NAME**, **RESOURCE_GROUP**, and **NAMESPACE_NAME** values.
- Ensure you ran **source .env** (Bash) or **. .\.env.ps1** (PowerShell) to load environment variables into your terminal session.
- If variables are empty, re-run **source .env** (Bash) or **. .\.env.ps1** (PowerShell).

**Check authentication**
- Confirm you are logged in to Azure CLI by running **az account show**.
- Verify the EventGrid Data Sender and EventGrid Data Receiver roles are assigned on the namespace. Run the deployment script's role assignment option (option 3) again if needed.

**Check Python environment and dependencies**
- Confirm the virtual environment is activated before running the app.
- Verify that all packages from *requirements.txt* were installed successfully by running **pip list**.
