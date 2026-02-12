"""
Event Grid functions for publishing content moderation events and reading
filtered delivery results from Service Bus queues.
"""
import os
import json
import uuid
from datetime import datetime, timezone
from azure.eventgrid import EventGridPublisherClient
from azure.core.messaging import CloudEvent
from azure.servicebus import ServiceBusClient
from azure.identity import DefaultAzureCredential

FLAGGED_QUEUE = "flagged-content"
APPROVED_QUEUE = "approved-content"
ALL_EVENTS_QUEUE = "all-events"


def get_eventgrid_client():
    """Get an Event Grid publisher client using Entra ID authentication."""
    endpoint = os.environ.get("EVENTGRID_TOPIC_ENDPOINT")

    if not endpoint:
        raise ValueError(
            "EVENTGRID_TOPIC_ENDPOINT environment variable must be set"
        )

    credential = DefaultAzureCredential()
    return EventGridPublisherClient(endpoint, credential)


def get_servicebus_client():
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


# BEGIN PUBLISH EVENTS FUNCTION
def publish_moderation_events():
    """Publish content moderation events to the Event Grid topic."""
    client = get_eventgrid_client()
    results = []

    # Build five CloudEvent objects representing different moderation outcomes.
    # Each event has a type, source, subject, and data payload that mirrors
    # a realistic AI content moderation pipeline.
    events = [
        CloudEvent(
            type="com.contoso.ai.ContentFlagged",
            source="/services/content-moderation",
            subject="/content/images/img-4821",
            data={
                "contentId": "img-4821",
                "contentType": "image",
                "modelName": "vision-moderator-v3",
                "modelVersion": "3.2.1",
                "confidence": 0.97,
                "category": "violence",
                "severity": "high",
                "reviewRequired": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            id=str(uuid.uuid4())
        ),
        CloudEvent(
            type="com.contoso.ai.ContentApproved",
            source="/services/content-moderation",
            subject="/content/text/doc-1137",
            data={
                "contentId": "doc-1137",
                "contentType": "text",
                "modelName": "text-moderator-v2",
                "modelVersion": "2.4.0",
                "confidence": 0.99,
                "category": "safe",
                "severity": "none",
                "reviewRequired": False,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            id=str(uuid.uuid4())
        ),
        CloudEvent(
            type="com.contoso.ai.ContentFlagged",
            source="/services/content-moderation",
            subject="/content/text/doc-2054",
            data={
                "contentId": "doc-2054",
                "contentType": "text",
                "modelName": "text-moderator-v2",
                "modelVersion": "2.4.0",
                "confidence": 0.88,
                "category": "hate-speech",
                "severity": "medium",
                "reviewRequired": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            id=str(uuid.uuid4())
        ),
        CloudEvent(
            type="com.contoso.ai.ContentApproved",
            source="/services/content-moderation",
            subject="/content/images/img-7733",
            data={
                "contentId": "img-7733",
                "contentType": "image",
                "modelName": "vision-moderator-v3",
                "modelVersion": "3.2.1",
                "confidence": 0.95,
                "category": "safe",
                "severity": "none",
                "reviewRequired": False,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            id=str(uuid.uuid4())
        ),
        CloudEvent(
            type="com.contoso.ai.ReviewEscalated",
            source="/services/content-moderation",
            subject="/content/text/doc-3301",
            data={
                "contentId": "doc-3301",
                "contentType": "text",
                "modelName": "text-moderator-v2",
                "modelVersion": "2.4.0",
                "confidence": 0.52,
                "category": "self-harm",
                "severity": "high",
                "reviewRequired": True,
                "escalationReason": "Low confidence requires human review",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            id=str(uuid.uuid4())
        ),
    ]

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
# END PUBLISH EVENTS FUNCTION


# BEGIN CHECK DELIVERY FUNCTION
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
# END CHECK DELIVERY FUNCTION


# BEGIN INSPECT EVENT FUNCTION
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
# END INSPECT EVENT FUNCTION
