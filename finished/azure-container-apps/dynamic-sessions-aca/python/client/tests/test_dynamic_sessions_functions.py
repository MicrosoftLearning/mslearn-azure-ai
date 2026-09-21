from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

CLIENT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT_DIR))

from dynamic_sessions_functions import (  # noqa: E402
    API_VERSION,
    CodeExecutionError,
    DynamicSessionClient,
    DynamicSessionRequestError,
    TOKEN_SCOPE,
)


def response_with(
    body: object | None = None,
    *,
    content: bytes = b"",
    status_code: int = 200,
) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.content = content
    response.text = ""
    response.json.return_value = body
    response.raise_for_status.return_value = None
    return response


class DynamicSessionClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.credential = Mock()
        self.credential.get_token.return_value.token = "test-token"
        self.http = Mock()
        self.client = DynamicSessionClient(
            "https://example.dynamicsessions.io/pool",
            credential=self.credential,
            http_session=self.http,
            identifier="session-1234",
        )

    def test_upload_uses_multipart_and_session_identifier(self) -> None:
        self.http.request.return_value = response_with(
            {"name": "operational-data.csv", "sizeInBytes": 42}
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "operational-data.csv"
            path.write_text("month,requests\nJanuary,100\n", encoding="utf-8")
            result = self.client.upload_file(path)

        self.assertEqual(result["name"], "operational-data.csv")
        _, url = self.http.request.call_args.args
        kwargs = self.http.request.call_args.kwargs
        self.assertEqual(url, "https://example.dynamicsessions.io/pool/files")
        self.assertEqual(
            kwargs["params"],
            {"api-version": API_VERSION, "identifier": "session-1234"},
        )
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(kwargs["files"]["file"][0], "operational-data.csv")
        self.credential.get_token.assert_called_once_with(TOKEN_SCOPE)

    def test_execute_uses_current_top_level_request_shape(self) -> None:
        self.http.request.return_value = response_with(
            {
                "id": "execution-1",
                "status": "Succeeded",
                "result": {"stdout": '{"total": 1000}', "stderr": ""},
            }
        )

        result = self.client.execute_code("print('hello')")

        self.assertEqual(result["status"], "Succeeded")
        request_body = self.http.request.call_args.kwargs["json"]
        self.assertNotIn("properties", request_body)
        self.assertEqual(request_body["codeInputType"], "Inline")
        self.assertEqual(request_body["executionType"], "Synchronous")
        self.assertEqual(request_body["timeoutInSeconds"], 60)

    def test_execute_raises_for_failed_code(self) -> None:
        self.http.request.return_value = response_with(
            {
                "status": "Failed",
                "result": {"stderr": "RuntimeError: supplied analysis failed"},
            }
        )

        with self.assertRaisesRegex(CodeExecutionError, "RuntimeError"):
            self.client.execute_code("raise RuntimeError()")

    def test_execute_surfaces_structured_execution_error(self) -> None:
        self.http.request.return_value = response_with(
            {
                "status": "Failed",
                "error": {"error": {"message": "Execution timed out"}},
            }
        )

        with self.assertRaisesRegex(CodeExecutionError, "Execution timed out"):
            self.client.execute_code("while True: pass")

    def test_list_and_download_reuse_same_session(self) -> None:
        self.http.request.side_effect = [
            response_with({"value": [{"name": "trend.svg", "type": "file"}]}),
            response_with(content=b"<svg/>"),
        ]

        files = self.client.list_files()
        content = self.client.download_file("trend.svg")

        self.assertEqual(files[0]["name"], "trend.svg")
        self.assertEqual(content, b"<svg/>")
        download_call = self.http.request.call_args_list[1]
        self.assertTrue(download_call.args[1].endswith("/files/trend.svg/content"))
        self.assertEqual(download_call.kwargs["params"]["identifier"], "session-1234")

    def test_download_rejects_directory_traversal(self) -> None:
        with self.assertRaisesRegex(ValueError, "file name"):
            self.client.download_file("../trend.svg")
        self.http.request.assert_not_called()

    def test_delete_uses_current_session_api(self) -> None:
        self.http.request.return_value = response_with(status_code=204)

        status_code = self.client.delete_session()

        method, url = self.http.request.call_args.args
        self.assertEqual(status_code, 204)
        self.assertEqual(method, "DELETE")
        self.assertTrue(url.endswith("/session"))
        self.assertEqual(
            self.http.request.call_args.kwargs["params"]["api-version"],
            API_VERSION,
        )

    def test_structured_http_error_is_surfaced(self) -> None:
        response = response_with(
            {"error": {"message": "Role assignment is not effective yet"}},
            status_code=403,
        )
        import requests

        response.raise_for_status.side_effect = requests.HTTPError(
            response=response
        )
        self.http.request.return_value = response

        with self.assertRaisesRegex(
            DynamicSessionRequestError, "Role assignment is not effective yet"
        ):
            self.client.list_files()


if __name__ == "__main__":
    unittest.main()
