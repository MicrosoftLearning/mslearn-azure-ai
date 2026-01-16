"""Document Processing API - Mock service for Azure App Service exercise."""

import json
import logging
import os
import uuid
from datetime import datetime

from flask import Flask, jsonify, request

app = Flask(__name__)

# Configuration from environment variables
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MAX_DOCUMENT_SIZE_MB = int(os.getenv("MAX_DOCUMENT_SIZE_MB", "50"))
PROCESSING_TIMEOUT_SECONDS = int(os.getenv("PROCESSING_TIMEOUT_SECONDS", "30"))

# Persistent storage path (App Service mounts /home when WEBSITES_ENABLE_APP_SERVICE_STORAGE=true)
STORAGE_PATH = os.getenv("STORAGE_PATH", "/home/processed")

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def ensure_storage_directory():
    """Create storage directory if it doesn't exist."""
    try:
        os.makedirs(STORAGE_PATH, exist_ok=True)
        return True
    except Exception as e:
        logger.warning(f"Could not create storage directory: {e}")
        return False


@app.route("/", methods=["GET"])
def root():
    """Health check and service information endpoint."""
    logger.info("Health check requested")
    return jsonify(
        {
            "service": "Document Processing API",
            "status": "running",
            "environment": ENVIRONMENT,
            "version": "1.0.0",
            "config": {
                "max_document_size_mb": MAX_DOCUMENT_SIZE_MB,
                "processing_timeout_seconds": PROCESSING_TIMEOUT_SECONDS,
                "log_level": LOG_LEVEL,
            },
        }
    )


@app.route("/health", methods=["GET"])
def health():
    """Simple health check endpoint."""
    return jsonify({"status": "healthy"})


@app.route("/process", methods=["POST"])
def process_document():
    """
    Process a document and return mock analysis results.

    Accepts JSON with document content or a file upload.
    Returns mock processing results including extracted entities,
    sentiment, and key phrases.
    """
    logger.info("Document processing request received")

    # Generate unique document ID
    doc_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()

    # Get document content from request
    if request.is_json:
        data = request.get_json()
        content = data.get("content", "")
        filename = data.get("filename", "document.txt")
    elif request.files:
        file = request.files.get("file")
        if file:
            content = file.read().decode("utf-8", errors="ignore")
            filename = file.filename
        else:
            return jsonify({"error": "No file provided"}), 400
    else:
        content = request.data.decode("utf-8", errors="ignore") or "Sample document"
        filename = "document.txt"

    # Check document size
    content_size_mb = len(content.encode("utf-8")) / (1024 * 1024)
    if content_size_mb > MAX_DOCUMENT_SIZE_MB:
        logger.warning(f"Document too large: {content_size_mb:.2f} MB")
        return (
            jsonify(
                {
                    "error": f"Document exceeds maximum size of {MAX_DOCUMENT_SIZE_MB} MB"
                }
            ),
            413,
        )

    logger.info(f"Processing document: {filename} ({len(content)} characters)")

    # Generate mock processing results
    word_count = len(content.split())
    char_count = len(content)

    # Mock entity extraction
    mock_entities = [
        {"text": "Azure", "type": "Technology", "confidence": 0.95},
        {"text": "App Service", "type": "Service", "confidence": 0.92},
        {"text": "container", "type": "Concept", "confidence": 0.88},
    ]

    # Mock key phrases
    mock_key_phrases = [
        "document processing",
        "cloud deployment",
        "container hosting",
        "managed service",
    ]

    # Mock sentiment analysis
    mock_sentiment = {
        "overall": "neutral",
        "confidence": 0.78,
        "scores": {"positive": 0.25, "neutral": 0.65, "negative": 0.10},
    }

    # Build result
    result = {
        "document_id": doc_id,
        "filename": filename,
        "processed_at": timestamp,
        "environment": ENVIRONMENT,
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

    # Save result to persistent storage if available
    storage_available = ensure_storage_directory()
    if storage_available:
        try:
            result_path = os.path.join(STORAGE_PATH, f"{doc_id}.json")
            with open(result_path, "w") as f:
                json.dump(result, f, indent=2)
            result["storage"] = {"saved": True, "path": result_path}
            logger.info(f"Result saved to {result_path}")
        except Exception as e:
            logger.error(f"Failed to save result: {e}")
            result["storage"] = {"saved": False, "error": str(e)}
    else:
        result["storage"] = {"saved": False, "reason": "Storage not available"}

    logger.info(f"Document processed successfully: {doc_id}")
    return jsonify(result)


@app.route("/documents", methods=["GET"])
def list_documents():
    """List all processed documents from storage."""
    logger.info("Listing processed documents")

    if not ensure_storage_directory():
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
                        "created_at": datetime.fromtimestamp(
                            stat.st_ctime
                        ).isoformat(),
                    }
                )
        return jsonify({"documents": files, "count": len(files)})
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        return jsonify({"documents": [], "error": str(e)})


@app.route("/documents/<doc_id>", methods=["GET"])
def get_document(doc_id):
    """Retrieve a processed document by ID."""
    logger.info(f"Retrieving document: {doc_id}")

    filepath = os.path.join(STORAGE_PATH, f"{doc_id}.json")

    if not os.path.exists(filepath):
        return jsonify({"error": "Document not found"}), 404

    try:
        with open(filepath, "r") as f:
            return jsonify(json.load(f))
    except Exception as e:
        logger.error(f"Failed to read document: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    logger.info(f"Starting Document Processing API in {ENVIRONMENT} environment")
    logger.info(f"Configuration: MAX_SIZE={MAX_DOCUMENT_SIZE_MB}MB, TIMEOUT={PROCESSING_TIMEOUT_SECONDS}s")

    # Ensure storage directory exists
    ensure_storage_directory()

    # Run the application
    port = int(os.getenv("PORT", "80"))
    app.run(host="0.0.0.0", port=port)
