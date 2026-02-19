"""
Flask application demonstrating OpenTelemetry instrumentation
for a document processing pipeline.
"""
import logging
import os

from telemetry_functions import (
    configure_telemetry,
    process_documents,
    check_telemetry_status
)

# Configure OpenTelemetry before importing Flask.
# The distro replaces flask.Flask with an instrumented subclass,
# so this call must happen before Flask is imported into this module.
configure_telemetry()

from flask import Flask, render_template, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = os.urandom(24)


@app.route("/")
def index():
    """Display the main page."""
    return render_template("index.html")


@app.route("/process-documents", methods=["POST"])
def process():
    """Process a batch of documents through the traced pipeline."""
    try:
        results = process_documents(5)
        slow_count = sum(1 for r in results if r["enrich"]["slow"])
        flash(
            f"Processed {len(results)} document(s). "
            f"{slow_count} experienced high enrichment latency.",
            "success"
        )
        return render_template("index.html", process_results=results)
    except Exception as e:
        flash(f"Error processing documents: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/check-status", methods=["POST"])
def status():
    """Check the telemetry configuration status."""
    try:
        result = check_telemetry_status()
        if result["configured"]:
            flash("Telemetry is configured and exporting to Application Insights.", "success")
        else:
            flash("Telemetry is not fully configured. Check the connection string.", "error")
        return render_template("index.html", status_result=result)
    except Exception as e:
        flash(f"Error checking status: {str(e)}", "error")
        return redirect(url_for("index"))


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(" * Running on http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
