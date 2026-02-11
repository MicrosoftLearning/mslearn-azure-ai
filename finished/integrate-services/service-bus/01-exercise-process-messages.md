---
lab:
    topic: Azure Service Bus
    title: 'Process messages with Azure Service Bus'
    description: 'Learn how to send, receive, and route messages using Azure Service Bus queues, topics, and subscriptions with the Python SDK.'
    level: 200
    duration: 30
---

# Process messages with Azure Service Bus

In this exercise, you create an Azure Service Bus namespace and build a Python console application that demonstrates core messaging patterns. You work with queues to send and receive messages using peek-lock delivery, inspect the dead-letter queue for failed messages, and use topics with filtered subscriptions for fan-out messaging.

Tasks performed in this exercise:

- Download the project starter files
- Create an Azure Service Bus namespace
- Create messaging entities using the Azure CLI
- Add code to the starter files to complete the console app
- Run the console app to perform messaging operations

This exercise takes approximately **30** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli?view=azure-cli-latest).

## Download project starter files and deploy Azure Service Bus

In this section you download the starter files for the console app and use a script to deploy an Azure Service Bus namespace to your subscription.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/service-bus-messaging-python.zip
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

1. When the script is running, enter **1** to launch the **1. Create Service Bus namespace** option.

    This option creates the resource group if it doesn't already exist, and deploys an Azure Service Bus namespace with the Standard tier. The namespace is the container for all messaging entities you create during the exercise.

1. After the deployment completes, enter **2** to run the **2. Check deployment status** option. Verify the status shows **Succeeded** before continuing. If the namespace is still provisioning, wait a moment and try again.

1. Enter **3** to run the **3. Assign role and create .env file** option. This assigns the Azure Service Bus Data Owner role to your account and creates the environment variable files with the resource group name, namespace name, and fully qualified domain name (FQDN).

1. Enter **4** to exit the deployment script.

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

## Create messaging entities

In this section you use the Azure CLI to create the queue, topic, and subscriptions that the console app uses. These are the types of operations a developer typically performs when setting up messaging resources for an application.

1. Run the following command to create a queue named **inference-requests**. The queue is configured with a max delivery count of 5 so that poison messages are automatically moved to the dead-letter queue after five failed delivery attempts. Dead-lettering on message expiration is also enabled.

    ```
    az servicebus queue create \
        --name inference-requests \
        --namespace-name $NAMESPACE_NAME \
        --resource-group $RESOURCE_GROUP \
        --max-delivery-count 5 \
        --enable-dead-lettering-on-message-expiration true
    ```

1. Run the following command to create a topic named **inference-results**. Topics enable fan-out messaging where multiple subscriptions can each receive a copy of every message.

    ```
    az servicebus topic create \
        --name inference-results \
        --namespace-name $NAMESPACE_NAME \
        --resource-group $RESOURCE_GROUP
    ```

1. Run the following commands to create two subscriptions on the topic. The **notifications** subscription receives all messages, while the **high-priority** subscription will be configured with a filter in the next step.

    ```
    az servicebus topic subscription create \
        --name notifications \
        --topic-name inference-results \
        --namespace-name $NAMESPACE_NAME \
        --resource-group $RESOURCE_GROUP

    az servicebus topic subscription create \
        --name high-priority \
        --topic-name inference-results \
        --namespace-name $NAMESPACE_NAME \
        --resource-group $RESOURCE_GROUP
    ```

