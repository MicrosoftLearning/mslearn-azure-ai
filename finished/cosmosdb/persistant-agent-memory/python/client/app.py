"""Flask application demonstrating persistent agent memory with Cosmos DB."""

import logging
import os
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


def _run_action(
    action: Callable[[], Any],
    result_name: str,
    success_message: str,
) -> Any:
    try:
        result = action()
        flash(success_message, "success")
        return render_template("index.html", **{result_name: result})
    except (AzureError, ValueError) as error:
        flash(f"Error: {error}", "error")
        return redirect(url_for("index"))


@app.route("/")
def index() -> str:
    """Display the persistent-memory workflow."""
    return render_template("index.html")


@app.route("/setup-container", methods=["POST"])
def setup_container() -> Any:
    """Create the memory container with hierarchical partitioning and TTL."""
    return _run_action(
        create_memory_container,
        "container_result",
        "Memory container is ready.",
    )


@app.route("/store-turns", methods=["POST"])
def store_turns() -> Any:
    """Store sample turns from two conversation threads."""
    return _run_action(
        store_conversation_turns,
        "turns_result",
        "Conversation turns stored.",
    )


@app.route("/store-preference", methods=["POST"])
def store_preference() -> Any:
    """Store a durable user preference."""
    return _run_action(
        store_durable_preference,
        "preference_result",
        "Durable preference stored.",
    )


@app.route("/retrieve-thread", methods=["POST"])
def retrieve_thread() -> Any:
    """Retrieve only the active thread's recent turns."""
    return _run_action(
        retrieve_active_thread,
        "recent_turns",
        "Active thread retrieved.",
    )


@app.route("/retrieve-memory", methods=["POST"])
def retrieve_memory() -> Any:
    """Retrieve the user's durable cross-thread memory."""
    return _run_action(
        retrieve_durable_memory,
        "durable_memory",
        "Durable memory retrieved.",
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
    )


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(" * Running on http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
