import json
import logging
import os
from pathlib import Path

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

MODEL_ENDPOINT = os.getenv("MODEL_ENDPOINT", "http://localhost:11434").rstrip("/")
MODEL_INFO_PATH = Path(os.getenv("MODEL_INFO_PATH", "/app/models/manifest.json"))
MODEL_REQUEST_TIMEOUT = int(os.getenv("MODEL_REQUEST_TIMEOUT", "240"))
MAX_MESSAGES = 8
MAX_MESSAGE_LENGTH = 2000
MAX_CONVERSATION_LENGTH = 10000

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def validate_messages(payload: object) -> tuple[list[dict[str, str]] | None, str | None]:
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        return None, "Request JSON must contain a list named 'messages'."

    messages = payload["messages"]
    if not messages:
        return None, "At least one message is required."
    if len(messages) > MAX_MESSAGES:
        return None, f"Conversation history must not exceed {MAX_MESSAGES} messages."

    validated = []
    for message in messages:
        if not isinstance(message, dict):
            return None, "Each message must be an object."
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"}:
            return None, "Message roles must be either 'user' or 'assistant'."
        if not isinstance(content, str) or not content.strip():
            return None, "Each message must contain non-empty text."
        if len(content) > MAX_MESSAGE_LENGTH:
            return None, f"Each message must not exceed {MAX_MESSAGE_LENGTH} characters."
        validated.append({"role": role, "content": content.strip()})

    if validated[-1]["role"] != "user":
        return None, "The final message must have the 'user' role."
    if sum(len(message["content"]) for message in validated) > MAX_CONVERSATION_LENGTH:
        return None, "The conversation is too long. Clear it and start a new conversation."
    return validated, None


@app.get("/")
def root():
    return jsonify(
        {
            "service": "Phi-3 Chat API",
            "status": "running",
            "endpoints": ["/api/chat", "/health/ready", "/model-info"],
        }
    )


@app.post("/api/chat")
def chat():
    messages, error = validate_messages(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400

    try:
        response = requests.post(
            f"{MODEL_ENDPOINT}/generate",
            json={"messages": messages, "max_new_tokens": 128},
            timeout=MODEL_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error("Model request failed: %s", exc)
        return jsonify({"error": "The local model service is unavailable."}), 503

    return jsonify(
        {
            "model": result["model"],
            "message": result["message"],
            "usage": result["usage"],
        }
    )


@app.get("/health/ready")
def ready():
    try:
        response = requests.get(f"{MODEL_ENDPOINT}/health", timeout=5)
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Model readiness check failed: %s", exc)
        return jsonify({"status": "not ready", "model_available": False}), 503

    is_ready = result.get("status") == "ready"
    return (
        jsonify({"status": "ready" if is_ready else "not ready", "model_available": is_ready}),
        200 if is_ready else 503,
    )


@app.get("/model-info")
def model_info():
    try:
        with MODEL_INFO_PATH.open(encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
    except FileNotFoundError:
        return jsonify({"error": "The model manifest is not available."}), 503
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Could not read the model manifest: %s", exc)
        return jsonify({"error": "The model manifest could not be read."}), 500

    return jsonify(
        {
            "model": manifest.get("model"),
            "quantization": manifest.get("quantization"),
            "status": manifest.get("status"),
            "runtime": manifest.get("runtime"),
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
