import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = PROJECT_ROOT / "samples"
LOCAL_FUNCTION_APP_URL = "http://localhost:7071"
TERMINAL_FAILURE_STATES = {"Canceled", "Failed", "Terminated"}


class WorkflowTestError(RuntimeError):
    pass


@dataclass
class WorkflowSession:
    instance_id: str
    status_url: str
    scenario: str


def _request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise WorkflowTestError(
            f"{method} {url} returned HTTP {exc.code}: {error_body}"
        ) from exc
    except URLError as exc:
        raise WorkflowTestError(f"{method} {url} failed: {exc.reason}") from exc

    if not response_body:
        return {}
    try:
        result = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise WorkflowTestError(
            f"{method} {url} returned invalid JSON: {response_body}"
        ) from exc
    if not isinstance(result, dict):
        raise WorkflowTestError(f"{method} {url} did not return a JSON object.")
    return result


def _with_function_key(url: str, function_key: str | None) -> str:
    if not function_key:
        return url

    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if not any(name == "code" for name, _ in query):
        query.append(("code", function_key))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _load_sample(filename: str) -> dict[str, Any]:
    sample_path = SAMPLES_DIR / filename
    try:
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowTestError(f"Could not read {sample_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise WorkflowTestError(f"{sample_path} must contain a JSON object.")
    return payload


def _start_workflow(
    function_app_url: str,
    function_key: str | None,
    sample_filename: str,
) -> tuple[str, str]:
    workflow_url = _with_function_key(
        f"{function_app_url}/api/workflows",
        function_key,
    )
    response = _request_json("POST", workflow_url, _load_sample(sample_filename))
    instance_id = response.get("id")
    status_url = response.get("statusQueryGetUri")
    if not isinstance(instance_id, str) or not isinstance(status_url, str):
        raise WorkflowTestError(
            "The workflow start response did not contain id and statusQueryGetUri."
        )
    print(f"Started orchestration: {instance_id}")
    return instance_id, status_url


def _instance_status_url(status_url: str, instance_id: str) -> str:
    parts = urlsplit(status_url)
    path_segments = parts.path.rstrip("/").split("/")
    path_segments[-1] = instance_id
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            "/".join(path_segments),
            parts.query,
            parts.fragment,
        )
    )


def _read_status(session: WorkflowSession) -> dict[str, Any]:
    status = _request_json("GET", session.status_url)
    _print_status_summary(status)
    if status.get("runtimeStatus") != "Completed" and session.scenario == "mixed":
        _print_active_document_statuses(session)
    return status


def _workflow_output(status: dict[str, Any]) -> dict[str, Any]:
    output = status.get("output")
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except json.JSONDecodeError as exc:
            raise WorkflowTestError(
                "The completed orchestration output was invalid JSON."
            ) from exc
    if not isinstance(output, dict):
        raise WorkflowTestError(
            "The completed orchestration did not return an output object."
        )
    return output


def _workflow_documents(status: dict[str, Any]) -> list[dict[str, Any]]:
    output = _workflow_output(status)
    documents = output.get("documents")
    if not isinstance(documents, list):
        raise WorkflowTestError(
            "The completed orchestration output did not contain documents."
        )
    return [document for document in documents if isinstance(document, dict)]


def _document_statuses(status: dict[str, Any]) -> list[str]:
    return [
        str(document.get("status"))
        for document in _workflow_documents(status)
    ]


def _print_status_summary(status: dict[str, Any]) -> None:
    print(f"Instance ID: {status.get('instanceId', 'Unknown')}")
    print(f"Runtime status: {status.get('runtimeStatus', 'Unknown')}")

    created_time = status.get("createdTime")
    if created_time:
        print(f"Created: {created_time}")
    last_updated_time = status.get("lastUpdatedTime")
    if last_updated_time:
        print(f"Last updated: {last_updated_time}")

    custom_status = status.get("customStatus")
    if custom_status is not None:
        print(f"Custom status: {custom_status}")

    if status.get("runtimeStatus") != "Completed":
        return

    output = _workflow_output(status)
    batch_id = output.get("batch_id")
    if batch_id:
        print(f"Batch ID: {batch_id}")

    documents = _workflow_documents(status)
    if not documents:
        print("Documents: None")
        return

    print("Documents:")
    for document in documents:
        details = [
            f"id={document.get('document_id', 'Unknown')}",
            f"status={document.get('status', 'Unknown')}",
        ]
        for field in ("category", "confidence", "retry_occurred", "write_status"):
            value = document.get(field)
            if value is not None:
                details.append(f"{field}={value}")
        print(f"  - {', '.join(details)}")


def _print_active_document_statuses(session: WorkflowSession) -> None:
    print("Documents:")
    for document_id in ("claim-001", "claim-002"):
        child_instance_id = f"{session.instance_id}-{document_id}"
        child_status = _request_json(
            "GET",
            _instance_status_url(session.status_url, child_instance_id),
        )
        runtime_status = child_status.get("runtimeStatus", "Unknown")
        result_status = "Pending"
        if runtime_status == "Completed":
            output = child_status.get("output")
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except json.JSONDecodeError:
                    output = None
            if isinstance(output, dict):
                result_status = str(output.get("status", "Completed"))
            else:
                result_status = "Completed"
        elif runtime_status in TERMINAL_FAILURE_STATES:
            result_status = str(runtime_status)

        print(
            f"  - id={document_id}, orchestration={runtime_status}, "
            f"status={result_status}"
        )


