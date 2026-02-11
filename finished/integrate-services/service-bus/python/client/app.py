"""
Flask application demonstrating messaging patterns with Azure Service Bus.
"""
import os
from flask import Flask, render_template, redirect, url_for, flash

from service_bus_functions import (
    send_messages,
    process_messages,
    inspect_dead_letter_queue,
    topic_messaging
)

app = Flask(__name__)
app.secret_key = os.urandom(24)


@app.route("/")
def index():
    """Display the main page."""
    return render_template("index.html")


@app.route("/send-messages", methods=["POST"])
def send():
    """Send messages to the queue."""
    try:
        results = send_messages()
        flash(f"Successfully sent {len(results)} message(s) to the queue.", "success")
        return render_template("index.html", send_results=results)
    except Exception as e:
        flash(f"Error sending messages: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/process-messages", methods=["POST"])
def process():
    """Process messages from the queue."""
    try:
        results = process_messages()
        if results:
            completed = sum(1 for r in results if r["status"] == "completed")
            dead_lettered = sum(1 for r in results if r["status"] == "dead-lettered")
            flash(f"Processed {len(results)} message(s): {completed} completed, {dead_lettered} dead-lettered.", "success")
        else:
            flash("No messages to process. Send messages first.", "success")
        return render_template("index.html", process_results=results)
    except Exception as e:
        flash(f"Error processing messages: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/inspect-dlq", methods=["POST"])
def inspect_dlq():
    """Inspect the dead-letter queue."""
    try:
        results = inspect_dead_letter_queue()
        if results:
            flash(f"Found {len(results)} message(s) in the dead-letter queue.", "success")
        else:
            flash("No messages in the dead-letter queue.", "success")
        return render_template("index.html", dlq_results=results)
    except Exception as e:
        flash(f"Error inspecting dead-letter queue: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/topic-messaging", methods=["POST"])
def topic():
    """Send and receive topic messages."""
    try:
        results = topic_messaging()
        flash(
            f"Sent {len(results['sent'])} message(s). "
            f"Notifications received {len(results['notifications'])}, "
            f"High-priority received {len(results['high_priority'])}.",
            "success"
        )
        return render_template("index.html", topic_results=results)
    except Exception as e:
        flash(f"Error with topic messaging: {str(e)}", "error")
        return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
