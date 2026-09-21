from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT_DIR))

from app import EXPECTED_SUMMARY, app, workflow  # noqa: E402


class FakeSessionClient:
    identifier = "12345678-abcd-efgh"

    def upload_file(self, file_path: Path) -> dict[str, object]:
        return {"name": file_path.name, "sizeInBytes": 42}

    def execute_code(self, code: str) -> dict[str, object]:
        return {
            "id": "execution-1",
            "status": "Succeeded",
            "result": {
                "stdout": json.dumps(EXPECTED_SUMMARY),
                "executionTimeInMilliseconds": 5,
            },
        }

    def list_files(self) -> list[dict[str, object]]:
        return [
            {"name": "operational-data.csv", "type": "file"},
            {"name": "trend.svg", "type": "file"},
        ]

    def download_file(self, file_name: str) -> bytes:
        return b"<svg/>"

    def delete_session(self) -> None:
        return None


class WorkflowProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        app.config["TESTING"] = True
        workflow.reset()
        workflow.client = FakeSessionClient()
        self.client = app.test_client()

    def tearDown(self) -> None:
        workflow.reset()

    def assert_step(
        self,
        response,
        step: str,
        status: str,
        state_class: str,
    ) -> None:
        text = response.get_data(as_text=True)
        pattern = re.compile(
            rf'<button[^>]*class="[^"]*{state_class}[^"]*"[^>]*>'
            rf".*?<span>{re.escape(step)}</span>"
            rf'.*?<span class="step-status">\s*{status}\s*</span>',
            re.DOTALL,
        )
        self.assertRegex(text, pattern)

    def test_workflow_steps_advance_in_order(self) -> None:
        response = self.client.get("/")
        self.assert_step(
            response, "1. Upload Sample Data", "Next", "step-current"
        )

        response = self.client.post("/upload")
        self.assertTrue(workflow.uploaded)
        self.assert_step(
            response, "1. Upload Sample Data", "Completed", "step-completed"
        )
        self.assert_step(
            response, "2. Execute Analysis", "Next", "step-current"
        )

        response = self.client.post("/execute")
        self.assertTrue(workflow.executed)
        self.assert_step(
            response, "2. Execute Analysis", "Completed", "step-completed"
        )
        self.assert_step(
            response, "3. List Session Files", "Next", "step-current"
        )

        response = self.client.post("/files")
        self.assertTrue(workflow.files_listed)
        self.assert_step(
            response, "3. List Session Files", "Completed", "step-completed"
        )
        self.assert_step(
            response, "4. Download Generated Chart", "Next", "step-current"
        )

        response = self.client.post("/download")
        self.assertTrue(workflow.downloaded)
        self.assert_step(
            response,
            "4. Download Generated Chart",
            "Completed",
            "step-completed",
        )
        self.assertIn('id="prepared-download"', response.get_data(as_text=True))

        response = self.client.get("/download-content")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"<svg/>")


if __name__ == "__main__":
    unittest.main()
