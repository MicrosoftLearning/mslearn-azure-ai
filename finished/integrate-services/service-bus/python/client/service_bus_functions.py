"""
Service Bus messaging functions for sending, receiving, and routing messages.
These functions serve as the interface between the Flask app and Azure Service Bus.
"""
import os
import json
import uuid
from azure.servicebus import ServiceBusClient, ServiceBusMessage, ServiceBusSubQueue
from azure.identity import DefaultAzureCredential

QUEUE_NAME = "inference-requests"
TOPIC_NAME = "inference-results"


def get_client():
    """Get a Service Bus client using Entra ID authentication."""
    fqdn = os.environ.get("SERVICE_BUS_FQDN")

    if not fqdn:
        raise ValueError(
            "SERVICE_BUS_FQDN environment variable must be set"
        )

    credential = DefaultAzureCredential()
    return ServiceBusClient(
        fully_qualified_namespace=fqdn,
        credential=credential
    )


# BEGIN SEND MESSAGES FUNCTION
def send_messages():
    """Send messages to the queue including one malformed message."""
    # Create a ServiceBusClient using DefaultAzureCredential
    client = get_client()
    results = []

    with client:
        # Open a sender bound to the queue
        with client.get_queue_sender(QUEUE_NAME) as sender:
            # Valid message 1 — message_id enables deduplication,
            # correlation_id links related messages for tracking,
            # and application_properties carry custom metadata for routing
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
            results.append({
                "correlation_id": msg1.correlation_id,
                "type": "valid",
                "status": "sent"
            })

            # Valid message 2 — priority is set to "high" so it matches
            # the SQL filter on the high-priority topic subscription
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
            results.append({
                "correlation_id": msg2.correlation_id,
                "type": "valid",
                "status": "sent"
            })

            # Invalid message — intentionally malformed JSON body to
            # demonstrate dead-lettering during processing
            msg3 = ServiceBusMessage(
                body="not valid json: [broken",
                content_type="application/json",
                message_id=str(uuid.uuid4()),
                correlation_id="req-doc-003",
                application_properties={"priority": "standard"}
            )
            sender.send_messages(msg3)
            results.append({
                "correlation_id": msg3.correlation_id,
                "type": "malformed",
                "status": "sent"
            })

    return results
# END SEND MESSAGES FUNCTION


# BEGIN PROCESS MESSAGES FUNCTION
def process_messages():
    """Receive and process messages from the queue using peek-lock."""
    client = get_client()
    results = []

    with client:
        # Peek-lock is the default receive mode — the message is locked
        # but stays in the queue until explicitly completed or dead-lettered.
        # max_wait_time sets how long the receiver waits for new messages.
        with client.get_queue_receiver(
            queue_name=QUEUE_NAME,
            max_wait_time=5
        ) as receiver:
            for msg in receiver:
                try:
                    payload = json.loads(str(msg))
                    # Complete removes the message from the queue
                    receiver.complete_message(msg)
                    results.append({
                        "correlation_id": msg.correlation_id,
                        "document_id": payload.get("document_id"),
                        "model": payload.get("model"),
                        "prompt": payload.get("prompt", "")[:50],
                        "status": "completed"
                    })
                except json.JSONDecodeError:
                    # Dead-letter moves the message to the dead-letter
                    # sub-queue with a reason and description for diagnostics
                    receiver.dead_letter_message(
                        msg,
                        reason="MalformedPayload",
                        error_description="Message body is not valid JSON"
                    )
                    results.append({
                        "correlation_id": msg.correlation_id,
                        "document_id": None,
                        "model": None,
                        "prompt": str(msg)[:50],
                        "status": "dead-lettered"
                    })

    return results
# END PROCESS MESSAGES FUNCTION


# BEGIN INSPECT DLQ FUNCTION
def inspect_dead_letter_queue():
    """Inspect and remove messages from the dead-letter queue."""
    client = get_client()
    results = []

    with client:
        # ServiceBusSubQueue.DEAD_LETTER targets the dead-letter sub-queue,
        # which holds messages that failed processing
        with client.get_queue_receiver(
            queue_name=QUEUE_NAME,
            sub_queue=ServiceBusSubQueue.DEAD_LETTER,
            max_wait_time=5
        ) as dlq_receiver:
            for msg in dlq_receiver:
                # Dead-lettered messages include diagnostic properties:
                # dead_letter_reason, dead_letter_error_description,
                # and delivery_count (number of delivery attempts)
                results.append({
                    "message_id": msg.message_id,
                    "correlation_id": msg.correlation_id,
                    "dead_letter_reason": msg.dead_letter_reason,
                    "error_description": msg.dead_letter_error_description,
                    "delivery_count": msg.delivery_count,
                    "body": str(msg)[:100]
                })
                # Complete removes the message from the dead-letter queue
                dlq_receiver.complete_message(msg)

    return results
# END INSPECT DLQ FUNCTION


# BEGIN TOPIC MESSAGING FUNCTION
def topic_messaging():
    """Send messages to a topic and receive from filtered subscriptions."""
    client = get_client()
    sent = []
    notifications = []
    high_priority = []

    with client:
        # get_topic_sender opens a sender bound to a topic instead of a queue.
        # Each message is broadcast to all matching subscriptions.
        with client.get_topic_sender(TOPIC_NAME) as sender:
            for i, priority in enumerate(["standard", "high", "standard", "high", "low"]):
                result = {
                    "document_id": f"doc-{i+1:03d}",
                    "status": "completed",
                    "confidence": 0.95
                }
                # The "priority" application property is what the SQL
                # filter on the high-priority subscription evaluates
                msg = ServiceBusMessage(
                    body=json.dumps(result),
                    content_type="application/json",
                    message_id=str(uuid.uuid4()),
                    application_properties={"priority": priority}
                )
                sender.send_messages(msg)
                sent.append({
                    "document_id": f"doc-{i+1:03d}",
                    "priority": priority
                })

        # Receive from the notifications subscription, which has no filter
        # and therefore receives all messages sent to the topic
        with client.get_subscription_receiver(
            topic_name=TOPIC_NAME,
            subscription_name="notifications",
            max_wait_time=5
        ) as receiver:
            for msg in receiver:
                body = json.loads(str(msg))
                # Application properties may arrive as bytes depending
                # on the AMQP encoding, so handle both str and bytes keys
                props = msg.application_properties or {}
                priority_val = props.get("priority") or props.get(b"priority", b"unknown")
                if isinstance(priority_val, bytes):
                    priority_val = priority_val.decode("utf-8")
                notifications.append({
                    "document_id": body["document_id"],
                    "priority": priority_val
                })
                receiver.complete_message(msg)

        # Receive from the high-priority subscription, which only delivers
        # messages where the SQL filter "priority = 'high'" matches
        with client.get_subscription_receiver(
            topic_name=TOPIC_NAME,
            subscription_name="high-priority",
            max_wait_time=5
        ) as receiver:
            for msg in receiver:
                body = json.loads(str(msg))
                props = msg.application_properties or {}
                priority_val = props.get("priority") or props.get(b"priority", b"unknown")
                if isinstance(priority_val, bytes):
                    priority_val = priority_val.decode("utf-8")
                high_priority.append({
                    "document_id": body["document_id"],
                    "priority": priority_val
                })
                receiver.complete_message(msg)

    return {
        "sent": sent,
        "notifications": notifications,
        "high_priority": high_priority
    }
# END TOPIC MESSAGING FUNCTION
