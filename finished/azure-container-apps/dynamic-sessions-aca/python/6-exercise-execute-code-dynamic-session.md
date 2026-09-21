In this exercise, you build the execution component of an AI document-analysis backend. The backend uploads a CSV file, runs a supplied Python payload in an isolated code interpreter session, validates the result, reuses the session to retrieve generated files, and confirms that a failed execution doesn't appear successful.

The supplied payload represents code produced by an AI orchestration layer. Using fixed code and data makes the exercise repeatable while preserving the production boundary between model output and isolated execution.

> [!NOTE]
> This exercise uses current Azure Container Apps dynamic sessions commands and preview data-plane APIs. Supported regions, command options, API versions, limits, and pricing change regularly. You can review [Dynamic sessions in Azure Container Apps](/azure/container-apps/sessions) and [Azure Container Apps billing](/azure/container-apps/billing#dynamic-sessions) for current details.

## Prepare the development environment

You need an Azure subscription, Azure CLI, and Python 3.11 or later. The signed-in account must be able to create resources and role assignments in the subscription. The exercise uses `DefaultAzureCredential` with your Azure CLI sign-in during local development.

You can prepare a Python virtual environment and install the two client libraries with the following steps:

1. You can create a working directory and virtual environment.

    ```bash
    mkdir dynamic-session-exercise
    cd dynamic-session-exercise
    python -m venv .venv
    source .venv/bin/activate
    ```

1. You can install the Azure Identity and HTTP client libraries.

    ```bash
    python -m pip install azure-identity requests
    ```

1. You can sign in to Azure and confirm the subscription you want to use.

    ```azurecli
    az login
    az account show --output table
    ```

If the displayed subscription isn't the intended subscription, you can run `az account set --subscription <SUBSCRIPTION_ID>` before creating resources.

## Create the session pool

The exercise uses a built-in Python interpreter because the analysis requires only standard Python libraries. The pool allows five concurrent sessions, removes an idle session after 300 seconds, and blocks outbound network traffic. These values keep the exercise bounded while allowing enough time to complete related operations.

You can create the required Azure resources with the following steps:

1. You can define names for the exercise resources. Replace `<UNIQUE_SUFFIX>` with a short value that makes the resource group and pool names unique.

    ```bash
    export LOCATION="westus2"
    export RESOURCE_GROUP="rg-dynamic-sessions-<UNIQUE_SUFFIX>"
    export SESSION_POOL="sp-ai-code-<UNIQUE_SUFFIX>"
    ```

1. You can create the resource group and code interpreter session pool.

    ```bash
    az group create \
        --name "$RESOURCE_GROUP" \
        --location "$LOCATION"

    az containerapp sessionpool create \
        --name "$SESSION_POOL" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --container-type PythonLTS \
        --max-sessions 5 \
        --cooldown-period 300 \
        --network-status EgressDisabled
    ```

1. You can retrieve the pool resource ID and management endpoint.

    ```bash
    export SESSION_POOL_RESOURCE_ID=$(az containerapp sessionpool show \
        --name "$SESSION_POOL" \
        --resource-group "$RESOURCE_GROUP" \
        --query id \
        --output tsv)

    export SESSION_POOL_ENDPOINT=$(az containerapp sessionpool show \
        --name "$SESSION_POOL" \
        --resource-group "$RESOURCE_GROUP" \
        --query properties.poolManagementEndpoint \
        --output tsv)

    printf '%s\n' "$SESSION_POOL_ENDPOINT"
    ```

1. You can grant your signed-in identity permission to execute code in the pool. The local Python application uses the same Azure CLI identity through `DefaultAzureCredential`.

    ```bash
    export BACKEND_PRINCIPAL_ID=$(az ad signed-in-user show \
        --query id \
        --output tsv)

    az role assignment create \
        --role "Azure ContainerApps Session Executor" \
        --assignee "$BACKEND_PRINCIPAL_ID" \
        --scope "$SESSION_POOL_RESOURCE_ID"
    ```

Azure role assignments can take a few minutes to become effective. If the application receives an authorization error during the first run, wait briefly and try again.

## Create deterministic inputs

The source data contains four months of document-processing request counts. The supplied analysis code calculates known summary values and writes an SVG chart without downloading packages or contacting an external service. The output contract makes it possible to validate the session result independently of a language model.

You can create the input files with the following steps:

1. You can create `operational-data.csv`.

    ```bash
    cat > operational-data.csv <<'EOF'
    month,requests
    January,100
    February,200
    March,300
    April,400
    EOF
    ```

1. You can create `analysis_payload.py`. In a production application, an AI orchestration layer supplies the equivalent code only after the backend applies its authorization and validation policy.

    ```python
    import csv
    import json
    from pathlib import Path

    data_path = Path("/mnt/data/operational-data.csv")
    output_path = Path("/mnt/data/trend.svg")

    with data_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))

    values = [int(row["requests"]) for row in rows]
    summary = {
        "months": len(rows),
        "total_requests": sum(values),
        "average_requests": sum(values) / len(values),
        "peak_month": rows[values.index(max(values))]["month"],
        "peak_requests": max(values),
    }

    bars = []
    for index, row in enumerate(rows):
        height = int(row["requests"])
        x = 30 + index * 80
        y = 430 - height
        bars.append(
            f'<rect x="{x}" y="{y}" width="50" height="{height}" '
            f'fill="#0078d4"><title>{row["month"]}: '
            f'{row["requests"]}</title></rect>'
        )

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="360" height="460">'
        '<rect width="100%" height="100%" fill="white"/>'
        '<text x="20" y="20">Monthly document requests</text>'
        + "".join(bars)
        + "</svg>"
    )
    output_path.write_text(svg, encoding="utf-8")

    print(json.dumps(summary))
    ```

1. You can create `failing_payload.py` to test the backend's execution-error path.

    ```python
    raise RuntimeError("Supplied analysis failed")
    ```

The expected successful summary contains four months, 1,000 total requests, an average of 250 requests, and April as the peak month with 400 requests.

## Implement the session client

The client generates its own unpredictable identifier rather than accepting one from an end user. It authenticates each operation, submits code to the `executions` endpoint, and validates both the HTTP response and execution status. The same client instance retains the identifier for file upload, execution, listing, and download operations.

You can create `session_client.py` with the following code:

```python
import json
import os
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import requests
from azure.identity import DefaultAzureCredential

API_VERSION = "2025-10-02-preview"
SESSION_API_VERSION = "2025-02-02-preview"
TOKEN_SCOPE = "https://dynamicsessions.io/.default"


class SessionRequestError(RuntimeError):
    pass


class CodeExecutionError(RuntimeError):
    pass


class DynamicSessionClient:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.identifier = str(uuid4())
        self.credential = DefaultAzureCredential()

    def _headers(self) -> dict[str, str]:
        token = self.credential.get_token(TOKEN_SCOPE).token
        return {"Authorization": f"Bearer {token}"}

    def _params(self, api_version: str = API_VERSION) -> dict[str, str]:
        return {
            "api-version": api_version,
            "identifier": self.identifier,
        }

    @staticmethod
    def _check_response(response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise SessionRequestError(
                f"Session API returned HTTP {response.status_code}: "
                f"{response.text}"
            ) from error

    def upload(self, file_path: Path) -> None:
        with file_path.open("rb") as source:
            response = requests.post(
                f"{self.endpoint}/files",
                headers=self._headers(),
                params=self._params(),
                files={
                    "file": (
                        file_path.name,
                        source,
                        "text/csv",
                    )
                },
                timeout=(5, 30),
            )
        self._check_response(response)

    def execute(self, code: str) -> dict:
        response = requests.post(
            f"{self.endpoint}/executions",
            headers={
                **self._headers(),
                "Content-Type": "application/json",
            },
            params=self._params(),
            json={
                "properties": {
                    "codeInputType": "inline",
                    "executionType": "synchronous",
                    "code": code,
                }
            },
            timeout=(5, 60),
        )
        self._check_response(response)
        properties = response.json().get("properties", {})
        if properties.get("status") != "Success":
            raise CodeExecutionError(
                properties.get("stderr") or "Code execution failed"
            )
        return properties

    def list_files(self) -> list[str]:
        response = requests.get(
            f"{self.endpoint}/files",
            headers=self._headers(),
            params=self._params(),
            timeout=(5, 15),
        )
        self._check_response(response)
        return [
            item["properties"]["filename"]
            for item in response.json().get("value", [])
        ]

    def download(self, file_name: str, destination: Path) -> None:
        safe_name = quote(file_name, safe="")
        response = requests.get(
            f"{self.endpoint}/files/{safe_name}/content",
            headers=self._headers(),
            params=self._params(),
            timeout=(5, 30),
        )
        self._check_response(response)
        destination.write_bytes(response.content)

    def delete(self) -> None:
        response = requests.delete(
            f"{self.endpoint}/session",
            headers=self._headers(),
            params=self._params(SESSION_API_VERSION),
            timeout=(5, 15),
        )
        if response.status_code != 204:
            self._check_response(response)


def main() -> None:
    endpoint = os.environ.get("SESSION_POOL_ENDPOINT")
    if not endpoint:
        raise RuntimeError("SESSION_POOL_ENDPOINT isn't set")

    client = DynamicSessionClient(endpoint)
    source_path = Path("operational-data.csv")
    payload = Path("analysis_payload.py").read_text(encoding="utf-8")
    session_started = False

    try:
        client.upload(source_path)
        session_started = True
        result = client.execute(payload)
        summary = json.loads(result["stdout"])

        expected = {
            "months": 4,
            "total_requests": 1000,
            "average_requests": 250.0,
            "peak_month": "April",
            "peak_requests": 400,
        }
        if summary != expected:
            raise RuntimeError(
                f"Unexpected analysis result: {summary}"
            )

        files = client.list_files()
        if "operational-data.csv" not in files or "trend.svg" not in files:
            raise RuntimeError(f"Expected session files aren't present: {files}")

        client.download("trend.svg", Path("trend.svg"))
        print(f"Session {client.identifier} returned the expected summary.")
        print("Downloaded trend.svg from the reused session.")

        failing_code = Path("failing_payload.py").read_text(encoding="utf-8")
        try:
            client.execute(failing_code)
        except CodeExecutionError as error:
            print(f"Handled the expected execution error: {error}")
        else:
            raise RuntimeError("The failing payload appeared successful")
    finally:
        if session_started:
            client.delete()
            print("Deleted the dynamic session.")


if __name__ == "__main__":
    main()
```

The `finally` block attempts session deletion even when validation fails. The code reports an error if explicit cleanup fails rather than printing a success message that doesn't reflect the API result.

## Execute and validate the workflow

The completed client exercises one session from allocation through deletion. A successful run proves that the same identifier retains the uploaded CSV long enough for code execution and file retrieval. It also proves that the backend recognizes a Python exception as an execution failure.

You can run and validate the workflow with the following steps:

1. You can run the Python client from the shell where `SESSION_POOL_ENDPOINT` is defined and the virtual environment is active.

    ```bash
    python session_client.py
    ```

1. You can confirm that the output reports the expected summary, downloaded file, handled execution error, and deleted session. The exact UUID and error detail can vary, but the result resembles the following output.

    ```text
    Session 42b14c34-86de-4b70-89c3-2d57cc6d99aa returned the expected summary.
    Downloaded trend.svg from the reused session.
    Handled the expected execution error: RuntimeError: Supplied analysis failed
    Deleted the dynamic session.
    ```

1. You can open `trend.svg` to confirm that the generated artifact contains four bars with increasing heights.

If the first request returns an authorization error, allow time for the role assignment to propagate and rerun the client. If execution returns another failure, inspect the structured HTTP response or `stderr` value without exposing the bearer token.

## Clean up Azure resources

The Python client deletes its allocated session, but the session pool and resource group continue to exist. You can remove the exercise resources to prevent ongoing charges after you finish validating the workflow. Resource-group deletion removes the session pool and its associated exercise resources.

You can start the cleanup with the following command:

```bash
az group delete \
    --name "$RESOURCE_GROUP" \
    --yes \
    --no-wait
```

The command returns before Azure finishes the asynchronous deletion. You can check the resource group later if you need to confirm that cleanup completed.
