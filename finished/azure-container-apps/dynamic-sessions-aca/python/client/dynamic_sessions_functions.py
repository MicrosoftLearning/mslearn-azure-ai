"""Client functions for Azure Container Apps dynamic sessions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import requests
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

# Dynamic Sessions has no stable data-plane API version yet. Use the newest
# version published in the official Azure REST API specification.
API_VERSION = "2025-10-02-preview"
TOKEN_SCOPE = "https://dynamicsessions.io/.default"


class DynamicSessionError(RuntimeError):
    """Base error for dynamic session operations."""


class DynamicSessionRequestError(DynamicSessionError):
    """Raised when the dynamic sessions API rejects a request."""


class CodeExecutionError(DynamicSessionError):
    """Raised when code finishes with a failed execution status."""


# BEGIN CREATE SESSION CLIENT CODE SECTION
def get_session_client() -> "DynamicSessionClient":
    """Create a client from the session pool endpoint in the environment."""
    endpoint = os.environ.get("SESSION_POOL_ENDPOINT", "").strip()
    if not endpoint:
        raise ValueError("SESSION_POOL_ENDPOINT environment variable must be set")

    # The backend creates the identifier instead of accepting one from the
    # browser. Reusing this unpredictable value keeps related operations in the
    # same session without letting a user target another session.
    identifier = str(uuid4())

    # DefaultAzureCredential uses developer credentials locally and can use a
    # managed identity after the application is hosted in Azure.
    credential = DefaultAzureCredential()
    return DynamicSessionClient(
        endpoint,
        credential=credential,
        identifier=identifier,
    )


# END CREATE SESSION CLIENT CODE SECTION


class DynamicSessionClient:
    """Call a code interpreter session while retaining one secure identifier."""

    def __init__(
        self,
        endpoint: str,
        *,
        credential: TokenCredential | None = None,
        http_session: requests.Session | None = None,
        identifier: str | None = None,
    ) -> None:
        if not endpoint.startswith("https://"):
            raise ValueError("The session pool endpoint must use HTTPS")

        self.endpoint = endpoint.rstrip("/")
        self.identifier = identifier or str(uuid4())
        self.credential = credential or DefaultAzureCredential()
        self.http = http_session or requests.Session()

    # BEGIN AUTHENTICATE SESSION REQUESTS CODE SECTION
    def _headers(self) -> dict[str, str]:
        # Request a token for the dynamic sessions audience on every operation.
        # DefaultAzureCredential handles token caching and renewal.
        token = self.credential.get_token(TOKEN_SCOPE).token
        return {"Authorization": f"Bearer {token}"}

    def _params(self) -> dict[str, str]:
        # The identifier routes every request to the same temporary environment.
        # A request allocates the session automatically if it does not exist.
        return {
            "api-version": API_VERSION,
            "identifier": self.identifier,
        }

    # END AUTHENTICATE SESSION REQUESTS CODE SECTION

    @staticmethod
    def _error_detail(response: requests.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text.strip() or "No response details were returned"

        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str) and message:
                    return message
        return response.text.strip() or "No response details were returned"

    def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: tuple[int, int],
        **kwargs: Any,
    ) -> requests.Response:
        try:
            response = self.http.request(
                method,
                f"{self.endpoint}{path}",
                headers=self._headers(),
                params=self._params(),
                timeout=timeout,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            response = error.response
            if response is None:
                raise DynamicSessionRequestError(
                    f"Could not reach the dynamic sessions API: {error}"
                ) from error
            raise DynamicSessionRequestError(
                f"Dynamic sessions API returned HTTP {response.status_code}: "
                f"{self._error_detail(response)}"
            ) from error

    @staticmethod
    def _json_object(response: requests.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as error:
            raise DynamicSessionRequestError(
                "Dynamic sessions API returned an invalid JSON response"
            ) from error
        if not isinstance(body, dict):
            raise DynamicSessionRequestError(
                "Dynamic sessions API returned an unexpected response"
            )
        return body

    # BEGIN UPLOAD SESSION FILE CODE SECTION
    def upload_file(self, file_path: Path) -> dict[str, Any]:
        """Upload a local file into the session's /mnt/data directory."""
        # The service stores uploaded files in /mnt/data. Analysis code sent
        # with the same identifier can access the file without another upload.
        with file_path.open("rb") as source:
            response = self._request(
                "POST",
                "/files",
                files={"file": (file_path.name, source, "text/csv")},
                timeout=(5, 30),
            )
        return self._json_object(response)

    # END UPLOAD SESSION FILE CODE SECTION

    # BEGIN EXECUTE CODE AND CHECK RESULT CODE SECTION
    def execute_code(self, code: str) -> dict[str, Any]:
        """Execute Python code synchronously and verify its final status."""
        # The code runs in the isolated interpreter session, not in the Flask
        # process. The backend must still authorize and validate the task.
        response = self._request(
            "POST",
            "/executions",
            json={
                "codeInputType": "Inline",
                "executionType": "Synchronous",
                "code": code,
                "timeoutInSeconds": 60,
                "outputStreamsMaxLength": 4096,
            },
            timeout=(5, 90),
        )
        execution = self._json_object(response)

        # A successful HTTP request only proves that the service accepted and
        # ran the operation. Python can still raise an execution-level error.
        if execution.get("status") != "Succeeded":
            result = execution.get("result")
            stderr = result.get("stderr") if isinstance(result, dict) else None
            error = execution.get("error")
            message = None
            if isinstance(error, dict):
                message = error.get("message")
                nested_error = error.get("error")
                if not message and isinstance(nested_error, dict):
                    message = nested_error.get("message")
            raise CodeExecutionError(
                str(stderr or message or "Code execution failed")
            )
        return execution

    # END EXECUTE CODE AND CHECK RESULT CODE SECTION

    # BEGIN MANAGE SESSION FILES CODE SECTION
    def list_files(self) -> list[dict[str, Any]]:
        """List files retained in the current session."""
        # The same identifier used for upload and execution exposes both the
        # original input and artifacts created by the generated code.
        response = self._request("GET", "/files", timeout=(5, 15))
        body = self._json_object(response)
        files = body.get("value", [])
        if not isinstance(files, list) or not all(
            isinstance(item, dict) for item in files
        ):
            raise DynamicSessionRequestError(
                "Dynamic sessions API returned an unexpected file list"
            )
        return files

    def download_file(self, file_name: str) -> bytes:
        """Download one file from the current session."""
        # Reject directory components before placing the name in the URL. This
        # keeps file retrieval within the session's managed data directory.
        if Path(file_name).name != file_name:
            raise ValueError("A file name without a directory is required")
        safe_name = quote(file_name, safe="")
        response = self._request(
            "GET",
            f"/files/{safe_name}/content",
            timeout=(5, 30),
        )
        return response.content

    # END MANAGE SESSION FILES CODE SECTION

    # BEGIN DELETE SESSION CODE SECTION
    def delete_session(self) -> int:
        """Immediately release the current dynamic session."""
        # The pool cooldown eventually removes idle sessions, but explicit
        # deletion releases capacity and temporary data as soon as work ends.
        response = self._request("DELETE", "/session", timeout=(5, 15))
        return response.status_code

    # END DELETE SESSION CODE SECTION
