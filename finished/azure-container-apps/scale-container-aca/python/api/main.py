"""AI document processing mock API for Azure Container Apps exercises."""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request

app = Flask(__name__)

# Configuration from environment variables (set by Container Apps)
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MODEL_NAME = os.getenv("MODEL_NAME", "not-configured")
EMBEDDINGS_API_KEY = os.getenv("EMBEDDINGS_API_KEY")

MAX_DOCUMENT_SIZE_MB = int(os.getenv("MAX_DOCUMENT_SIZE_MB", "10"))
PROCESSING_TIMEOUT_SECONDS = int(os.getenv("PROCESSING_TIMEOUT_SECONDS", "15"))

# Container Apps filesystem is ephemeral by default; use /tmp for demo storage.
STORAGE_PATH = os.getenv("STORAGE_PATH", "/tmp/processed")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _ensure_storage_directory() -> bool:
    try:
        os.makedirs(STORAGE_PATH, exist_ok=True)
        return True
    except Exception as exc:
        logger.warning("Could not create storage directory: %s", exc)
        return False


def _embeddings_key_configured() -> bool:
    return bool(EMBEDDINGS_API_KEY and EMBEDDINGS_API_KEY.strip())


@app.route("/", methods=["GET"])
def root():
    """Service info endpoint for quick verification."""
    logger.info("Service info requested")
    return jsonify(
        {
            "service": "AI Document Processing API",
            "status": "running",
            "version": "1.0.0",
            "environment": ENVIRONMENT,
            "model": {"name": MODEL_NAME},
            "secrets": {"embeddings_api_key_configured": _embeddings_key_configured()},
            "config": {
                "max_document_size_mb": MAX_DOCUMENT_SIZE_MB,
                "processing_timeout_seconds": PROCESSING_TIMEOUT_SECONDS,
                "log_level": LOG_LEVEL,
                "storage_path": STORAGE_PATH,
            },
        }
    )


@app.route("/health", methods=["GET"])
def health():
    """Simple health check endpoint used by the exercise."""
    return jsonify({"status": "healthy"})


@app.route("/process", methods=["POST"])
def process_document():
    """Mock document processing endpoint.

    Accepts:
    - JSON: {"content": "...", "filename": "..."}
    - multipart/form-data with a file named "file"

    Returns:
    - mock entities, key phrases, sentiment, and a generated document id.
    """
    logger.info("Document processing request received")

    doc_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if request.is_json:
        data = request.get_json(silent=True) or {}
        content = data.get("content", "")
        filename = data.get("filename", "document.txt")
    elif request.files:
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No file provided"}), 400
        content = file.read().decode("utf-8", errors="ignore")
        filename = file.filename or "document.txt"
    else:
        content = request.data.decode("utf-8", errors="ignore") or "Sample document"
        filename = "document.txt"

    content_size_mb = len(content.encode("utf-8")) / (1024 * 1024)
    if content_size_mb > MAX_DOCUMENT_SIZE_MB:
        logger.warning("Document too large: %.2f MB", content_size_mb)
        return (
            jsonify({"error": f"Document exceeds maximum size of {MAX_DOCUMENT_SIZE_MB} MB"}),
            413,
        )

    logger.info("Processing document: %s (%s chars)", filename, len(content))

    word_count = len(content.split())
    char_count = len(content)

    mock_entities = [
        {"text": "Azure", "type": "Technology", "confidence": 0.95},
        {"text": "Container Apps", "type": "Service", "confidence": 0.93},
        {"text": "document", "type": "Concept", "confidence": 0.87},
    ]

    mock_key_phrases = [
        "document processing",
        "container deployment",
        "secrets and configuration",
        "revision management",
    ]

    mock_sentiment = {
        "overall": "neutral",
        "confidence": 0.78,
        "scores": {"positive": 0.22, "neutral": 0.68, "negative": 0.10},
    }

    result = {
        "document_id": doc_id,
        "filename": filename,
        "processed_at": timestamp,
        "environment": ENVIRONMENT,
        "model": {"name": MODEL_NAME},
        "secrets": {"embeddings_api_key_configured": _embeddings_key_configured()},
        "statistics": {
            "character_count": char_count,
            "word_count": word_count,
            "size_bytes": len(content.encode("utf-8")),
        },
        "analysis": {
            "entities": mock_entities,
            "key_phrases": mock_key_phrases,
            "sentiment": mock_sentiment,
        },
        "processing_config": {
            "timeout_seconds": PROCESSING_TIMEOUT_SECONDS,
            "max_size_mb": MAX_DOCUMENT_SIZE_MB,
        },
    }

    storage_available = _ensure_storage_directory()
    if storage_available:
        try:
            result_path = os.path.join(STORAGE_PATH, f"{doc_id}.json")
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            result["storage"] = {"saved": True, "path": result_path}
            logger.info("Result saved to %s", result_path)
        except Exception as exc:
            logger.error("Failed to save result: %s", exc)
            result["storage"] = {"saved": False, "error": str(exc)}
    else:
        result["storage"] = {"saved": False, "reason": "Storage not available"}

    return jsonify(result)


@app.route("/documents", methods=["GET"])
def list_documents():
    """List processed documents stored in the container's local filesystem."""
    logger.info("Listing processed documents")

    if not _ensure_storage_directory():
        return jsonify({"documents": [], "error": "Storage not available"})

    try:
        files = []
        for filename in os.listdir(STORAGE_PATH):
            if filename.endswith(".json"):
                filepath = os.path.join(STORAGE_PATH, filename)
                stat = os.stat(filepath)
                files.append(
                    {
                        "document_id": filename.replace(".json", ""),
                        "size_bytes": stat.st_size,
                        "created_at": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                    }
                )
        return jsonify({"documents": files, "count": len(files)})
    except Exception as exc:
        logger.error("Failed to list documents: %s", exc)
        return jsonify({"documents": [], "error": str(exc)})


@app.route("/documents/<doc_id>", methods=["GET"])
def get_document(doc_id: str):
    """Retrieve a processed document by id."""
    logger.info("Retrieving document: %s", doc_id)

    filepath = os.path.join(STORAGE_PATH, f"{doc_id}.json")
    if not os.path.exists(filepath):
        return jsonify({"error": "Document not found"}), 404

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception as exc:
        logger.error("Failed to read document: %s", exc)
        return jsonify({"error": str(exc)}), 500


def _log_startup_summary() -> None:
    logger.info("Starting AI Document Processing API")
    logger.info("ENVIRONMENT=%s LOG_LEVEL=%s", ENVIRONMENT, LOG_LEVEL)
    logger.info("MODEL_NAME=%s", MODEL_NAME)
    logger.info("EMBEDDINGS_API_KEY configured: %s", _embeddings_key_configured())


if __name__ == "__main__":
    _log_startup_summary()
    _ensure_storage_directory()

    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
