import json
import logging
import os
import re
from datetime import timedelta
from typing import Any

import azure.durable_functions as df
import azure.functions as func
from azure.core.exceptions import ResourceExistsError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

APPROVAL_CONFIDENCE_THRESHOLD = 0.80
APPROVAL_TIMEOUT_SECONDS = 30
MAX_BATCH_SIZE = 20
RESULTS_CONTAINER = "workflow-results"
CONTROL_CONTAINER = "workflow-control"

app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)
logger = logging.getLogger(__name__)


def _json_response(payload: dict[str, Any], status_code: int) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
    )


def _validate_workflow_input(payload: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        return None, "The request body must be a JSON object."

    batch_id = payload.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id.strip():
        return None, "Provide a non-empty batch_id."

    documents = payload.get("documents")
    if not isinstance(documents, list) or not documents:
        return None, "Provide at least one document."
    if len(documents) > MAX_BATCH_SIZE:
        return None, f"A batch can contain at most {MAX_BATCH_SIZE} documents."

    validated_documents: list[dict[str, Any]] = []
    document_ids: set[str] = set()
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            return None, f"Document {index + 1} must be a JSON object."

        document_id = document.get("document_id")
        blob_url = document.get("blob_url")
        document_type = document.get("document_type")
        confidence = document.get("confidence")

        if not isinstance(document_id, str) or not document_id.strip():
            return None, f"Document {index + 1} must have a non-empty document_id."
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", document_id):
            message = (
                f"Document ID '{document_id}' must contain 1-60 letters, "
                "numbers, hyphens, or underscores."
            )
            return (
                None,
                message,
            )
        if document_id in document_ids:
            return None, f"Document ID '{document_id}' occurs more than once."
        if not isinstance(blob_url, str) or not blob_url.startswith(("http://", "https://")):
            return None, f"Document '{document_id}' must have an HTTP or HTTPS blob_url."
        if not isinstance(document_type, str) or not document_type.strip():
            return None, f"Document '{document_id}' must have a document_type."
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            return None, f"Document '{document_id}' must have a numeric confidence."
        if not 0 <= float(confidence) <= 1:
            return None, f"Document '{document_id}' confidence must be between 0 and 1."

        document_ids.add(document_id)
        validated_documents.append(
            {
                "document_id": document_id,
                "blob_url": blob_url,
                "document_type": document_type,
                "confidence": float(confidence),
            }
        )

    return {
        "batch_id": batch_id,
        "documents": validated_documents,
    }, None


def _get_blob_service_client() -> BlobServiceClient:
    local_storage = os.environ.get("AzureWebJobsStorage")
    if local_storage == "UseDevelopmentStorage=true":
        return BlobServiceClient.from_connection_string(local_storage)

    storage_account_name = os.environ.get("STORAGE_ACCOUNT_NAME")
    if not storage_account_name:
        raise RuntimeError(
            "STORAGE_ACCOUNT_NAME must be configured when the app is not using Azurite."
        )

    return BlobServiceClient(
        account_url=f"https://{storage_account_name}.blob.core.windows.net",
        credential=DefaultAzureCredential(),
    )


def _get_or_create_container(container_name: str):
    container = _get_blob_service_client().get_container_client(container_name)
    try:
        container.create_container()
    except ResourceExistsError:
        pass
    return container


@app.route(route="workflows", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_workflow(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
) -> func.HttpResponse:
    try:
        request_body = req.get_json()
    except ValueError:
        return _json_response({"error": "The request body must be valid JSON."}, 400)

    workflow_input, validation_error = _validate_workflow_input(request_body)
    if validation_error:
        return _json_response({"error": validation_error}, 400)

    instance_id = await client.start_new(
        "document_workflow",
        client_input=workflow_input,
    )
    return client.create_check_status_response(req, instance_id)


@app.activity_trigger(input_name="document")
def extract_text(document):
    return {
        **document,
        "text_reference": f"{document['blob_url']}.extracted.txt",
    }


@app.activity_trigger(input_name="document")
def classify_document(document):
    document_id = document["document_id"]
    retry_occurred = False
    if document_id.endswith("-fail"):
        raise RuntimeError("Simulated permanent model failure")
    if document_id.endswith("-retry"):
        marker = _get_or_create_container(CONTROL_CONTAINER).get_blob_client(
            f"retry-markers/{document['operation_id']}"
        )
        try:
            marker.upload_blob(b"failed", overwrite=False)
        except ResourceExistsError:
            retry_occurred = True
        else:
            raise RuntimeError("Simulated transient model failure")

    return {
        **document,
        "category": document["document_type"],
        "confidence": document["confidence"],
        "retry_occurred": retry_occurred,
    }


@app.activity_trigger(input_name="document")
def generate_summary(document):
    return {
        **document,
        "summary_reference": f"summaries/{document['operation_id']}.json",
    }


# BEGIN IDEMPOTENT RESULT PERSISTENCE



# END IDEMPOTENT RESULT PERSISTENCE


@app.activity_trigger(input_name="request")
def notify_approver(request):
    logger.info(
        "Approval required for document %s in orchestration %s",
        request["document_id"],
        request["instance_id"],
    )
    return {"status": "Notified"}


@app.activity_trigger(input_name="request")
def compensate_document(request):
    logger.warning(
        "Compensating operation %s because %s",
        request["operation_id"],
        request["reason"],
    )
    return {"status": "Compensated", **request}


@app.orchestration_trigger(context_name="context")
def document_orchestrator(context: df.DurableOrchestrationContext):
    # BEGIN ACTIVITY RETRY WORKFLOW



    # END ACTIVITY RETRY WORKFLOW

    # BEGIN HUMAN APPROVAL WORKFLOW



    # END HUMAN APPROVAL WORKFLOW

    return (
        yield context.call_activity(
            "persist_result",
            {
                **summarized,
                "status": final_status,
                "instance_id": context.instance_id,
            },
        )
    )


# BEGIN FAN OUT FAN IN ORCHESTRATION



# END FAN OUT FAN IN ORCHESTRATION


@app.route(route="approvals/{instance_id}", methods=["POST"])
@app.durable_client_input(client_name="client")
async def submit_approval(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
) -> func.HttpResponse:
    try:
        payload = req.get_json()
    except ValueError:
        return _json_response({"error": "The request body must be valid JSON."}, 400)

    if not isinstance(payload, dict):
        return _json_response({"error": "The request body must be a JSON object."}, 400)

    event_id = payload.get("event_id")
    decision = payload.get("decision")
    if not isinstance(event_id, str) or not event_id.strip():
        return _json_response({"error": "Provide a non-empty event_id."}, 400)
    if decision not in {"Approved", "Rejected"}:
        return _json_response(
            {"error": "The decision must be Approved or Rejected."},
            400,
        )

    # BEGIN APPROVAL EVENT DELIVERY



    # END APPROVAL EVENT DELIVERY
