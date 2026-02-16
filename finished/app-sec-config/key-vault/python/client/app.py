"""
Flask application demonstrating secret management with Azure Key Vault.
"""
import logging
import os
import uuid
from flask import Flask, render_template, redirect, url_for, flash

from keyvault_functions import (
    retrieve_secrets,
    list_secret_properties,
    create_secret_version,
    cached_retrieval
)

app = Flask(__name__)
app.secret_key = os.urandom(24)


@app.route("/")
def index():
    """Display the main page."""
    return render_template("index.html")


@app.route("/retrieve-secrets", methods=["POST"])
def retrieve():
    """Retrieve secrets and their metadata."""
    try:
        results = retrieve_secrets()
        retrieved = sum(1 for r in results if r["status"] == "retrieved")
        flash(f"Retrieved {retrieved} of {len(results)} secret(s).", "success")
        return render_template("index.html", retrieve_results=results)
    except Exception as e:
        flash(f"Error retrieving secrets: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/list-secrets", methods=["POST"])
def list_secrets():
    """List all secret properties."""
    try:
        results = list_secret_properties()
        flash(f"Found {len(results)} secret(s) in the vault.", "success")
        return render_template("index.html", list_results=results)
    except Exception as e:
        flash(f"Error listing secrets: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/create-version", methods=["POST"])
def create_version():
    """Create a new version of a secret."""
    try:
        new_value = f"sk-rotated-key-{uuid.uuid4().hex[:8]}"
        result = create_secret_version("openai-api-key", new_value)
        flash("Successfully created new version of the secret.", "success")
        return render_template("index.html", version_result=result)
    except Exception as e:
        flash(f"Error creating secret version: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/cached-retrieval", methods=["POST"])
def cached():
    """Demonstrate cached secret retrieval."""
    try:
        results = cached_retrieval()
        flash(
            f"Completed {results['total_accesses']} access(es) with "
            f"{results['vault_calls']} Key Vault API call(s).",
            "success"
        )
        return render_template("index.html", cache_results=results)
    except Exception as e:
        flash(f"Error with cached retrieval: {str(e)}", "error")
        return redirect(url_for("index"))


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(" * Running on http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
