"""
Flask application demonstrating publish/subscribe messaging with Azure Managed Redis.

A single page lets you publish event messages to Redis channels and subscribe to
channels or patterns. Received messages are displayed live by polling the
/messages endpoint.
"""
import logging
import os
import threading

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from pubsub_functions import (
    AVAILABLE_CHANNELS,
    PubSubManager,
    broadcast_to_all,
    publish_inventory_alert,
    publish_notification,
    publish_order_created,
    publish_order_shipped,
)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# A single PubSubManager is shared across requests. It holds the Redis
# connection and the background listener thread. It is created lazily on the
# first request so the app can start even before the user has authenticated.
_manager = None
_manager_lock = threading.Lock()


def get_manager():
    """Return the shared PubSubManager, creating it on first use."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = PubSubManager()
        return _manager


# Maps the event name in the URL to the function that publishes it.
PUBLISHERS = {
    "order-created": publish_order_created,
    "order-shipped": publish_order_shipped,
    "inventory-alert": publish_inventory_alert,
    "notification": publish_notification,
    "broadcast": broadcast_to_all,
}


@app.route("/")
def index():
    """Display the main page."""
    return render_template("index.html", channels=AVAILABLE_CHANNELS)


@app.route("/publish/<event>", methods=["POST"])
def publish(event):
    """Publish an event message to one or more channels."""
    publisher = PUBLISHERS.get(event)
    if publisher is None:
        flash("Unknown event type.", "error")
        return redirect(url_for("index"))

    try:
        manager = get_manager()
        result = publisher(manager.r)
        if "channels" in result:
            flash(
                f"Broadcast to {len(result['channels'])} channel(s) — "
                f"{result['total_subscribers']} subscriber(s) reached.",
                "success",
            )
        else:
            flash(
                f"Published to '{result['channel']}' — "
                f"{result['subscribers']} subscriber(s).",
                "success",
            )
        return render_template(
            "index.html", channels=AVAILABLE_CHANNELS, publish_result=result
        )
    except Exception as e:
        flash(f"Error publishing message: {e}", "error")
        return redirect(url_for("index"))


@app.route("/subscribe", methods=["POST"])
def subscribe():
    """Subscribe to a specific channel."""
    channel = request.form.get("channel", "").strip()
    if not channel:
        flash("Enter a channel name to subscribe.", "error")
        return redirect(url_for("index"))
    try:
        message = get_manager().subscribe_to_channel(channel)
        flash(message, "success")
    except Exception as e:
        flash(f"Error subscribing: {e}", "error")
    return redirect(url_for("index"))


@app.route("/subscribe-pattern", methods=["POST"])
def subscribe_pattern():
    """Subscribe to a channel pattern (e.g. orders:*)."""
    pattern = request.form.get("pattern", "").strip()
    if not pattern:
        flash("Enter a pattern to subscribe.", "error")
        return redirect(url_for("index"))
    try:
        message = get_manager().subscribe_to_pattern(pattern)
        flash(message, "success")
    except Exception as e:
        flash(f"Error subscribing to pattern: {e}", "error")
    return redirect(url_for("index"))


@app.route("/unsubscribe", methods=["POST"])
def unsubscribe():
    """Unsubscribe from a specific channel."""
    channel = request.form.get("channel", "").strip()
    if not channel:
        flash("Enter a channel name to unsubscribe.", "error")
        return redirect(url_for("index"))
    try:
        message = get_manager().unsubscribe_from_channel(channel)
        flash(message, "success")
    except Exception as e:
        flash(f"Error unsubscribing: {e}", "error")
    return redirect(url_for("index"))


@app.route("/unsubscribe-all", methods=["POST"])
def unsubscribe_all():
    """Unsubscribe from all channels and patterns."""
    try:
        message = get_manager().unsubscribe_all()
        flash(message, "success")
    except Exception as e:
        flash(f"Error unsubscribing: {e}", "error")
    return redirect(url_for("index"))


@app.route("/messages")
def messages():
    """Return new received messages and current subscriptions as JSON."""
    since = request.args.get("since", default=0, type=int)
    try:
        manager = get_manager()
        new_messages, last_index = manager.get_messages(since)
        subscriptions = manager.get_subscriptions()
    except Exception as e:
        return jsonify({
            "messages": [],
            "last_index": since,
            "subscriptions": {"channels": [], "patterns": [], "listening": False},
            "error": str(e),
        })
    return jsonify({
        "messages": new_messages,
        "last_index": last_index,
        "subscriptions": subscriptions,
    })


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(" * Running on http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
