"""
Flask application demonstrating event routing with Azure Event Grid.
"""
import logging
import os
from flask import Flask, render_template, redirect, url_for, flash

from event_grid_functions import (
    publish_moderation_events,
    check_filtered_delivery,
    inspect_event_details
)

app = Flask(__name__)
app.secret_key = os.urandom(24)


@app.route("/")
def index():
    """Display the main page."""
    return render_template("index.html")


@app.route("/publish-events", methods=["POST"])
def publish():
    """Publish content moderation events to the Event Grid topic."""
    try:
        results = publish_moderation_events()
        flash(f"Successfully published {len(results)} event(s) to the Event Grid topic.", "success")
        return render_template("index.html", publish_results=results)
    except Exception as e:
        flash(f"Error publishing events: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/check-delivery", methods=["POST"])
def check():
    """Check filtered delivery across Service Bus queues."""
    try:
        results = check_filtered_delivery()
        total = len(results["flagged"]) + len(results["approved"]) + len(results["all_events"])
        if total > 0:
            flash(
                f"Flagged: {len(results['flagged'])}, "
                f"Approved: {len(results['approved'])}, "
                f"All events: {len(results['all_events'])}.",
                "success"
            )
        else:
            flash("No events found in the queues. Publish events first.", "success")
        return render_template("index.html", delivery_results=results)
    except Exception as e:
        flash(f"Error checking delivery: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/inspect-event", methods=["POST"])
def inspect():
    """Inspect CloudEvent details from the all-events queue."""
    try:
        result = inspect_event_details()
        if result:
            flash("Retrieved event details from the all-events queue.", "success")
        else:
            flash("No events available to inspect. Publish events first.", "success")
        return render_template("index.html", inspect_result=result)
    except Exception as e:
        flash(f"Error inspecting event: {str(e)}", "error")
        return redirect(url_for("index"))


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(" * Running on http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
