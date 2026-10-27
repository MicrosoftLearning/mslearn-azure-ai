import json
import re
import uuid
from dataclasses import asdict, dataclass, replace
from typing import Literal, TypedDict

from azure.core import MatchConditions
from azure.core.exceptions import ResourceModifiedError
from azure.storage.blob import ContainerClient, ContentSettings

Status = Literal["pending", "running", "completed", "failed", "interrupted"]
EventType = Literal["progress", "findings", "completed", "failed"]
TERMINAL = {"completed", "failed", "interrupted"}


class Event(TypedDict):
    schema_version: int
    operation_id: str
    event_id: str
    sequence: int
    type: EventType
    payload: dict[str, object]


@dataclass(frozen=True)
class Operation:
    operation_id: str
    owner: str
    allowed: list[str]
    sequence: int = 0
    text: str = ""
    progress: int = 0
    stage: str = "Ready to start"
    status: Status = "pending"
    worker_starts: int = 0
    worker_id: str | None = None
    result_ref: str | None = None
    delivery_error: str | None = None
    error: str | None = None


def validate_id(operation_id: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{32}", operation_id):
        raise ValueError("Invalid investigation ID.")
    return operation_id


class OperationStore:
    def __init__(self, container: ContainerClient):
        self.container = container
        self.worker_id = uuid.uuid4().hex

    def _blob(self, operation_id: str):
        return self.container.get_blob_client(f"operations/{validate_id(operation_id)}.json")

    def _save(self, operation: Operation, etag: str | None = None) -> None:
        options = {
            "content_settings": ContentSettings(content_type="application/json"),
        }
        data = json.dumps(asdict(operation))
        if etag is None:
            self._blob(operation.operation_id).upload_blob(data, overwrite=False, **options)
        else:
            self._blob(operation.operation_id).upload_blob(
                data, overwrite=True, etag=etag,
                match_condition=MatchConditions.IfNotModified, **options,
            )

    def create(self, owner: str, allowed: list[str]) -> Operation:
        operation = Operation(uuid.uuid4().hex, owner, allowed)
        self._save(operation)
        return operation

    def load(self, operation_id: str) -> tuple[Operation, str]:
        download = self._blob(operation_id).download_blob()
        operation = Operation(**json.loads(download.readall()))
        if operation.operation_id != operation_id:
            raise ValueError("Stored investigation ID does not match the requested ID.")
        return operation, download.properties.etag

    def claim(self, operation_id: str) -> tuple[Operation, bool]:
        operation, etag = self.load(operation_id)
        if operation.status != "pending":
            return operation, False
        claimed = replace(
            operation, status="running", worker_id=self.worker_id,
            worker_starts=operation.worker_starts + 1,
        )
        try:
            self._save(claimed, etag)
        except ResourceModifiedError:
            return self.load(operation_id)[0], False
        return claimed, True

    def record(
        self, operation_id: str, event_type: EventType,
        payload: dict[str, object],
    ) -> Event:
        operation, etag = self.load(operation_id)
        if operation.status != "running" or operation.worker_id != self.worker_id:
            raise ValueError("Only the active worker can update this investigation.")
        sequence = operation.sequence + 1
        changes: dict[str, object] = {"sequence": sequence}
        if event_type == "findings":
            text = payload["text"]
            if not isinstance(text, str) or not text:
                raise ValueError("Findings must contain nonempty text.")
            changes["text"] = operation.text + text
        elif event_type == "progress":
            progress, stage = payload["progress"], payload["stage"]
            if (
                not isinstance(progress, int) or isinstance(progress, bool)
                or not operation.progress <= progress < 100
                or not isinstance(stage, str)
            ):
                raise ValueError("Invalid progress update.")
            changes.update(progress=progress, stage=stage)
        elif event_type == "completed":
            reference = f"/api/operations/{operation_id}/result"
            if payload.get("result_ref") != reference:
                raise ValueError("Completion must reference this investigation's result.")
            result = {"operation_id": operation_id, "text": operation.text}
            self.container.get_blob_client(f"results/{operation_id}.json").upload_blob(
                json.dumps(result), overwrite=False,
                content_settings=ContentSettings(content_type="application/json"),
            )
            changes.update(status="completed", progress=100, stage="Complete", result_ref=reference)
        elif event_type == "failed":
            changes.update(status="failed", stage="Investigation failed", error=payload["error"])
        self._save(replace(operation, **changes), etag)
        return {
            "schema_version": 1, "operation_id": operation_id,
            "event_id": f"{operation_id}:{sequence}", "sequence": sequence,
            "type": event_type, "payload": payload,
        }

    def delivery_problem(self, operation_id: str, message: str | None) -> None:
        for attempt in range(3):
            operation, etag = self.load(operation_id)
            try:
                self._save(replace(operation, delivery_error=message), etag)
                return
            except ResourceModifiedError:
                if attempt == 2:
                    raise

    def result(self, operation_id: str) -> dict[str, str]:
        validate_id(operation_id)
        data = self.container.get_blob_client(f"results/{operation_id}.json").download_blob()
        return json.loads(data.readall())

    def interrupt_abandoned(self) -> None:
        for blob in self.container.list_blobs(name_starts_with="operations/"):
            operation_id = blob.name.removeprefix("operations/").removesuffix(".json")
            operation, etag = self.load(operation_id)
            if operation.status == "running":
                self._save(replace(
                    operation, status="interrupted", stage="Backend stopped",
                    error="The previous backend stopped. Create a new investigation to run again.",
                ), etag)
