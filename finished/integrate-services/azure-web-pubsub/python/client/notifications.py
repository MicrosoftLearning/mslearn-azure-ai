import logging
import time

from azure.core.exceptions import AzureError
from azure.messaging.webpubsubservice import WebPubSubServiceClient

from operation_access import group_name
from operation_store import Event, EventType, OperationStore

logger = logging.getLogger(__name__)
PUBLISH_ATTEMPTS = 3


# BEGIN RECORD EVENT
def record_event(
    store: OperationStore, operation_id: str,
    event_type: EventType, payload: dict[str, object],
) -> Event:
    return store.record(operation_id, event_type, payload)
# END RECORD EVENT


# BEGIN PUBLISH EVENT
def publish_event(
    client: WebPubSubServiceClient, store: OperationStore, event: Event,
) -> None:
    for attempt in range(PUBLISH_ATTEMPTS):
        try:
            client.send_to_group(
                group=group_name(event["operation_id"]),
                message=event, content_type="application/json",
            )
        except AzureError as exc:
            logger.warning(
                "Delivery attempt %s failed for event %s (%s).",
                attempt + 1, event["event_id"], type(exc).__name__,
            )
            if attempt + 1 < PUBLISH_ATTEMPTS:
                time.sleep(0.5 * (attempt + 1))
                continue
            store.delivery_problem(
                event["operation_id"],
                "Live delivery failed. Findings remain stored; reconnect or refresh the snapshot.",
            )
            return
        store.delivery_problem(event["operation_id"], None)
        return
# END PUBLISH EVENT
