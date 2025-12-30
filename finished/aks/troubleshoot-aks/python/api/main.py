"""
FastAPI application for AKS troubleshooting exercise.

This API is intentionally simple to focus on Kubernetes troubleshooting skills.
It requires the API_KEY environment variable to start successfully.

Endpoints:
- GET /healthz - Liveness probe
- GET /readyz - Readiness probe
- GET /api/info - Returns application info
"""

import os
import sys
import logging
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Check for required environment variable at startup
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    logger.error("FATAL: API_KEY environment variable is not set. Exiting.")
    sys.exit(1)

# Initialize FastAPI app
app = FastAPI(
    title="Troubleshoot API",
    description="Demo API for AKS troubleshooting exercise",
    version="1.0.0"
)

# Track startup time
STARTUP_TIME = datetime.utcnow().isoformat()

logger.info("Application started successfully")
logger.info(f"API_KEY is configured (length: {len(API_KEY)})")


@app.get("/healthz")
async def healthz():
    """
    Liveness probe endpoint.
    Returns 200 if the application is running.
    """
    logger.info("GET /healthz - Health check requested")
    return JSONResponse(
        status_code=200,
        content={"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
    )


@app.get("/readyz")
async def readyz():
    """
    Readiness probe endpoint.
    Returns 200 if the application is ready to receive traffic.
    """
    logger.info("GET /readyz - Readiness check requested")
    return JSONResponse(
        status_code=200,
        content={"status": "ready", "timestamp": datetime.utcnow().isoformat()}
    )


@app.get("/api/info")
async def info():
    """
    Returns application information.
    """
    logger.info("GET /api/info - Info requested")
    return JSONResponse(
        status_code=200,
        content={
            "app": "Troubleshoot API",
            "version": "1.0.0",
            "startup_time": STARTUP_TIME,
            "api_key_configured": True,
            "message": "Application is running correctly!"
        }
    )
