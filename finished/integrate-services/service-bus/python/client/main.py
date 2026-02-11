import os
import sys
import json
import uuid
from azure.servicebus import ServiceBusClient, ServiceBusMessage, ServiceBusSubQueue
from azure.identity import DefaultAzureCredential

QUEUE_NAME = "inference-requests"
TOPIC_NAME = "inference-results"

def clear_screen():
    """Clear console screen (cross-platform)"""
    os.system('cls' if os.name == 'nt' else 'clear')

clear_screen()

def connect_to_servicebus() -> ServiceBusClient:
    """Establish connection to Azure Service Bus"""
    clear_screen()

    # BEGIN CONNECTION CODE SECTION

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

    # END CONNECTION CODE SECTION

    except Exception as e:
        print(f"Connection error: {e}")
        print("Check if SERVICE_BUS_FQDN is set correctly and you are authenticated.")
        sys.exit(1)

# BEGIN SEND MESSAGES CODE SECTION

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

# END SEND MESSAGES CODE SECTION

# BEGIN PROCESS MESSAGES CODE SECTION

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

# END PROCESS MESSAGES CODE SECTION

# BEGIN INSPECT DLQ CODE SECTION

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

# END INSPECT DLQ CODE SECTION

# BEGIN TOPIC MESSAGING CODE SECTION

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

# END TOPIC MESSAGING CODE SECTION

def show_menu():
    """Display the main menu"""
    clear_screen()
    print("=" * 50)
    print("    Service Bus Messaging Menu")
    print("=" * 50)
    print("1. Send messages to queue")
    print("2. Process messages from queue")
    print("3. Inspect dead-letter queue")
    print("4. Send and receive topic messages")
    print("5. Exit")
    print("=" * 50)

def main() -> None:
    clear_screen()
    client = connect_to_servicebus()

    try:
        while True:
            show_menu()
            choice = input("\nPlease select an option (1-5): ")

            if choice == "1":
                send_messages(client, QUEUE_NAME)
            elif choice == "2":
                process_messages(client, QUEUE_NAME)
            elif choice == "3":
                inspect_dead_letter_queue(client, QUEUE_NAME)
            elif choice == "4":
                topic_messaging(client, TOPIC_NAME)
            elif choice == "5":
                clear_screen()
                print("Exiting...")
                break
            else:
                print("\nInvalid option. Please select 1-5.")
                input("\nPress Enter to continue...")

    finally:
        try:
            client.close()
            print("Service Bus connection closed")
        except Exception as e:
            print(f"Error closing connection: {e}")

if __name__ == "__main__":
    main()
