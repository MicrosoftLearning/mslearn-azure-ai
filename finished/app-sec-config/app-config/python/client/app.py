"""
Flask application demonstrating configuration management with Azure App Configuration.
"""
import logging
import os
import random
from flask import Flask, render_template, redirect, url_for, flash

from appconfig_functions import (
    load_settings,
    list_setting_properties,
    update_setting,
    refresh_configuration
)

app = Flask(__name__)
app.secret_key = os.urandom(24)


@app.route("/")
def index():
    """Display the main page."""
    return render_template("index.html")


@app.route("/load-settings", methods=["POST"])
def load():
    """Load all settings with label stacking and Key Vault resolution."""
    try:
        results = load_settings()
        loaded = sum(1 for r in results if r["status"] == "loaded")
        flash(f"Loaded {loaded} of {len(results)} setting(s).", "success")
        return render_template("index.html", load_results=results)
    except Exception as e:
        flash(f"Error loading settings: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/list-settings", methods=["POST"])
def list_settings():
    """List all setting properties."""
    try:
        results = list_setting_properties()
        flash(f"Found {len(results)} setting(s) in the store.", "success")
        return render_template("index.html", list_results=results)
    except Exception as e:
        flash(f"Error listing settings: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/update-setting", methods=["POST"])
def update():
    """Update a configuration setting."""
    try:
        new_value = str(random.randint(100, 999))
        result = update_setting("Pipeline:BatchSize", new_value, "Production")
        flash("Successfully updated the setting.", "success")
        return render_template("index.html", update_result=result)
    except Exception as e:
        flash(f"Error updating setting: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/refresh-settings", methods=["POST"])
def refresh():
    """Demonstrate sentinel-based dynamic refresh."""
    try:
        results = refresh_configuration()
        if results["batch_size_updated"]:
            flash("Configuration refreshed successfully.", "success")
        else:
            flash("Refresh completed but changes may not have propagated.", "warning")
        return render_template("index.html", refresh_results=results)
    except Exception as e:
        flash(f"Error refreshing configuration: {str(e)}", "error")
        return redirect(url_for("index"))


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(" * Running on http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