1. Run the following commands to add a SQL filter to the **high-priority** subscription. The first command removes the default **$Default** rule that accepts all messages. The second command creates a new rule that only allows messages where the **priority** application property equals **high**.

    **Bash**
    ```bash
    az servicebus topic subscription rule delete \
        --name '$Default' \
        --subscription-name high-priority \
        --topic-name inference-results \
        --namespace-name $NAMESPACE_NAME \
        --resource-group $RESOURCE_GROUP

    az servicebus topic subscription rule create \
        --name high-priority-filter \
        --subscription-name high-priority \
        --topic-name inference-results \
        --namespace-name $NAMESPACE_NAME \
        --resource-group $RESOURCE_GROUP \
        --filter-sql-expression "priority = 'high'"
    ```

    **PowerShell**
    ```powershell
    az servicebus topic subscription rule delete `
        --name '$Default' `
        --subscription-name high-priority `
        --topic-name inference-results `
        --namespace-name $NAMESPACE_NAME `
        --resource-group $RESOURCE_GROUP

    az servicebus topic subscription rule create `
        --name high-priority-filter `
        --subscription-name high-priority `
        --topic-name inference-results `
        --namespace-name $NAMESPACE_NAME `
        --resource-group $RESOURCE_GROUP `
        --filter-sql-expression "priority = 'high'"
    ```

## Complete the app

In this section you add code to the *main.py* script to complete the console app. You run the app later in the exercise, after confirming the messaging entities are created.

1. Open the *client/main.py* file to begin adding code.

>**Note:** The code blocks you add to the application should align with the comment for that section of the code.

### Add the client connection

In this section, you add code to establish a connection to Azure Service Bus using Microsoft Entra authentication. The code retrieves the fully qualified namespace from environment variables and creates a **ServiceBusClient** instance using **DefaultAzureCredential**.

1. Locate the **# BEGIN CONNECTION CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    try:
        fqdn = os.getenv("SERVICE_BUS_FQDN")

        credential = DefaultAzureCredential()
        client = ServiceBusClient(
            fully_qualified_namespace=fqdn,
            credential=credential
        )

        print(f"Connected to Service Bus namespace: {fqdn}")
        input("\nPress Enter to continue...")
        return client
    ```

### Add code to send messages to the queue

In this section, you add code to send three messages to the queue. Two messages have valid JSON payloads representing inference requests, and one has intentionally malformed JSON to simulate a processing failure that demonstrates the dead-letter queue.

1. Locate the **# BEGIN SEND MESSAGES CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def send_messages(client, queue_name) -> None:
        """Send messages to the queue including one malformed message"""
        clear_screen()
        print("Sending messages to queue...")

        with client.get_queue_sender(queue_name) as sender:
            # Valid message 1
            msg1 = ServiceBusMessage(
                body=json.dumps({
                    "prompt": "Extract parties and effective date.",
                    "model": "gpt-4o",
                    "document_id": "doc-001"
                }),
                content_type="application/json",
                message_id=str(uuid.uuid4()),
                correlation_id="req-doc-001",
                application_properties={"priority": "standard", "document_type": "contract"}
            )
            sender.send_messages(msg1)
            print(f"  Sent message: {msg1.correlation_id}")

            # Valid message 2
            msg2 = ServiceBusMessage(
                body=json.dumps({
                    "prompt": "Summarize the key terms.",
                    "model": "gpt-4o",
                    "document_id": "doc-002"
                }),
                content_type="application/json",
                message_id=str(uuid.uuid4()),
                correlation_id="req-doc-002",
                application_properties={"priority": "high", "document_type": "contract"}
            )
            sender.send_messages(msg2)
            print(f"  Sent message: {msg2.correlation_id}")

            # Invalid message (malformed body)
            msg3 = ServiceBusMessage(
                body="not valid json: [broken",
                content_type="application/json",
                message_id=str(uuid.uuid4()),
                correlation_id="req-doc-003",
                application_properties={"priority": "standard"}
            )
            sender.send_messages(msg3)
            print(f"  Sent malformed message: {msg3.correlation_id}")

        print("\nAll messages sent successfully.")
        input("\nPress Enter to continue...")
    ```

### Add code to process messages with peek-lock

In this section, you add code to receive messages from the queue using peek-lock mode. The processor validates the JSON payload, completes valid messages, and dead-letters messages with invalid JSON by providing a reason and error description.

1. Locate the **# BEGIN PROCESS MESSAGES CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def process_messages(client, queue_name) -> None:
        """Receive and process messages from the queue using peek-lock"""
        clear_screen()
        print("Processing messages from queue...\n")

        with client.get_queue_receiver(
            queue_name=queue_name,
            max_wait_time=10
        ) as receiver:
            for msg in receiver:
                print(f"Received message: correlation_id={msg.correlation_id}")
                try:
                    payload = json.loads(str(msg))
                    print(f"  Document: {payload.get('document_id')}")
                    print(f"  Model: {payload.get('model')}")
                    print(f"  Prompt: {payload.get('prompt')[:50]}...")
                    receiver.complete_message(msg)
                    print(f"  Status: Completed\n")
                except json.JSONDecodeError:
                    receiver.dead_letter_message(
                        msg,
                        reason="MalformedPayload",
                        error_description="Message body is not valid JSON"
                    )
                    print(f"  Status: Dead-lettered (invalid JSON)\n")

        print("No more messages. Processing complete.")
        input("\nPress Enter to continue...")
    ```

