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



# END PUBLISH EVENTS FUNCTION


# BEGIN CHECK DELIVERY FUNCTION



# END CHECK DELIVERY FUNCTION


# BEGIN INSPECT AND REJECT FUNCTION



# END INSPECT AND REJECT FUNCTION
