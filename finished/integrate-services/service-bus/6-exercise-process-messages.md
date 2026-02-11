In this exercise, you send AI inference requests to a Service Bus queue, process them with peek-lock delivery, handle failures through the dead-letter queue, and create a topic with filtered subscriptions for fan-out messaging. By the end, you'll have hands-on experience with the core Service Bus messaging patterns covered in this module.

> [!NOTE]
> This exercise requires an Azure subscription. If you don't have an Azure subscription, create a [free account](https://azure.microsoft.com/free/) before you begin.

## Create a Service Bus namespace and queue

You can start by creating a Service Bus namespace, a queue, and a topic with subscriptions using the Azure CLI. The namespace serves as the container for all your messaging entities.

1. Set environment variables for your resource names. You can replace the values with names that are unique in your subscription.

    ```bash
    RESOURCE_GROUP="rg-servicebus-lab"
    LOCATION="eastus"
    NAMESPACE_NAME="sbns-ai-lab-$RANDOM"
    QUEUE_NAME="inference-requests"
    TOPIC_NAME="inference-results"
    ```

1. Create a resource group and a Service Bus namespace with the Standard tier.

    ```bash
    az group create --name $RESOURCE_GROUP --location $LOCATION

    az servicebus namespace create \
        --name $NAMESPACE_NAME \
        --resource-group $RESOURCE_GROUP \
        --location $LOCATION \
        --sku Standard
    ```

1. Create a queue for inference requests. You can set the max delivery count to five so that poison messages move to the dead-letter queue after five failed delivery attempts.

    ```bash
    az servicebus queue create \
        --name $QUEUE_NAME \
        --namespace-name $NAMESPACE_NAME \
        --resource-group $RESOURCE_GROUP \
        --max-delivery-count 5 \
        --enable-dead-lettering-on-message-expiration true
    ```

1. Create a topic and two subscriptions for fan-out messaging. The `notifications` subscription receives all messages, while the `high-priority` subscription receives only messages with a `priority` property set to `high`.

    ```bash
    az servicebus topic create \
        --name $TOPIC_NAME \
        --namespace-name $NAMESPACE_NAME \
        --resource-group $RESOURCE_GROUP

    az servicebus topic subscription create \
        --name "notifications" \
        --topic-name $TOPIC_NAME \
        --namespace-name $NAMESPACE_NAME \
        --resource-group $RESOURCE_GROUP

    az servicebus topic subscription create \
        --name "high-priority" \
        --topic-name $TOPIC_NAME \
        --namespace-name $NAMESPACE_NAME \
        --resource-group $RESOURCE_GROUP
    ```

1. Add a SQL filter to the `high-priority` subscription so it only receives messages where the `priority` application property equals `high`. You can first remove the default `$Default` rule (which accepts all messages), then add the filter rule.

    ```bash
    az servicebus topic subscription rule delete \
        --name '$Default' \
        --subscription-name "high-priority" \
        --topic-name $TOPIC_NAME \
        --namespace-name $NAMESPACE_NAME \
        --resource-group $RESOURCE_GROUP

    az servicebus topic subscription rule create \
        --name "high-priority-filter" \
        --subscription-name "high-priority" \
        --topic-name $TOPIC_NAME \
        --namespace-name $NAMESPACE_NAME \
        --resource-group $RESOURCE_GROUP \
        --filter-sql-expression "priority = 'high'"
    ```

## Assign access and get the connection string

1. Retrieve the connection string for your namespace. You use this connection string to authenticate the Python SDK in this exercise.

    ```bash
    CONNECTION_STRING=$(az servicebus namespace authorization-rule keys list \
        --name RootManageSharedAccessKey \
        --namespace-name $NAMESPACE_NAME \
        --resource-group $RESOURCE_GROUP \
        --query primaryConnectionString \
        --output tsv)

    echo $CONNECTION_STRING
    ```

    > [!NOTE]
    > In production applications, you should use Microsoft Entra ID with managed identity instead of connection strings. This exercise uses a connection string for simplicity in a learning environment.