### Add code to inspect the dead-letter queue

In this section, you add code to read messages from the dead-letter queue and display diagnostic information. The dead-letter queue captures messages that couldn't be processed, along with the reason and error description for troubleshooting.

1. Locate the **# BEGIN INSPECT DLQ CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def inspect_dead_letter_queue(client, queue_name) -> None:
        """Inspect messages in the dead-letter queue"""
        clear_screen()
        print("Dead-letter queue messages:\n")

        with client.get_queue_receiver(
            queue_name=queue_name,
            sub_queue=ServiceBusSubQueue.DEAD_LETTER,
            max_wait_time=10
        ) as dlq_receiver:
            count = 0
            for msg in dlq_receiver:
                count += 1
                print(f"  Message ID: {msg.message_id}")
                print(f"  Correlation ID: {msg.correlation_id}")
                print(f"  Dead-letter reason: {msg.dead_letter_reason}")
                print(f"  Error description: {msg.dead_letter_error_description}")
                print(f"  Delivery count: {msg.delivery_count}")
                print(f"  Body: {str(msg)[:100]}")
                print()
                dlq_receiver.complete_message(msg)

            if count == 0:
                print("  No messages in the dead-letter queue.")

        print("\nDead-letter queue inspection complete.")
        input("\nPress Enter to continue...")
    ```

### Add code for topic messaging with filtered subscriptions

In this section, you add code to send messages to a topic with different priority levels, then receive from each subscription to verify that filtering works. The **notifications** subscription receives all messages, while the **high-priority** subscription receives only messages where the **priority** application property equals **high**.

1. Locate the **# BEGIN TOPIC MESSAGING CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def topic_messaging(client, topic_name) -> None:
        """Send messages to a topic and receive from filtered subscriptions"""
        clear_screen()
        print("Sending messages to topic...\n")

        # Send messages with different priorities
        with client.get_topic_sender(topic_name) as sender:
            for i, priority in enumerate(["standard", "high", "standard", "high", "low"]):
                result = {
                    "document_id": f"doc-{i+1:03d}",
                    "status": "completed",
                    "confidence": 0.95
                }
                msg = ServiceBusMessage(
                    body=json.dumps(result),
                    content_type="application/json",
                    message_id=str(uuid.uuid4()),
                    application_properties={"priority": priority}
                )
                sender.send_messages(msg)
                print(f"  Sent to topic: doc-{i+1:03d}, priority={priority}")

        # Receive from notifications subscription (all messages)
        print("\n--- Notifications subscription (all messages) ---")
        with client.get_subscription_receiver(
            topic_name=topic_name,
            subscription_name="notifications",
            max_wait_time=10
        ) as receiver:
            for msg in receiver:
                body = json.loads(str(msg))
                props = msg.application_properties or {}
                priority_val = props.get("priority") or props.get(b"priority", b"unknown")
                if isinstance(priority_val, bytes):
                    priority_val = priority_val.decode("utf-8")
                print(f"  Received: {body['document_id']}, priority={priority_val}")
                receiver.complete_message(msg)

        # Receive from high-priority subscription (filtered)
        print("\n--- High-priority subscription (filtered) ---")
        with client.get_subscription_receiver(
            topic_name=topic_name,
            subscription_name="high-priority",
            max_wait_time=10
        ) as receiver:
            for msg in receiver:
                body = json.loads(str(msg))
                props = msg.application_properties or {}
                priority_val = props.get("priority") or props.get(b"priority", b"unknown")
                if isinstance(priority_val, bytes):
                    priority_val = priority_val.decode("utf-8")
                print(f"  Received: {body['document_id']}, priority={priority_val}")
                receiver.complete_message(msg)

        print("\nTopic messaging complete.")
        input("\nPress Enter to continue...")
    ```

