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
def connection_details(
    client: WebPubSubServiceClient, operation: Operation, observer: str,
) -> dict[str, str]:
    """Issue a short-lived connection URL and the authorized investigation group."""
    authorize(operation, observer)
    group = group_name(operation.operation_id)
    # Scope group membership permission to this investigation; do not grant send permission.
    token = client.get_client_access_token(
        user_id=observer,
        roles=[f"webpubsub.joinLeaveGroup.{group}"],
        minutes_to_expire=5,
    )
    return {"url": token["url"], "group": group}
# END GENERATE CONNECTION DETAILS


# BEGIN RECORD EVENT
def record_event(
    store: OperationStore, operation_id: str,
    event_type: EventType, payload: dict[str, object],
) -> Event:
    """Persist an investigation update and return its sequenced event envelope."""
    return store.record(operation_id, event_type, payload)
# END RECORD EVENT


# BEGIN PUBLISH EVENT
def publish_event(
    client: WebPubSubServiceClient, store: OperationStore, event: Event,
) -> None:
    """Deliver a stored event with bounded retries and track live-delivery problems."""
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
            # Keep processing: observers can recover stored findings after reconnecting.
            store.delivery_problem(
                event["operation_id"],
                "Live delivery failed. Findings remain stored; reconnect this view to recover them.",
            )
            return
        store.delivery_problem(event["operation_id"], None)
        return
# END PUBLISH EVENT


# BEGIN RUN INVESTIGATION
def run_investigation(
    store: OperationStore,
    client: WebPubSubServiceClient,
    operation_id: str,
    fragments: Callable[[], Iterable[tuple[str, str, int]]] = simulate,
) -> None:
    """Batch simulated findings, store each update, and notify connected observers."""
    def emit(event_type: EventType, payload: dict[str, object]) -> None:
        # Persist first so a missed live message does not lose investigation state.
        event = record_event(store, operation_id, event_type, payload)
        publish_event(client, store, event)

    pending: list[str] = []
    current_stage = ""
    try:
        for stage, fragment, progress in fragments():
            if stage != current_stage:
                emit("progress", {"stage": stage, "progress": progress})
                current_stage = stage
            pending.append(fragment)
            # Batch small fragments to reduce live-message traffic.
            if len(pending) == BATCH_FRAGMENTS:
                emit("findings", {"text": "".join(pending)})
                pending.clear()
        if pending:
            emit("findings", {"text": "".join(pending)})
        # Publish a reference to the stored result rather than resending all findings.
        emit("completed", {"result_ref": f"/api/operations/{operation_id}/result"})
    except (AzureError, ValueError, RuntimeError) as exc:
        logger.exception("Investigation %s failed (%s).", operation_id, type(exc).__name__)
        operation, _ = store.load(operation_id)
        # Do not replace a terminal status if the failure occurred after completion.
        if operation.status == "running":
            emit("failed", {"error": "The investigation failed. Check the backend terminal for details."})
# END RUN INVESTIGATION
