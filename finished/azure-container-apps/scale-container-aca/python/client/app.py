#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp
from flask import Flask, jsonify, render_template, request


# Suppress Flask/Werkzeug request logging (the constant "GET /api/..." lines)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

LAB_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = LAB_DIR / ".env"


def _load_dotenv_exports(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _az_json(args: list[str]) -> Any:
    completed = subprocess.run(args, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "").strip() or "Azure CLI command failed")
    return json.loads(completed.stdout or "null")


@dataclass
class LoadConfig:
    target_url: str
    concurrency: int
    duration_seconds: int
    delay_ms: int


class LoadRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._state: Dict[str, Any] = {
            "running": False,
            "startedAt": None,
            "endedAt": None,
            "targetUrl": None,
            "concurrency": 0,
            "durationSeconds": 0,
            "delayMs": 0,
            "sent": 0,
            "succeeded": 0,
            "failed": 0,
            "lastError": None,
        }

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def stop(self) -> None:
        self._stop_event.set()

    def start(self, cfg: LoadConfig) -> None:
        with self._lock:
            if self._state["running"]:
                raise RuntimeError("Load test already running")

            self._stop_event.clear()
            self._state.update(
                {
                    "running": True,
                    "startedAt": int(time.time()),
                    "endedAt": None,
                    "targetUrl": cfg.target_url,
                    "concurrency": cfg.concurrency,
                    "durationSeconds": cfg.duration_seconds,
                    "delayMs": cfg.delay_ms,
                    "sent": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "lastError": None,
                }
            )

        self._thread = threading.Thread(target=self._run_thread, args=(cfg,), daemon=True)
        self._thread.start()

    def _bump(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._state[key] = int(self._state.get(key, 0)) + amount

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._state["lastError"] = message

    def _finish(self) -> None:
        with self._lock:
            self._state["running"] = False
            self._state["endedAt"] = int(time.time())

    def _run_thread(self, cfg: LoadConfig) -> None:
        try:
            asyncio.run(self._run_async(cfg))
        except Exception as exc:  # noqa: BLE001
            self._set_error(str(exc))
        finally:
            self._finish()

    async def _run_async(self, cfg: LoadConfig) -> None:
        timeout = aiohttp.ClientTimeout(total=max(10, cfg.delay_ms / 1000 + 10))

        async with aiohttp.ClientSession(timeout=timeout) as session:
            end_time = time.time() + cfg.duration_seconds

            async def worker(worker_id: int) -> None:
                while time.time() < end_time and not self._stop_event.is_set():
                    self._bump("sent")
                    try:
                        async with session.post(
                            cfg.target_url,
                            json={
                                "input": f"hello from worker {worker_id}",
                                "delayMs": cfg.delay_ms,
                            },
                        ) as resp:
                            if 200 <= resp.status < 300:
                                await resp.read()
                                self._bump("succeeded")
                            else:
                                await resp.read()
                                self._bump("failed")
                    except Exception as exc:  # noqa: BLE001
                        self._bump("failed")
                        self._set_error(str(exc))

            tasks = [asyncio.create_task(worker(i)) for i in range(cfg.concurrency)]
            await asyncio.gather(*tasks)


app = Flask(__name__)
runner = LoadRunner()


@app.get("/")
def index():
    env = _load_dotenv_exports(ENV_FILE)

    resource_group = env.get("RESOURCE_GROUP", "")
    container_app_name = env.get("CONTAINER_APP_NAME", "")

    base_url = env.get("CONTAINER_APP_URL", "").rstrip("/")
    default_target = f"{base_url}/agent/process" if base_url else ""

    return render_template(
        "index.html",
        envFound=ENV_FILE.exists(),
        resourceGroup=resource_group,
        containerAppName=container_app_name,
        containerAppUrl=base_url,
        defaultTargetUrl=default_target,
    )


@app.get("/api/env")
def get_env():
    return jsonify(_load_dotenv_exports(ENV_FILE))


@app.get("/api/revisions")
def revisions():
    env = _load_dotenv_exports(ENV_FILE)
    rg = request.args.get("resourceGroup") or env.get("RESOURCE_GROUP")
    name = request.args.get("containerAppName") or env.get("CONTAINER_APP_NAME")

    if not rg or not name:
        return jsonify({"error": "Missing RESOURCE_GROUP or CONTAINER_APP_NAME"}), 400

    try:
        data = _az_json(["az", "containerapp", "revision", "list", "--resource-group", rg, "--name", name, "-o", "json"])
        return jsonify({"items": data})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.get("/api/replicas")
def replicas():
    env = _load_dotenv_exports(ENV_FILE)
    rg = request.args.get("resourceGroup") or env.get("RESOURCE_GROUP")
    name = request.args.get("containerAppName") or env.get("CONTAINER_APP_NAME")

    if not rg or not name:
        return jsonify({"error": "Missing RESOURCE_GROUP or CONTAINER_APP_NAME"}), 400

    try:
        data = _az_json(["az", "containerapp", "replica", "list", "--resource-group", rg, "--name", name, "-o", "json"])
        items = data if isinstance(data, list) else []
        return jsonify({"count": len(items), "items": items})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.post("/api/load/start")
def load_start():
    body = request.get_json(silent=True) or {}

    target_url = str(body.get("targetUrl", "")).strip()
    concurrency = int(body.get("concurrency", 25))
    duration_seconds = int(body.get("durationSeconds", 30))
    delay_ms = int(body.get("delayMs", 500))

    if not target_url:
        return jsonify({"error": "targetUrl is required"}), 400

    concurrency = max(1, min(concurrency, 500))
    duration_seconds = max(1, min(duration_seconds, 600))
    delay_ms = max(0, min(delay_ms, 30_000))

    try:
        runner.start(
            LoadConfig(
                target_url=target_url,
                concurrency=concurrency,
                duration_seconds=duration_seconds,
                delay_ms=delay_ms,
            )
        )
        return jsonify(runner.status())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 409


@app.post("/api/load/stop")
def load_stop():
    runner.stop()
    return jsonify({"ok": True})


@app.get("/api/load/status")
def load_status():
    return jsonify(runner.status())


if __name__ == "__main__":
    # Local-only dashboard
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
