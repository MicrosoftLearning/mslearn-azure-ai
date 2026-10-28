import logging
import os
import secrets
import threading
from dataclasses import asdict
from urllib.parse import urlsplit

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import ContainerClient
from flask import Flask, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException

from operation_store import OperationStore
from webpubsub_functions import OBSERVERS, authorize, connection_details, get_client, run_investigation


def create_app(store=None, pubsub=None, *, recover: bool = True) -> Flask:
    app = Flask(__name__)
    app.secret_key = os.urandom(24)
    app.config.update(
        MAX_CONTENT_LENGTH=4096, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
    )
    if store is None or pubsub is None:
        required = ("WEBPUBSUB_ENDPOINT", "WEBPUBSUB_HUB", "BLOB_ACCOUNT_URL", "BLOB_CONTAINER")
        missing = [key for key in required if not os.environ.get(key)]
        if missing:
            raise ValueError(
                f"Missing configuration: {', '.join(missing)}. "
                "Run deployment option 4 and load its generated environment file "
                "from the folder containing azdeploy.py."
            )
        credential = DefaultAzureCredential()
        store = OperationStore(ContainerClient(
            account_url=os.environ["BLOB_ACCOUNT_URL"],
            container_name=os.environ["BLOB_CONTAINER"], credential=credential,
        ))
        pubsub = get_client(credential)
    if recover:
        store.interrupt_abandoned()
    app.extensions["operation_store"] = store
    app.extensions["webpubsub"] = pubsub

    @app.before_request
    def protect_demo():
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and urlsplit(origin).netloc != request.host:
                return jsonify(error="Cross-origin actions are not allowed."), 403
            if not secrets.compare_digest(
                request.headers.get("X-CSRF-Token", ""), session.get("csrf_token", "-"),
            ):
                return jsonify(error="Reload the page before submitting this action."), 403

    def observer() -> str:
        supplied = request.headers.get("X-Demo-Viewer", "")
        for name, token in session.get("viewer_tokens", {}).items():
            if name in OBSERVERS and secrets.compare_digest(supplied.encode(), token.encode()):
                return name
        raise PermissionError("Unknown observer context. Reload the page and try again.")

    def operation(operation_id, *, start=False):
        viewer = observer()
        value, _ = store.load(operation_id)
        authorize(value, viewer, start=start)
        return value

    @app.get("/")
    def index():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(24)
        if "viewer_tokens" not in session:
            session["viewer_tokens"] = {name: secrets.token_hex(24) for name in OBSERVERS}
        return render_template(
            "index.html", observers=OBSERVERS, viewer_tokens=session["viewer_tokens"],
            csrf_token=session["csrf_token"],
        )

    @app.post("/api/operations")
    def create_operation():
        if observer() != "oncall":
            raise PermissionError("Only the on-call developer can create investigations.")
        value = store.create("oncall", ["oncall", "database"])
        return jsonify(asdict(value)), 201

    @app.get("/api/operations/<operation_id>")
    def snapshot(operation_id):
        return jsonify(asdict(operation(operation_id)))

    @app.post("/api/operations/<operation_id>/negotiate")
    def negotiate(operation_id):
        value = operation(operation_id)
        return jsonify(connection_details(pubsub, value, observer()))

    @app.post("/api/operations/<operation_id>/start")
    def start_operation(operation_id):
        operation(operation_id, start=True)
        value, claimed = store.claim(operation_id)
        if claimed:
            thread = threading.Thread(
                target=run_investigation, args=(store, pubsub, operation_id), daemon=True,
                name=f"investigation-{operation_id}",
            )
            try:
                thread.start()
            except RuntimeError:
                store.record(operation_id, "failed", {"error": "Could not start the background worker."})
                raise
        return jsonify(operation=asdict(value), started=claimed)

    @app.get("/api/operations/<operation_id>/result")
    def result(operation_id):
        value = operation(operation_id)
        if value.status != "completed":
            return jsonify(error="The investigation result is not ready."), 409
        return jsonify(store.result(operation_id))

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.errorhandler(PermissionError)
    def forbidden(exc):
        return jsonify(error=str(exc)), 403

    @app.errorhandler(ValueError)
    def invalid(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(ResourceNotFoundError)
    def missing_resource(exc):
        app.logger.warning("A requested investigation or storage resource was not found.")
        return jsonify(error="Investigation or storage container not found. Check the ID and deployment."), 404

    @app.errorhandler(AzureError)
    def azure_failure(exc):
        app.logger.error("Azure request failed (%s). Check configuration and data-plane roles.", type(exc).__name__)
        return jsonify(error="Azure request failed. Check the backend terminal, deployment, and RBAC permissions."), 503

    @app.errorhandler(Exception)
    def unexpected(exc):
        if isinstance(exc, HTTPException):
            return jsonify(error=exc.description), exc.code
        app.logger.exception("Unexpected backend error.")
        return jsonify(error="Unexpected backend error. Check the terminal for details."), 500

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("azure").setLevel(logging.WARNING)
    try:
        application = create_app()
    except (AzureError, ValueError) as error:
        raise SystemExit(f"Error: Cannot start the app: {error}") from error
    print("Open http://localhost:5000 to watch both responders on one page.")
    application.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)