## Set up the Python environment

1. Create a working directory and set up a Python virtual environment.

    ```bash
    mkdir servicebus-lab && cd servicebus-lab
    python -m venv .venv
    source .venv/bin/activate
    pip install azure-servicebus
    ```

## Send structured messages to the queue

1. Create a file named `send_messages.py` that sends three inference request messages to the queue. Two messages have valid JSON payloads, and one has intentionally malformed JSON to simulate a processing failure.

    ```python
    import json
    import uuid
    import os
    from azure.servicebus import ServiceBusClient, ServiceBusMessage

    CONNECTION_STRING = os.environ.get("SERVICE_BUS_CONNECTION_STRING", "<your-connection-string>")
    QUEUE_NAME = "inference-requests"

    def create_inference_message(prompt, model, priority, document_id):
        payload = {
            "prompt": prompt,
            "model": model,
            "temperature": 0.1,
            "max_tokens": 2000,
            "document_id": document_id
        }
        return ServiceBusMessage(
            body=json.dumps(payload),
            content_type="application/json",
            message_id=str(uuid.uuid4()),
            correlation_id=f"req-{document_id}",
            application_properties={
                "model_name": model,
                "priority": priority,
                "document_type": "contract"
            }
        )

    with ServiceBusClient.from_connection_string(CONNECTION_STRING) as client:
        with client.get_queue_sender(QUEUE_NAME) as sender:
            # Valid message 1
            msg1 = create_inference_message(
                prompt="Extract parties and effective date.",
                model="gpt-4o",
                priority="standard",
                document_id="doc-001"
            )
            sender.send_messages(msg1)
            print(f"Sent message: {msg1.correlation_id}")

            # Valid message 2
            msg2 = create_inference_message(
                prompt="Summarize the key terms.",
                model="gpt-4o",
                priority="high",
                document_id="doc-002"
            )
            sender.send_messages(msg2)
            print(f"Sent message: {msg2.correlation_id}")

            # Invalid message (malformed body)
            msg3 = ServiceBusMessage(
                body="not valid json: [broken",
                content_type="application/json",
                message_id=str(uuid.uuid4()),
                correlation_id="req-doc-003",
                application_properties={
                    "model_name": "gpt-4o",
                    "priority": "standard"
                }
            )
            sender.send_messages(msg3)
            print(f"Sent malformed message: {msg3.correlation_id}")

    print("All messages sent successfully.")
    ```

1. Run the sender script.

    ```bash
    SERVICE_BUS_CONNECTION_STRING="$CONNECTION_STRING" python send_messages.py
    ```

## Receive and process messages with peek-lock

1. Create a file named `process_messages.py` that receives messages from the queue using peek-lock mode. The processor completes valid messages and dead-letters messages with invalid JSON.

    ```python
    import json
    import os
    from azure.servicebus import ServiceBusClient

    CONNECTION_STRING = os.environ.get("SERVICE_BUS_CONNECTION_STRING", "<your-connection-string>")
    QUEUE_NAME = "inference-requests"

    def simulate_inference(payload):
        """Simulate AI inference processing."""
        print(f"  Processing document: {payload.get('document_id')}")
        print(f"  Model: {payload.get('model')}")
        print(f"  Prompt: {payload.get('prompt')[:50]}...")
        return {"status": "completed", "document_id": payload.get("document_id")}

    with ServiceBusClient.from_connection_string(CONNECTION_STRING) as client:
        with client.get_queue_receiver(
            queue_name=QUEUE_NAME,
            max_wait_time=10
        ) as receiver:
            print("Waiting for messages...\n")
            for msg in receiver:
                print(f"Received message: correlation_id={msg.correlation_id}")
                try:
                    payload = json.loads(str(msg))
                    result = simulate_inference(payload)
                    receiver.complete_message(msg)
                    print(f"  Completed: {result}\n")
                except json.JSONDecodeError:
                    receiver.dead_letter_message(
                        msg,
                        reason="MalformedPayload",
                        error_description="Message body is not valid JSON"
                    )
                    print(f"  Dead-lettered: invalid JSON\n")

    print("No more messages. Processing complete.")
    ```

