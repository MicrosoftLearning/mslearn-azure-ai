"""
Event Grid functions for publishing content moderation events and receiving
events through pull delivery with Event Grid Namespace subscriptions.
"""
import os
import json
import uuid
from datetime import datetime, timezone
from azure.eventgrid import EventGridPublisherClient, EventGridConsumerClient
from azure.core.messaging import CloudEvent
from azure.identity import DefaultAzureCredential

SUB_FLAGGED = "sub-flagged"
SUB_APPROVED = "sub-approved"
SUB_ALL = "sub-all-events"


def get_publisher_client():
    """Get an Event Grid publisher client for the namespace topic."""
    endpoint = os.environ.get("EVENTGRID_ENDPOINT")
    topic_name = os.environ.get("EVENTGRID_TOPIC_NAME")

    if not endpoint:
        raise ValueError(
            "EVENTGRID_ENDPOINT environment variable must be set"
        )
    if not topic_name:
        raise ValueError(
            "EVENTGRID_TOPIC_NAME environment variable must be set"
        )

    credential = DefaultAzureCredential()
    return EventGridPublisherClient(
        endpoint, credential, namespace_topic=topic_name
    )


def get_consumer_client(subscription_name):
    """Get an Event Grid consumer client for an event subscription."""
    endpoint = os.environ.get("EVENTGRID_ENDPOINT")
    topic_name = os.environ.get("EVENTGRID_TOPIC_NAME")

    if not endpoint:
        raise ValueError(
            "EVENTGRID_ENDPOINT environment variable must be set"
        )
    if not topic_name:
        raise ValueError(
            "EVENTGRID_TOPIC_NAME environment variable must be set"
        )

    credential = DefaultAzureCredential()
    return EventGridConsumerClient(
        endpoint, credential,
        namespace_topic=topic_name,
        subscription=subscription_name
    )


# BEGIN PUBLISH EVENTS FUNCTION
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
# END PUBLISH EVENTS FUNCTION


# BEGIN CHECK DELIVERY FUNCTION
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
    details = consumer.receive(max_events=10, max_wait_time=10)
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
    details = consumer.receive(max_events=10, max_wait_time=10)
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
    details = consumer.receive(max_events=10, max_wait_time=10)
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
# END CHECK DELIVERY FUNCTION


# BEGIN INSPECT AND REJECT FUNCTION
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
# END INSPECT AND REJECT FUNCTION
