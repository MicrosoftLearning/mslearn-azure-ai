import logging
from collections.abc import Callable, Iterable

from azure.core.exceptions import AzureError
from azure.messaging.webpubsubservice import WebPubSubServiceClient

from notifications import publish_event, record_event
from operation_store import EventType, OperationStore
from simulator import simulate

logger = logging.getLogger(__name__)
BATCH_FRAGMENTS = 3


# BEGIN RUN INVESTIGATION
def run_investigation(
    store: OperationStore,
    client: WebPubSubServiceClient,
    operation_id: str,
    fragments: Callable[[], Iterable[tuple[str, str, int]]] = simulate,
) -> None:
    def emit(event_type: EventType, payload: dict[str, object]) -> None:
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
            if len(pending) == BATCH_FRAGMENTS:
                emit("findings", {"text": "".join(pending)})
                pending.clear()
        if pending:
            emit("findings", {"text": "".join(pending)})
        emit("completed", {"result_ref": f"/api/operations/{operation_id}/result"})
    except (AzureError, ValueError, RuntimeError) as exc:
        logger.exception("Investigation %s failed (%s).", operation_id, type(exc).__name__)
        operation, _ = store.load(operation_id)
        if operation.status == "running":
            emit("failed", {"error": "The investigation failed. Check the backend terminal for details."})
# END RUN INVESTIGATION