1. Run the processor script.

    ```bash
    SERVICE_BUS_CONNECTION_STRING="$CONNECTION_STRING" python process_messages.py
    ```

    You should see two messages processed successfully and one messages dead-lettered due to invalid JSON.

## Inspect the dead-letter queue

1. Create a file named `inspect_dlq.py` that reads messages from the dead-letter queue and displays diagnostic information.

    ```python
    import os
    from azure.servicebus import ServiceBusClient, ServiceBusSubQueue

    CONNECTION_STRING = os.environ.get("SERVICE_BUS_CONNECTION_STRING", "<your-connection-string>")
    QUEUE_NAME = "inference-requests"

    with ServiceBusClient.from_connection_string(CONNECTION_STRING) as client:
        with client.get_queue_receiver(
            queue_name=QUEUE_NAME,
            sub_queue=ServiceBusSubQueue.DEAD_LETTER,
            max_wait_time=10
        ) as dlq_receiver:
            print("Dead-letter queue messages:\n")
            for msg in dlq_receiver:
                print(f"  Message ID: {msg.message_id}")
                print(f"  Correlation ID: {msg.correlation_id}")
                print(f"  Dead-letter reason: {msg.dead_letter_reason}")
                print(f"  Error description: {msg.dead_letter_error_description}")
                print(f"  Delivery count: {msg.delivery_count}")
                print(f"  Body: {str(msg)[:100]}")
                print()
                dlq_receiver.complete_message(msg)

    print("Dead-letter queue inspection complete.")
    ```

1. Run the DLQ inspection script.

    ```bash
    SERVICE_BUS_CONNECTION_STRING="$CONNECTION_STRING" python inspect_dlq.py
    ```

    You should see the malformed message with its dead-letter reason and error description.

## Send messages to a topic with filtered subscriptions

1. Create a file named `topic_messages.py` that sends messages to the topic with different priority levels, then receives from each subscription to verify that filtering works correctly.

    ```python
    import json
    import uuid
    import os
    from azure.servicebus import ServiceBusClient, ServiceBusMessage

    CONNECTION_STRING = os.environ.get("SERVICE_BUS_CONNECTION_STRING", "<your-connection-string>")
    TOPIC_NAME = "inference-results"

    with ServiceBusClient.from_connection_string(CONNECTION_STRING) as client:
        # Send messages with different priorities
        with client.get_topic_sender(TOPIC_NAME) as sender:
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
                print(f"Sent to topic: doc-{i+1:03d}, priority={priority}")

        print("\n--- Notifications subscription (all messages) ---")
        with client.get_subscription_receiver(
            topic_name=TOPIC_NAME,
            subscription_name="notifications",
            max_wait_time=10
        ) as receiver:
            for msg in receiver:
                body = json.loads(str(msg))
                print(f"  Received: {body['document_id']}, priority={msg.application_properties.get('priority')}")
                receiver.complete_message(msg)

        print("\n--- High-priority subscription (filtered) ---")
        with client.get_subscription_receiver(
            topic_name=TOPIC_NAME,
            subscription_name="high-priority",
            max_wait_time=10
        ) as receiver:
            for msg in receiver:
                body = json.loads(str(msg))
                print(f"  Received: {body['document_id']}, priority={msg.application_properties.get('priority')}")
                receiver.complete_message(msg)

    print("\nTopic messaging complete.")
    ```

1. Run the topic messaging script.

    ```bash
    SERVICE_BUS_CONNECTION_STRING="$CONNECTION_STRING" python topic_messages.py
    ```

    The `notifications` subscription should receive all five messages. The `high-priority` subscription should receive only the two messages with `priority` set to `high`.

## Clean up resources

When you're finished with the exercise, you can delete the resource group to remove all the resources you created.

```bash
az group delete --name $RESOURCE_GROUP --yes --no-wait
```
