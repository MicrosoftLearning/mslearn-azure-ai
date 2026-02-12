---
lab:
    topic: Integrate backend services
    title: 'Trigger and process events with Azure Event Grid'
    description: 'Learn how to publish and route content moderation events using Azure Event Grid with filtered subscriptions and Service Bus queue endpoints.'
    level: 200
    duration: 30
---

{% include under-construction.md %}

# Trigger and process events with Azure Event Grid

AI content moderation systems generate a high volume of events as they classify and review submissions. Azure Event Grid provides the routing layer that directs these events to the right downstream consumers based on event type, so each handler receives only the events it needs without polling or manual filtering.

In this exercise, you deploy an Event Grid custom topic and a Service Bus namespace, then build a Python Flask application that publishes content moderation events and reads the filtered results from Service Bus queues. Event Grid subscriptions route flagged content, approved content, and all events to separate queues so you can observe how filtering and fan-out delivery work in practice.

Tasks performed in this exercise:

- Download the project starter files
- Deploy an Event Grid topic and Service Bus namespace
- Create Service Bus queues and event subscriptions with filters
- Add code to the starter files to complete the app
- Run the app to publish and inspect moderation events

This exercise takes approximately **30** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli?view=azure-cli-latest).

## Download project starter files and deploy resources

In this section you download the starter files for the app and use a script to deploy an Event Grid custom topic and a Service Bus namespace to your subscription. Event Grid handles event routing while Service Bus queues serve as the delivery endpoints that your local Flask app reads from.

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

