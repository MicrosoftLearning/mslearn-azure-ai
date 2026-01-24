"""Mock agent API for Azure Container Apps autoscaling exercise.

This app exposes an HTTP endpoint that simulates agent request processing.
Students use it to generate concurrent HTTP traffic and observe autoscaling.
"""

from __future__ import annotations

import os
import threading
import time
import uuid

from flask import Flask, jsonify, request


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
AGENT_DEFAULT_DELAY_MS = _int_env("AGENT_DEFAULT_DELAY_MS", 500)

app = Flask(__name__)

_lock = threading.Lock()
_stats = {
    "requests_total": 0,
    "requests_in_flight": 0,
    "requests_succeeded": 0,
    "requests_failed": 0,
    "total_processing_ms": 0,
}


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"})


@app.route("/", methods=["GET"])
def root():
    with _lock:
        avg_ms = 0
        if _stats["requests_succeeded"] > 0:
            avg_ms = int(_stats["total_processing_ms"] / _stats["requests_succeeded"])

        snapshot = {
            **_stats,
            "avg_processing_ms": avg_ms,
        }

    return jsonify({
        "service": "Mock Agent API",
        "status": "running",
        "version": APP_VERSION,
        "config": {
            "agent_default_delay_ms": AGENT_DEFAULT_DELAY_MS,
        },
        "stats": snapshot,
    })


@app.route("/agent/process", methods=["POST"])
def agent_process():
    payload = request.get_json(silent=True) or {}
    delay_ms = payload.get("delayMs", AGENT_DEFAULT_DELAY_MS)
    try:
        delay_ms = int(delay_ms)
    except (TypeError, ValueError):
        delay_ms = AGENT_DEFAULT_DELAY_MS

    delay_ms = max(0, min(delay_ms, 30_000))

    request_id = payload.get("requestId") or str(uuid.uuid4())
    user_input = payload.get("input", "")

    start = time.perf_counter()
    with _lock:
        _stats["requests_total"] += 1
        _stats["requests_in_flight"] += 1

    try:
        time.sleep(delay_ms / 1000.0)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        with _lock:
            _stats["requests_succeeded"] += 1
            _stats["total_processing_ms"] += elapsed_ms

        return jsonify({
            "requestId": request_id,
            "status": "ok",
            "inputEcho": user_input[:2000],
            "output": {
                "answer": "This is mock agent output.",
                "citations": [],
            },
            "latencyMs": elapsed_ms,
        })
    except Exception:
        with _lock:
            _stats["requests_failed"] += 1
        return jsonify({"requestId": request_id, "status": "error"}), 500
    finally:
        with _lock:
            _stats["requests_in_flight"] = max(0, _stats["requests_in_flight"] - 1)
