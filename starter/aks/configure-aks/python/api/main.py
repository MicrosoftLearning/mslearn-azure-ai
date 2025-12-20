"""
FastAPI application for AKS configuration exercise.

This API demonstrates AKS configuration patterns including:
- ConfigMaps for non-sensitive configuration
- Secrets for sensitive data
- Persistent volumes for log storage

Endpoints:
- GET /healthz - Liveness probe
- GET /readyz - Readiness probe
- GET /secrets - Returns mock secrets stored in AKS
- GET /product/{product_id} - Returns mock product information for a single item
- GET /products - Returns the full list of products
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="AKS Configuration API",
    description="Demo API for AKS configuration patterns",
    version="1.0.0"
)

# Configuration from environment (ConfigMap)
STUDENT_NAME = os.getenv("STUDENT_NAME", "Student")
API_VERSION = os.getenv("API_VERSION", "1.0.0")

# Secrets from environment (Kubernetes Secrets)
SECRET_ENDPOINT = os.getenv("SECRET_ENDPOINT", "")
SECRET_ACCESS_KEY = os.getenv("SECRET_ACCESS_KEY", "")

# Persistent storage path
LOG_PATH = os.getenv("LOG_PATH", "/var/log/api")

# Mock product data
PRODUCTS = [
    {"id": 1, "name": "Laptop Pro", "category": "Electronics", "price": 1299.99, "stock": 45},
    {"id": 2, "name": "Wireless Mouse", "category": "Electronics", "price": 29.99, "stock": 150},
    {"id": 3, "name": "Ergonomic Keyboard", "category": "Electronics", "price": 79.99, "stock": 89},
    {"id": 4, "name": "USB-C Hub", "category": "Accessories", "price": 49.99, "stock": 200},
    {"id": 5, "name": "Monitor 27\"", "category": "Electronics", "price": 399.99, "stock": 32},
    {"id": 6, "name": "Desk Lamp", "category": "Furniture", "price": 34.99, "stock": 78},
    {"id": 7, "name": "Office Chair", "category": "Furniture", "price": 249.99, "stock": 18},
    {"id": 8, "name": "Webcam HD", "category": "Electronics", "price": 89.99, "stock": 64},
    {"id": 9, "name": "Headphones", "category": "Electronics", "price": 149.99, "stock": 102},
    {"id": 10, "name": "Notebook Set", "category": "Office Supplies", "price": 14.99, "stock": 250}
]

def log_request(endpoint: str, method: str = "GET", details: Optional[str] = None):
    """
    Log API requests to persistent storage.

    Args:
        endpoint: The API endpoint being accessed
        method: HTTP method (GET, POST, etc.)
        details: Optional additional details to log
    """
    try:
        # Ensure log directory exists
        log_dir = Path(LOG_PATH)
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create log file path with date
        log_file = log_dir / f"api-requests-{datetime.now().strftime('%Y-%m-%d')}.log"

        # Create log entry
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "method": method,
            "endpoint": endpoint,
            "details": details,
            "student": STUDENT_NAME
        }

        # Append to log file
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        logger.info(f"Logged request: {method} {endpoint}")
    except Exception as e:
        logger.error(f"Failed to log request: {e}")

@app.get("/healthz")
async def liveness_probe():
    """
    Liveness probe endpoint - indicates if the pod is alive.

    Returns:
        dict: Status message
    """
    log_request("/healthz")
    return {
        "status": "alive",
        "service": "aks-config-api",
        "version": API_VERSION,
        "student": STUDENT_NAME
    }

@app.get("/readyz")
async def readiness_probe():
    """
    Readiness probe endpoint - verifies the API is ready to serve requests.

    Returns:
        dict: Status message including configuration status

    Raises:
        HTTPException: 503 if configuration is incomplete
    """
    log_request("/readyz")

    # Check if essential configuration is available
    if not STUDENT_NAME or STUDENT_NAME == "Student":
        raise HTTPException(
            status_code=503,
            detail="Configuration not loaded (STUDENT_NAME not set)"
        )

    # Check if secrets are loaded
    if not SECRET_ENDPOINT or not SECRET_ACCESS_KEY:
        logger.warning("Secrets not fully configured")

    # Check if log path is writable
    try:
        log_dir = Path(LOG_PATH)
        log_dir.mkdir(parents=True, exist_ok=True)
        test_file = log_dir / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        storage_ready = True
    except Exception as e:
        logger.error(f"Persistent storage not writable: {e}")
        storage_ready = False

    return {
        "status": "ready",
        "configuration": {
            "student_name": STUDENT_NAME,
            "api_version": API_VERSION
        },
        "secrets_loaded": bool(SECRET_ENDPOINT and SECRET_ACCESS_KEY),
        "persistent_storage_ready": storage_ready,
        "log_path": LOG_PATH
    }

@app.get("/secrets")
async def get_secrets():
    """
    Returns information about loaded secrets (masked for security).

    This endpoint demonstrates how secrets from Kubernetes Secrets
    are accessed by the application.

    Returns:
        dict: Information about loaded secrets (values masked)
    """
    log_request("/secrets")

    return {
        "message": f"Secrets loaded for {STUDENT_NAME}",
        "secrets": {
            "secret_endpoint": {
                "loaded": bool(SECRET_ENDPOINT),
                "value": SECRET_ENDPOINT[:10] + "..." if SECRET_ENDPOINT and len(SECRET_ENDPOINT) > 10 else "Not Set",
                "length": len(SECRET_ENDPOINT) if SECRET_ENDPOINT else 0
            },
            "secret_access_key": {
                "loaded": bool(SECRET_ACCESS_KEY),
                "value": "***" + SECRET_ACCESS_KEY[-4:] if SECRET_ACCESS_KEY and len(SECRET_ACCESS_KEY) > 4 else "Not Set",
                "length": len(SECRET_ACCESS_KEY) if SECRET_ACCESS_KEY else 0
            }
        },
        "note": "Secret values are masked for security"
    }

@app.get("/product/{product_id}")
async def get_product(product_id: int):
    """
    Get information about a specific product by ID.

    Args:
        product_id: The product ID to retrieve

    Returns:
        dict: Product information

    Raises:
        HTTPException: 404 if product not found
    """
    log_request(f"/product/{product_id}", details=f"Requested product ID: {product_id}")

    # Find product by ID
    product = next((p for p in PRODUCTS if p["id"] == product_id), None)

    if not product:
        raise HTTPException(
            status_code=404,
            detail=f"Product with ID {product_id} not found"
        )

    return {
        "requested_by": STUDENT_NAME,
        "product": product,
        "api_version": API_VERSION
    }

@app.get("/products")
async def get_products():
    """
    Get the full list of products.

    Returns:
        dict: List of all products with summary information
    """
    log_request("/products", details=f"Returned {len(PRODUCTS)} products")

    return {
        "requested_by": STUDENT_NAME,
        "total_products": len(PRODUCTS),
        "products": PRODUCTS,
        "categories": list(set(p["category"] for p in PRODUCTS)),
        "api_version": API_VERSION
    }

@app.get("/logs/summary")
async def get_log_summary():
    """
    Get a summary of logged requests from persistent storage.

    Returns:
        dict: Summary of logged requests

    Raises:
        HTTPException: 500 if unable to read logs
    """
    try:
        log_dir = Path(LOG_PATH)

        if not log_dir.exists():
            return {
                "message": "No logs available yet",
                "log_path": LOG_PATH
            }

        # Get today's log file
        log_file = log_dir / f"api-requests-{datetime.now().strftime('%Y-%m-%d')}.log"

        if not log_file.exists():
            return {
                "message": "No logs for today",
                "log_path": str(log_file)
            }

        # Read and parse log entries
        with open(log_file, "r") as f:
            log_lines = f.readlines()

        log_entries = [json.loads(line.strip()) for line in log_lines if line.strip()]

        # Calculate summary statistics
        endpoint_counts = {}
        for entry in log_entries:
            endpoint = entry.get("endpoint", "unknown")
            endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1

        return {
            "log_path": str(log_file),
            "total_requests": len(log_entries),
            "endpoint_counts": endpoint_counts,
            "first_request": log_entries[0]["timestamp"] if log_entries else None,
            "last_request": log_entries[-1]["timestamp"] if log_entries else None,
            "student": STUDENT_NAME
        }
    except Exception as e:
        logger.error(f"Failed to read logs: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read logs: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting API for student: {STUDENT_NAME}")
    logger.info(f"API version: {API_VERSION}")
    logger.info(f"Log path: {LOG_PATH}")
    logger.info(f"Secrets loaded: {bool(SECRET_ENDPOINT and SECRET_ACCESS_KEY)}")

    # Run the application
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
