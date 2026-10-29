"""Publish stored investigation updates to observers through Azure Web PubSub."""

import logging
import os
import time
from collections.abc import Callable, Iterable

from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential
from azure.messaging.webpubsubservice import WebPubSubServiceClient

from operation_store import Event, EventType, Operation, OperationStore
from simulator import simulate

logger = logging.getLogger(__name__)
BATCH_FRAGMENTS = 3
PUBLISH_ATTEMPTS = 3
OBSERVERS = {
    "oncall": "On-call developer",
    "database": "Database specialist",
}


def get_client(credential: DefaultAzureCredential) -> WebPubSubServiceClient:
    """Return the configured service client using Microsoft Entra authentication."""
    return WebPubSubServiceClient(
        endpoint=os.environ["WEBPUBSUB_ENDPOINT"],
        hub=os.environ["WEBPUBSUB_HUB"],
        credential=credential,
    )


def group_name(operation_id: str) -> str:
    """Return the Web PubSub group dedicated to one investigation."""
    return f"investigation-{operation_id}"


def authorize(operation: Operation, observer: str, *, start: bool = False) -> None:
    """Check demo observer access and restrict starting to the investigation owner."""
    if observer not in operation.allowed or (start and observer != operation.owner):
        raise PermissionError("This observer cannot access this investigation.")


# BEGIN GENERATE CONNECTION DETAILS



# END GENERATE CONNECTION DETAILS


# BEGIN RECORD EVENT



# END RECORD EVENT


# BEGIN PUBLISH EVENT



# END PUBLISH EVENT


# BEGIN RUN INVESTIGATION



# END RUN INVESTIGATION