1. Run the following commands to ensure your subscription has the necessary resource providers for the exercise.

    ```
    az provider register --namespace Microsoft.EventGrid
    az provider register --namespace Microsoft.ServiceBus
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

1. When the script is running, enter **1** to launch the **1. Create Event Grid topic and Service Bus namespace** option.

    This option creates the resource group if it doesn't already exist, deploys an Event Grid custom topic configured for the CloudEvents v1.0 schema, and creates an Azure Service Bus namespace with the Standard tier. The topic is where your application publishes moderation events, and the Service Bus queues serve as delivery endpoints that Event Grid routes events to.

1. Enter **2** to run the **2. Create queues and event subscriptions** option.

    This option creates three Service Bus queues and three Event Grid subscriptions that connect the topic to those queues. The **flagged-content** queue receives only events with the type **com.contoso.ai.ContentFlagged**. The **approved-content** queue receives only **com.contoso.ai.ContentApproved** events. The **all-events** queue receives every event published to the topic regardless of type, serving as an audit log.

1. Enter **3** to run the **3. Assign roles** option. This assigns the EventGrid Data Sender role on the topic and the Azure Service Bus Data Owner role on the namespace so your account can publish events and read from queues using Microsoft Entra authentication.

1. Enter **4** to run the **4. Check deployment status** option. Verify that the topic and namespace both show **Succeeded** and the roles are assigned before continuing. If either resource is still provisioning, wait a moment and try again.

1. Enter **5** to run the **5. Retrieve connection info** option. This creates the environment variable files with the resource group name, topic endpoint, namespace name, and Service Bus FQDN.

1. Enter **6** to exit the deployment script.

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

In this section you add code to the *event_grid_functions.py* file to complete the Event Grid publishing and Service Bus reading functions. The Flask app in *app.py* calls these functions and displays the results in the browser. You run the app later in the exercise.

1. Open the *client/event_grid_functions.py* file to begin adding code.

>**Note:** The code blocks you add to the application should align with the comment for that section of the code.

### Add code to publish moderation events

In this section, you add code to publish five content moderation events to the Event Grid topic. The events use the CloudEvents v1.0 schema and represent different moderation outcomes — flagged content, approved content, and an escalated review — so you can observe how each subscription's event type filter determines which queue receives each event.

The function loads event definitions from the *moderation_events.json* file, which contains the CloudEvent envelope fields (**type**, **source**, **subject**) and **data** payload for each event. At publish time, the function adds a unique **id** and a current UTC **timestamp** to each event, then creates **CloudEvent** objects and publishes them with the **send()** method in a single request. The **EventGridPublisherClient** uses **DefaultAzureCredential** for Microsoft Entra authentication.

1. Locate the **# BEGIN PUBLISH EVENTS FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def publish_moderation_events():
        """Publish content moderation events to the Event Grid topic."""
        client = get_eventgrid_client()
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

        # send() publishes all events to the Event Grid custom topic in a
        # single request. Event Grid then evaluates each subscription's
        # filters and routes matching events to the configured endpoints.
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

### Add code to check filtered delivery

In this section, you add code to read delivered events from each Service Bus queue, demonstrating how Event Grid's event type filters route different moderation outcomes to different queues. The function reads from all three queues and returns the results so the Flask app can display them side by side.

The function creates a **ServiceBusClient** using **DefaultAzureCredential** and opens a **get_queue_receiver()** for each of the three queues. The **flagged-content** queue should contain only **ContentFlagged** events, the **approved-content** queue should contain only **ContentApproved** events, and the **all-events** queue should contain all five events. Each message is parsed from JSON, and **complete_message()** removes it from the queue after processing.

1. Locate the **# BEGIN CHECK DELIVERY FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def check_filtered_delivery():
        """Read delivered events from each Service Bus queue to verify filtering."""
        client = get_servicebus_client()
        flagged = []
        approved = []
        all_events = []

        with client:
            # Read from the flagged-content queue, which receives only events
            # where the event type is com.contoso.ai.ContentFlagged.
            # max_wait_time controls how long the receiver waits for messages.
            with client.get_queue_receiver(
                queue_name=FLAGGED_QUEUE,
                max_wait_time=5
            ) as receiver:
                for msg in receiver:
                    body = json.loads(str(msg))
                    flagged.append({
                        "content_id": body.get("contentId"),
                        "category": body.get("category"),
                        "severity": body.get("severity"),
                        "confidence": body.get("confidence")
                    })
                    # complete_message removes the message from the queue
                    receiver.complete_message(msg)

            # Read from the approved-content queue, which receives only events
            # where the event type is com.contoso.ai.ContentApproved.
            with client.get_queue_receiver(
                queue_name=APPROVED_QUEUE,
                max_wait_time=5
            ) as receiver:
                for msg in receiver:
                    body = json.loads(str(msg))
                    approved.append({
                        "content_id": body.get("contentId"),
                        "category": body.get("category"),
                        "severity": body.get("severity"),
                        "confidence": body.get("confidence")
                    })
                    receiver.complete_message(msg)

            # Read from the all-events queue, which has no filter and
            # receives every event published to the topic (audit log).
            with client.get_queue_receiver(
                queue_name=ALL_EVENTS_QUEUE,
                max_wait_time=5
            ) as receiver:
                for msg in receiver:
                    body = json.loads(str(msg))
                    all_events.append({
                        "content_id": body.get("contentId"),
                        "event_type": body.get("modelName", "unknown"),
                        "category": body.get("category"),
                        "confidence": body.get("confidence")
                    })
                    receiver.complete_message(msg)

        return {
            "flagged": flagged,
            "approved": approved,
            "all_events": all_events
        }
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to inspect event details

In this section, you add code to peek at a message from the all-events queue to examine the full CloudEvent structure without removing the message. This demonstrates how Event Grid preserves CloudEvent attributes when delivering to Service Bus queues.

The function uses **peek_messages()** to read a message without locking or removing it. When Event Grid delivers CloudEvents to a Service Bus queue, the event **data** becomes the message body and the envelope attributes (**specversion**, **type**, **source**, **subject**, **id**, **time**) are stored as application properties with a **cloudEvents:** prefix.

1. Locate the **# BEGIN INSPECT EVENT FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def inspect_event_details():
        """Peek at a message from the all-events queue to show CloudEvent structure."""
        client = get_servicebus_client()
        result = None

        with client:
            # peek_messages reads messages without locking or removing them,
            # so they remain available for subsequent receive operations.
            with client.get_queue_receiver(
                queue_name=ALL_EVENTS_QUEUE,
                max_wait_time=5
            ) as receiver:
                peeked = receiver.peek_messages(max_message_count=1)
                if peeked:
                    msg = peeked[0]
                    body = json.loads(str(msg))

                    # Extract the CloudEvent attributes that Event Grid
                    # preserves when delivering to Service Bus queues.
                    # The message body contains the CloudEvent data field,
                    # while envelope attributes are in application_properties.
                    props = msg.application_properties or {}

                    def decode_prop(key):
                        val = props.get(key) or props.get(
                            key.encode("utf-8") if isinstance(key, str) else key,
                            ""
                        )
                        if isinstance(val, bytes):
                            val = val.decode("utf-8")
                        return str(val) if val else ""

                    result = {
                        "specversion": decode_prop("cloudEvents:specversion") or "1.0",
                        "type": decode_prop("cloudEvents:type"),
                        "source": decode_prop("cloudEvents:source"),
                        "subject": decode_prop("cloudEvents:subject"),
                        "id": decode_prop("cloudEvents:id"),
                        "time": decode_prop("cloudEvents:time"),
                        "data": body
                    }

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

In this section, you run the completed Flask application to publish content moderation events to the Event Grid topic and verify that filtered subscriptions routed them to the correct Service Bus queues. The app provides a web interface that lets you publish events, check filtered delivery across queues, and inspect the CloudEvent structure of delivered events.

1. Run the following command in the terminal to start the app. Refer to the commands from earlier in the exercise to activate the environment, if needed, before running the command. If you navigated away from the *client* directory, run **cd client** first.

    ```
    python app.py
    ```

1. Open a browser and navigate to `http://localhost:5000` to access the app.