1. Save your changes to the *main.py* file.

## Run the console app

In this section, you run the completed console application to perform various Service Bus messaging operations. The app provides a menu-driven interface that lets you send messages, process them with peek-lock delivery, inspect the dead-letter queue, and test topic messaging with filtered subscriptions.

1. Run the following command in the terminal to start the console app. Refer to the commands from earlier in the exercise to activate the environment, if needed, before running the command. If you navigated away from the *client* directory, run **cd client** first.

    ```
    python main.py
    ```

1. The app has the following options. Select **1. Send messages to queue** to get started.

    ```
    1. Send messages to queue
    2. Process messages from queue
    3. Inspect dead-letter queue
    4. Send and receive topic messages
    5. Exit
    ```

1. Select the remaining options in order to run the different operations.

>**Note:** Run the options in order for the best experience. Option 1 sends three messages (two valid, one malformed). Option 2 processes them, completing the valid messages and dead-lettering the malformed one. Option 3 inspects the dead-letter queue to display the failed message's diagnostic information. Option 4 demonstrates topic messaging with filtered subscriptions.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. The command uses the **RESOURCE_GROUP** environment variable set earlier. If needed, replace **$RESOURCE_GROUP** with the name you chose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name $RESOURCE_GROUP --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues while completing this exercise, try the following troubleshooting steps:

**Verify Azure Service Bus namespace deployment**
- Navigate to the [Azure portal](https://portal.azure.com) and locate your resource group.
- Confirm that the Service Bus namespace shows a **Provisioning State** of **Succeeded**.
- Verify the namespace tier is **Standard** (required for topics and subscriptions).

**Check messaging entities**
- Verify the queue, topic, and subscriptions were created by running **az servicebus queue list**, **az servicebus topic list**, and **az servicebus topic subscription list** commands.
- Confirm the SQL filter was applied to the **high-priority** subscription by checking that the **$Default** rule was removed and the **high-priority-filter** rule exists.

**Check code completeness and indentation**
- Ensure all code blocks were added to the correct sections in *main.py* between the appropriate BEGIN/END comment markers.
- Verify that Python indentation is consistent (use spaces, not tabs) and that all code aligns properly within functions.
- Confirm that no code was accidentally removed or modified outside the designated sections.

**Verify environment variables**
- Check that the *.env* file exists in the project root and contains **SERVICE_BUS_FQDN**, **RESOURCE_GROUP**, and **NAMESPACE_NAME** values.
- Ensure you ran **source .env** (Bash) or **. .\.env.ps1** (PowerShell) to load environment variables into your terminal session.
- If variables are empty, re-run **source .env** (Bash) or **. .\.env.ps1** (PowerShell).

**Check authentication**
- Confirm you are logged in to Azure CLI by running **az account show**.
- Verify the Azure Service Bus Data Owner role is assigned to your account by checking the role assignments in the Azure portal or running the deployment script's option to assign the role again.

**Check Python environment and dependencies**
- Confirm the virtual environment is activated before running the app.
- Verify that all packages from *requirements.txt* were installed successfully by running **pip list**.
