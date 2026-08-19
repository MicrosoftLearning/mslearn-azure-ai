import logging
import os
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request

CLIENT_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(CLIENT_DIR / "templates"),
    static_folder=str(CLIENT_DIR / "static"),
)

CHAT_API_URL = os.getenv("CHAT_API_URL", "").rstrip("/")
CHAT_API_TIMEOUT = int(os.getenv("CHAT_API_TIMEOUT", "300"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def api_url(path: str) -> str:
    if not CHAT_API_URL:
        raise RuntimeError(
            "CHAT_API_URL is not configured. Source .env or dot-source .env.ps1 "
            "before starting the client."
        )
    return f"{CHAT_API_URL}{path}"


def proxy_json(method: str, path: str, payload: object = None, timeout: int = 10):
    try:
        response = requests.request(
            method,
            api_url(path),
            json=payload,
            timeout=timeout,
        )
        result = response.json()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return jsonify({"error": str(exc)}), 500
    except requests.RequestException as exc:
        logger.error("Chat API request failed: %s", exc)
        return jsonify({"error": "The Azure chat API is unavailable."}), 503
    except ValueError:
        logger.error("Chat API returned a non-JSON response.")
        return jsonify({"error": "The Azure chat API returned an invalid response."}), 502
    return jsonify(result), response.status_code


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/chat")
def chat():
    return proxy_json(
        "POST",
        "/api/chat",
        payload=request.get_json(silent=True),
        timeout=CHAT_API_TIMEOUT,
    )


@app.get("/health/ready")
def ready():
    return proxy_json("GET", "/health/ready")


@app.get("/model-info")
def model_info():
    return proxy_json("GET", "/model-info")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