1. Select **Publish Moderation Events** in the left panel. This publishes five content moderation events to the Event Grid topic: two flagged content events, two approved content events, and one escalated review. The results in the right panel confirm each event was published along with its content ID, event type, and category.

1. Select **Check Filtered Delivery** in the left panel. This reads from the three Service Bus queues and displays the events each one received. Verify the following delivery behavior based on the filters you configured:

    - **Flagged Content Queue:** Should contain two events, both with category values indicating policy violations (violence and hate-speech). These are the **ContentFlagged** events.
    - **Approved Content Queue:** Should contain two events, both with the category **safe**. These are the **ContentApproved** events.
    - **All Events Queue:** Should contain all five events regardless of type, serving as the audit log.

    The escalated review event (**ReviewEscalated**) appears only in the all-events queue because neither the flagged nor approved subscriptions include that event type in their filter.

1. Select **Inspect Event Details** in the left panel. This peeks at one event from the all-events queue without removing it and displays the full CloudEvent structure, including the **specversion**, **type**, **source**, **subject**, **id**, **time**, and **data** attributes. This demonstrates how Event Grid preserves CloudEvent envelope attributes as application properties when delivering to Service Bus.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues while completing this exercise, try the following troubleshooting steps:

**Verify Event Grid topic deployment**
- Navigate to the [Azure portal](https://portal.azure.com) and locate your resource group.
- Confirm that the Event Grid topic shows a **Provisioning State** of **Succeeded**.
- Verify the topic is configured with the **CloudEvents v1.0** input schema.

**Verify Service Bus namespace deployment**
- Confirm that the Service Bus namespace shows a **Provisioning State** of **Succeeded**.
- Verify the namespace tier is **Standard** (required for receiving Event Grid deliveries).

**Check queues and event subscriptions**
- Verify the three Service Bus queues were created by running **az servicebus queue list**.
- Verify the three event subscriptions were created by running **az eventgrid event-subscription list**.
- If no events appear in the queues after publishing, check that the event subscriptions were created after the queues. Subscriptions created before their target queue exists will fail silently.

**Check code completeness and indentation**
- Ensure all code blocks were added to the correct sections in *event_grid_functions.py* between the appropriate BEGIN/END comment markers.
- Verify that Python indentation is consistent (use spaces, not tabs) and that all code aligns properly within functions.
- Confirm that no code was accidentally removed or modified outside the designated sections.

**Verify environment variables**
- Check that the *.env* file exists in the project root and contains **EVENTGRID_TOPIC_ENDPOINT**, **SERVICE_BUS_FQDN**, **RESOURCE_GROUP**, and **NAMESPACE_NAME** values.
- Ensure you ran **source .env** (Bash) or **. .\.env.ps1** (PowerShell) to load environment variables into your terminal session.
- If variables are empty, re-run **source .env** (Bash) or **. .\.env.ps1** (PowerShell).

**Check authentication**
- Confirm you are logged in to Azure CLI by running **az account show**.
- Verify the EventGrid Data Sender role is assigned on the topic and the Azure Service Bus Data Owner role is assigned on the namespace. Run the deployment script's role assignment option again if needed.

**Check Python environment and dependencies**
- Confirm the virtual environment is activated before running the app.
- Verify that all packages from *requirements.txt* were installed successfully by running **pip list**.
