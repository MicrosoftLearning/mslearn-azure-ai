"""Flask application demonstrating Azure Container Apps dynamic sessions."""

from __future__ import annotations

import json
import logging
import os
import threading
from io import BytesIO
from pathlib import Path
from typing import Any

from flask import Flask, flash, redirect, render_template, send_file, url_for

from dynamic_sessions_functions import (
    CodeExecutionError,
    DynamicSessionClient,
    DynamicSessionError,
    get_session_client,
)

app = Flask(__name__)
app.secret_key = os.urandom(24)

CLIENT_DIR = Path(__file__).resolve().parent
DATA_FILE = CLIENT_DIR / "operational-data.csv"
ANALYSIS_PAYLOAD = CLIENT_DIR / "analysis_payload.py"
FAILING_CODE = 'raise RuntimeError("Supplied analysis failed")'
EXPECTED_SUMMARY = {
    "months": 4,
    "total_requests": 1000,
    "average_requests": 250.0,
    "peak_month": "April",
    "peak_requests": 400,
}


class WorkflowState:
    """Keep one session identifier across the local learning workflow."""

    def __init__(self) -> None:
        self.client: DynamicSessionClient | None = None
        self.uploaded = False
        self.executed = False
        self.files_listed = False
        self.downloaded = False
        self.download_content: bytes | None = None
        self.lock = threading.Lock()

    def view(self) -> dict[str, Any]:
        identifier = self.client.identifier if self.client else ""
        return {
            "active": self.client is not None,
            "identifier": f"{identifier[:8]}..." if identifier else "",
            "uploaded": self.uploaded,
            "executed": self.executed,
            "files_listed": self.files_listed,
            "downloaded": self.downloaded,
        }

    def reset(self) -> None:
        self.client = None
        self.uploaded = False
        self.executed = False
        self.files_listed = False
        self.downloaded = False
        self.download_content = None


workflow = WorkflowState()


def render_index(**context: Any):
    """Render the page with the latest workflow state."""
    return render_template("index.html", state=workflow.view(), **context)


def require_client() -> DynamicSessionClient:
    """Return the active client or raise a user-facing workflow error."""
    if workflow.client is None:
        raise ValueError("Upload the sample data to start a session first")
    return workflow.client


@app.route("/")
def index():
    """Display the dynamic session workflow."""
    return render_index()


@app.route("/upload", methods=["POST"])
def upload():
    """Start a session and upload the deterministic CSV input."""
    try:
        with workflow.lock:
            if workflow.client is None:
                workflow.client = get_session_client()
            metadata = workflow.client.upload_file(DATA_FILE)
            workflow.uploaded = True
            workflow.executed = False
            workflow.files_listed = False
            workflow.downloaded = False
            workflow.download_content = None
        flash("Uploaded operational-data.csv to a new isolated session.", "success")
        return render_index(upload_result=metadata)
    except (DynamicSessionError, OSError, ValueError) as error:
        flash(f"Error uploading sample data: {error}", "error")
        return redirect(url_for("index"))


@app.route("/execute", methods=["POST"])
def execute():
    """Run the supplied analysis code and validate its output contract."""
    try:
        with workflow.lock:
            client = require_client()
            if not workflow.uploaded:
                raise ValueError("Upload the sample data before running the analysis")
            code = ANALYSIS_PAYLOAD.read_text(encoding="utf-8")
            execution = client.execute_code(code)
            result = execution.get("result")
            if not isinstance(result, dict):
                raise ValueError("The execution response did not include a result")
            stdout = result.get("stdout")
            if not isinstance(stdout, str):
                raise ValueError("The analysis did not write a JSON summary")
            summary = json.loads(stdout)
            if summary != EXPECTED_SUMMARY:
                raise ValueError(f"Unexpected analysis result: {summary}")
            workflow.executed = True
            workflow.files_listed = False
            workflow.downloaded = False
            workflow.download_content = None

        flash("The supplied analysis ran and returned the expected result.", "success")
        return render_index(
            execution_result={
                "id": execution.get("id", ""),
                "status": execution.get("status", ""),
                "duration": result.get("executionTimeInMilliseconds", 0),
                "stderr": result.get("stderr", ""),
                "summary": summary,
            }
        )
    except (
        DynamicSessionError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        flash(f"Error executing analysis: {error}", "error")
        return redirect(url_for("index"))


@app.route("/files", methods=["POST"])
def list_session_files():
    """List artifacts retained by the active session."""
    try:
        with workflow.lock:
            if not workflow.executed:
                raise ValueError("Run the analysis before listing session files")
            files = require_client().list_files()
            workflow.files_listed = True
        flash(f"Found {len(files)} file(s) in the reused session.", "success")
        return render_index(file_results=files)
    except (DynamicSessionError, ValueError) as error:
        flash(f"Error listing session files: {error}", "error")
        return redirect(url_for("index"))


@app.route("/download", methods=["POST"])
def download():
    """Prepare the generated chart and mark the workflow step complete."""
    try:
        with workflow.lock:
            if not workflow.files_listed:
                raise ValueError("List the session files before downloading the chart")
            content = require_client().download_file("trend.svg")
            workflow.download_content = content
            workflow.downloaded = True
        flash("Downloaded trend.svg from the reused session.", "success")
        return render_index(
            download_ready=True,
            download_result={
                "name": "trend.svg",
                "content_type": "image/svg+xml",
                "size": len(content),
            },
        )
    except (DynamicSessionError, ValueError) as error:
        flash(f"Error downloading generated chart: {error}", "error")
        return redirect(url_for("index"))


@app.route("/download-content")
def download_content():
    """Send the prepared chart as an attachment."""
    with workflow.lock:
        content = workflow.download_content
    if content is None:
        flash("Prepare the generated chart before downloading it.", "error")
        return redirect(url_for("index"))
    return send_file(
        BytesIO(content),
        mimetype="image/svg+xml",
        as_attachment=True,
        download_name="trend.svg",
    )


@app.route("/test-failure", methods=["POST"])
def test_failure():
    """Confirm that a Python exception is reported as execution failure."""
    try:
        with workflow.lock:
            client = require_client()
            try:
                client.execute_code(FAILING_CODE)
            except CodeExecutionError as error:
                expected_error = str(error)
            else:
                raise ValueError("The failing payload appeared successful")
        flash("The expected execution failure was detected.", "success")
        return render_index(expected_error=expected_error)
    except (DynamicSessionError, ValueError) as error:
        flash(f"Error testing the failure path: {error}", "error")
        return redirect(url_for("index"))


@app.route("/delete", methods=["POST"])
def delete():
    """Delete the active session and clear local workflow state."""
    try:
        with workflow.lock:
            identifier = workflow.view()["identifier"]
            status_code = require_client().delete_session()
            workflow.reset()
        flash("Deleted the dynamic session and released its resources.", "success")
        return render_index(
            delete_result={
                "identifier": identifier,
                "status_code": status_code,
            }
        )
    except (DynamicSessionError, ValueError) as error:
        flash(f"Error deleting the session: {error}", "error")
        return redirect(url_for("index"))


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(" * Running on http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