def _wait_for_completion(
    status_url: str,
    expected_statuses: list[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_runtime_status = ""

    while time.monotonic() < deadline:
        status = _request_json("GET", status_url)
        runtime_status = status.get("runtimeStatus")
        if runtime_status != last_runtime_status:
            print(f"Runtime status: {runtime_status}")
            last_runtime_status = str(runtime_status)

        if runtime_status == "Completed":
            actual_statuses = _document_statuses(status)
            if actual_statuses != expected_statuses:
                raise WorkflowTestError(
                    f"Expected document statuses {expected_statuses}, "
                    f"but received {actual_statuses}."
                )
            _print_status_summary(status)
            return status

        if runtime_status in TERMINAL_FAILURE_STATES:
            raise WorkflowTestError(
                f"The orchestration ended with status {runtime_status}: "
                f"{status.get('output')}"
            )
        time.sleep(2)

    raise WorkflowTestError(
        f"The orchestration did not complete within {timeout_seconds} seconds."
    )


def _start_mixed_workflow(
    function_app_url: str,
    function_key: str | None,
) -> WorkflowSession:
    instance_id, status_url = _start_workflow(
        function_app_url,
        function_key,
        "mixed-confidence-batch.json",
    )
    child_instance_id = f"{instance_id}-claim-002"
    print(f"Low-confidence child orchestration: {child_instance_id}")
    print("Use the menu to inspect the workflow, then approve or reject it.")
    return WorkflowSession(instance_id, status_url, "mixed")


def _submit_decision(
    session: WorkflowSession | None,
    function_app_url: str,
    function_key: str | None,
    decision: str,
) -> None:
    if session is None or session.scenario != "mixed":
        raise WorkflowTestError(
            "Start a mixed-confidence workflow before submitting a decision."
        )
    approval_url = _with_function_key(
        f"{function_app_url}/api/approvals/{session.instance_id}-claim-002",
        function_key,
    )
    approval = _request_json(
        "POST",
        approval_url,
        {
            "event_id": f"workflow-test-{decision.lower()}",
            "decision": decision,
        },
    )
    if approval.get("status") != "Accepted":
        raise WorkflowTestError(f"The decision was not accepted: {approval}")
    print(f"{decision} decision accepted for the low-confidence document.")


def run_retry_test(function_app_url: str, function_key: str | None) -> None:
    _, status_url = _start_workflow(
        function_app_url,
        function_key,
        "retry-batch.json",
    )
    status = _wait_for_completion(status_url, ["Completed"], 90)
    documents = _workflow_documents(status)
    retry_document = next(
        (
            document
            for document in documents
            if document.get("document_id") == "claim-003-retry"
        ),
        None,
    )
    if retry_document is None:
        raise WorkflowTestError(
            "The retry result did not contain document claim-003-retry."
        )
    if retry_document.get("retry_occurred") is not True:
        raise WorkflowTestError(
            "Document claim-003-retry completed without evidence of a retry."
        )
    print(
        "Verified claim-003-retry recovered from one simulated transient "
        "failure."
    )


def run_timeout_test(function_app_url: str, function_key: str | None) -> None:
    _, status_url = _start_workflow(
        function_app_url,
        function_key,
        "mixed-confidence-batch.json",
    )
    print("Waiting approximately 30 seconds for the approval timer to expire...")
    _wait_for_completion(
        status_url,
        ["Completed", "ApprovalTimedOut"],
        60,
    )


def _show_menu(
    target: str,
    function_app_url: str,
    session: WorkflowSession | None,
) -> None:
    print()
    print("===========================================================")
    print("    Durable Functions Workflow Tests")
    print("===========================================================")
    print(f"Target: {target} ({function_app_url})")
    active_id = session.instance_id if session else "None"
    print(f"Active orchestration: {active_id}")
    print("===========================================================")
    print("1. Start a mixed-confidence workflow")
    print("2. Check the active workflow status")
    print("3. Approve the low-confidence document")
    print("4. Reject the low-confidence document")
    print("5. Run the retry scenario")
    print("6. Run the timeout scenario")
    print("7. Exit")
    print("===========================================================")


def _clear_screen() -> None:
    clear_command = ["cmd", "/c", "cls"] if os.name == "nt" else ["clear"]
    result = subprocess.run(clear_command, check=False)
    if result.returncode != 0:
        print("\033[2J\033[H", end="", flush=True)


def _pause_for_menu() -> None:
    input("\nPress Enter to return to the menu...")


def main() -> int:
    function_app_url = os.environ.get(
        "FUNCTION_APP_URL",
        LOCAL_FUNCTION_APP_URL,
    ).rstrip("/")
    function_key = os.environ.get("FUNCTION_KEY")
    target = "Azure" if function_key else "the local Functions host"
    session: WorkflowSession | None = None

    while True:
        _clear_screen()
        _show_menu(target, function_app_url, session)
        choice = input("Please select an option (1-7): ").strip()
        _clear_screen()

        try:
            if choice == "1":
                session = _start_mixed_workflow(function_app_url, function_key)
            elif choice == "2":
                if session is None:
                    raise WorkflowTestError(
                        "Start a mixed-confidence workflow first."
                    )
                _read_status(session)
            elif choice == "3":
                _submit_decision(
                    session,
                    function_app_url,
                    function_key,
                    "Approved",
                )
            elif choice == "4":
                _submit_decision(
                    session,
                    function_app_url,
                    function_key,
                    "Rejected",
                )
            elif choice == "5":
                run_retry_test(function_app_url, function_key)
                print("PASS: retry scenario")
            elif choice == "6":
                run_timeout_test(function_app_url, function_key)
                print("PASS: timeout scenario")
            elif choice == "7":
                print("Exiting...")
                return 0
            else:
                print("Invalid option. Please select 1-7.")
        except WorkflowTestError as exc:
            print(f"Error: {exc}", file=sys.stderr)

        _pause_for_menu()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
        raise SystemExit(130)
