import json
import os
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


def _read_status(status_url: str) -> dict[str, Any]:
    status = _request_json("GET", status_url)
    print(json.dumps(status, indent=2))
    return status


def _document_statuses(status: dict[str, Any]) -> list[str]:
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
    documents = output.get("documents")
    if not isinstance(documents, list):
        raise WorkflowTestError(
            "The completed orchestration output did not contain documents."
        )
    return [
        str(document.get("status"))
        for document in documents
        if isinstance(document, dict)
    ]


def _wait_for_completion(
    status_url: str,
    expected_statuses: list[str],
    timeout_seconds: int,
) -> None:
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
            print(json.dumps(status.get("output"), indent=2))
            return

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
    _wait_for_completion(status_url, ["Completed"], 90)


def run_timeout_test(function_app_url: str, function_key: str | None) -> None:
    _, status_url = _start_workflow(
        function_app_url,
        function_key,
        "mixed-confidence-batch.json",
    )
    print("Waiting for the two-minute approval timer to expire...")
    _wait_for_completion(
        status_url,
        ["Completed", "ApprovalTimedOut"],
        180,
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


def main() -> int:
    function_app_url = os.environ.get(
        "FUNCTION_APP_URL",
        LOCAL_FUNCTION_APP_URL,
    ).rstrip("/")
    function_key = os.environ.get("FUNCTION_KEY")
    target = "Azure" if function_key else "the local Functions host"
    session: WorkflowSession | None = None

    while True:
        _show_menu(target, function_app_url, session)
        choice = input("Please select an option (1-7): ").strip()
        print()

        try:
            if choice == "1":
                session = _start_mixed_workflow(function_app_url, function_key)
            elif choice == "2":
                if session is None:
                    raise WorkflowTestError(
                        "Start a mixed-confidence workflow first."
                    )
                _read_status(session.status_url)
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


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
        raise SystemExit(130)
