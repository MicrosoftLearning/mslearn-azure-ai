"""
Flask application demonstrating event routing with Azure Event Grid.
"""
import logging
import os
from flask import Flask, render_template, redirect, url_for, flash

from event_grid_functions import (
    publish_moderation_events,
    check_filtered_delivery,
    inspect_and_reject
)

app = Flask(__name__)
app.secret_key = os.urandom(24)


@app.route("/")
def index():
    """Display the main page."""
    return render_template("index.html")


@app.route("/publish-events", methods=["POST"])
def publish():
    """Publish content moderation events to the Event Grid namespace topic."""
    try:
        results = publish_moderation_events()
        flash(f"Successfully published {len(results)} event(s) to the Event Grid namespace topic.", "success")
        return render_template("index.html", publish_results=results)
    except Exception as e:
        flash(f"Error publishing events: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/check-delivery", methods=["POST"])
def check():
    """Receive and acknowledge events from filtered subscriptions."""
    try:
        results = check_filtered_delivery()
        total = len(results["flagged"]) + len(results["approved"]) + len(results["all_events"])
        if total > 0:
            flash(
                f"Received and acknowledged — Flagged: {len(results['flagged'])}, "
                f"Approved: {len(results['approved'])}, "
                f"All events: {len(results['all_events'])}.",
                "success"
            )
        else:
            flash("No events available in subscriptions. Publish events first.", "success")
        return render_template("index.html", delivery_results=results)
    except Exception as e:
        flash(f"Error receiving events: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/inspect-event", methods=["POST"])
def inspect():
    """Publish, receive, inspect, and reject an event."""
    try:
        result = inspect_and_reject()
        if result:
            flash("Published a test event, received it, inspected the envelope, and rejected it.", "success")
        else:
            flash("No events received from the subscription. Check that the namespace is deployed.", "success")
        return render_template("index.html", inspect_result=result)
    except Exception as e:
        flash(f"Error inspecting event: {str(e)}", "error")
        return redirect(url_for("index"))


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(" * Running on http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
