"""Flask application demonstrating persistent agent memory with Cosmos DB."""

import logging
import os
import threading
from collections.abc import Callable
from typing import Any

from azure.core.exceptions import AzureError
from flask import Flask, flash, redirect, render_template, url_for
from memory_functions import (
    build_agent_context,
    create_memory_container,
    retrieve_active_thread,
    retrieve_durable_memory,
    store_conversation_turns,
    store_durable_preference,
)

CURRENT_USER_MESSAGE = "Show me how to correct the configuration."

app = Flask(__name__)
app.secret_key = os.urandom(24)

WORKFLOW_STEPS = [
    ("container_ready", "set up the memory container"),
    ("turns_stored", "store the conversation turns"),
    ("preference_stored", "store the durable preference"),
    ("thread_retrieved", "retrieve the active thread"),
    ("memory_retrieved", "retrieve durable memory"),
    ("context_built", "build the agent context"),
]


class WorkflowState:
    """Track progress through the local learning workflow."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def view(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name, _ in WORKFLOW_STEPS}

    def complete(self, step: str) -> None:
        step_index = next(
            index for index, (name, _) in enumerate(WORKFLOW_STEPS) if name == step
        )
        for index, (name, _) in enumerate(WORKFLOW_STEPS):
            if index >= step_index:
                setattr(self, name, index == step_index)

    def reset(self) -> None:
        for name, _ in WORKFLOW_STEPS:
            setattr(self, name, False)


workflow = WorkflowState()


def render_index(**context: Any) -> str:
    """Render the page with the latest workflow state."""
    return render_template("index.html", state=workflow.view(), **context)


def _require_step(step: str | None) -> None:
    if step and not getattr(workflow, step):
        label = next(label for name, label in WORKFLOW_STEPS if name == step)
        raise ValueError(f"Complete the previous step to {label} first")


def _run_action(
    action: Callable[[], Any],
    result_name: str,
    success_message: str,
    completed_step: str,
    required_step: str | None = None,
) -> Any:
    try:
        with workflow.lock:
            _require_step(required_step)
            result = action()
            workflow.complete(completed_step)
        flash(success_message, "success")
        return render_index(**{result_name: result})
    except (AzureError, ValueError) as error:
        flash(f"Error: {error}", "error")
        return redirect(url_for("index"))


@app.route("/")
def index() -> str:
    """Display the persistent-memory workflow."""
    return render_index()


@app.route("/setup-container", methods=["POST"])
def setup_container() -> Any:
    """Create the memory container with hierarchical partitioning and TTL."""
    return _run_action(
        create_memory_container,
        "container_result",
        "Memory container is ready.",
        "container_ready",
    )


@app.route("/store-turns", methods=["POST"])
def store_turns() -> Any:
    """Store sample turns from two conversation threads."""
    return _run_action(
        store_conversation_turns,
        "turns_result",
        "Conversation turns stored.",
        "turns_stored",
        "container_ready",
    )


@app.route("/store-preference", methods=["POST"])
def store_preference() -> Any:
    """Store a durable user preference."""
    return _run_action(
        store_durable_preference,
        "preference_result",
        "Durable preference stored.",
        "preference_stored",
        "turns_stored",
    )


@app.route("/retrieve-thread", methods=["POST"])
def retrieve_thread() -> Any:
    """Retrieve only the active thread's recent turns."""
    return _run_action(
        retrieve_active_thread,
        "recent_turns",
        "Active thread retrieved.",
        "thread_retrieved",
        "preference_stored",
    )


@app.route("/retrieve-memory", methods=["POST"])
def retrieve_memory() -> Any:
    """Retrieve the user's durable cross-thread memory."""
    return _run_action(
        retrieve_durable_memory,
        "durable_memory",
        "Durable memory retrieved.",
        "memory_retrieved",
        "thread_retrieved",
    )


@app.route("/build-context", methods=["POST"])
def build_context() -> Any:
    """Build bounded context from recent and durable memory."""

    def create_context() -> dict[str, Any]:
        return build_agent_context(
            retrieve_active_thread(),
            retrieve_durable_memory(),
            CURRENT_USER_MESSAGE,
        )

    return _run_action(
        create_context,
        "context_result",
        "Agent context built.",
        "context_built",
        "memory_retrieved",
    )


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(" * Running on http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
