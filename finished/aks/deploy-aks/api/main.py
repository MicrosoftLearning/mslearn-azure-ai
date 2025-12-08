"""
FastAPI application for AKS deployment with Foundry model integration.

This API acts as a gateway between clients and the gpt-4o-mini model hosted in Microsoft Foundry.

Endpoints:
- GET /healthz - Liveness probe
- GET /readyz - Readiness probe (checks Foundry connectivity)
- POST /v1/inference - Synchronous inference endpoint
- POST /v1/inference/stream - Streaming inference endpoint
"""

import os
import json
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="AKS Foundry Gateway API",
    description="Gateway API for gpt-4o-mini inference via Microsoft Foundry",
    version="1.0.0"
)

# Load Foundry credentials from environment
FOUNDRY_ENDPOINT = os.getenv("OPENAI_API_ENDPOINT")
FOUNDRY_KEY = os.getenv("OPENAI_API_KEY")
FOUNDRY_DEPLOYMENT = os.getenv("OPENAI_DEPLOYMENT_NAME")
FOUNDRY_API_VERSION = os.getenv("OPENAI_API_VERSION")

def validate_configuration() -> bool:
    """
    Validate that all required Foundry credentials are loaded.

    Returns:
        bool: True if configuration is valid, False otherwise
    """
    if not FOUNDRY_ENDPOINT:
        logger.error("OPENAI_API_ENDPOINT environment variable not set")
        return False
    if not FOUNDRY_KEY:
        logger.error("OPENAI_API_KEY environment variable not set")
        return False
    logger.info(f"Configuration validated. Endpoint: {FOUNDRY_ENDPOINT}")
    return True

@app.get("/healthz")
async def liveness_probe():
    """
    Liveness probe endpoint - indicates if the pod is alive.

    Returns:
        dict: Status message
    """
    return {"status": "alive", "service": "aks-foundry-gateway"}

@app.get("/readyz")
async def readiness_probe():
    """
    Readiness probe endpoint - verifies downstream Foundry connectivity.

    Returns:
        dict: Status message including Foundry connectivity status

    Raises:
        HTTPException: 503 if Foundry is not reachable
    """
    if not validate_configuration():
        raise HTTPException(status_code=503, detail="Foundry configuration not available")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Simple HEAD request to check endpoint accessibility
            response = await client.head(FOUNDRY_ENDPOINT)
            if response.status_code < 500:
                return {"status": "ready", "foundry_endpoint": FOUNDRY_ENDPOINT}
    except Exception as e:
        logger.warning(f"Foundry connectivity check failed: {e}")

    raise HTTPException(status_code=503, detail="Foundry endpoint not reachable")

@app.post("/v1/inference")
async def synchronous_inference(request: Request):
    """
    Synchronous inference endpoint - sends request to Foundry model and returns response.

    Expected request body:
    {
        "deployment": "gpt-4o-mini",
        "inputs": {
            "prompt": "Your prompt here",
            ...
        },
        "parameters": {
            "temperature": 0.7,
            ...
        },
        "user": "anon|contoso:alice"
    }

    Returns:
        dict: Model inference result

    Raises:
        HTTPException: 400 for invalid requests, 503 for Foundry errors
    """
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse request body: {e}")
        raise HTTPException(status_code=400, detail="Invalid request body")

    prompt = body.get("inputs", {}).get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing 'inputs.prompt' in request body")

    parameters = body.get("parameters", {})

    try:
        result = await call_foundry_inference(prompt, parameters, stream=False)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Inference failed: {e}")
        raise HTTPException(status_code=503, detail="Foundry inference failed")

@app.post("/v1/inference/stream")
async def streaming_inference(request: Request):
    """
    Streaming inference endpoint - streams tokens from Foundry model to client.

    Supports Server-Sent Events (SSE) for streaming responses.

    Expected request body:
    {
        "deployment": "gpt-4o-mini",
        "inputs": {...},
        "parameters": {...},
        "user": "anon|contoso:alice"
    }

    Returns:
        StreamingResponse: Server-Sent Events stream of tokens

    Raises:
        HTTPException: 400 for invalid requests, 503 for Foundry errors
    """
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse request body: {e}")
        raise HTTPException(status_code=400, detail="Invalid request body")

    prompt = body.get("inputs", {}).get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing 'inputs.prompt' in request body")

    parameters = body.get("parameters", {})

    async def event_generator():
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = prepare_foundry_headers()
                payload = {
                    "model": FOUNDRY_DEPLOYMENT,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": parameters.get("temperature", 0.7),
                    "max_tokens": parameters.get("max_tokens", 1024),
                    "top_p": parameters.get("top_p", 1.0),
                    "stream": True
                }

                url = f"{FOUNDRY_ENDPOINT}/openai/deployments/{FOUNDRY_DEPLOYMENT}/chat/completions?api-version={FOUNDRY_API_VERSION}"

                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        logger.error(f"Foundry streaming error: {response.status_code}")
                        yield f"data: {json.dumps({'error': 'Foundry streaming failed'})}\n\n"
                        return

                    async for line in response.aiter_lines():
                        if line.strip():
                            # Pass through Foundry SSE format as-is
                            yield line + "\n"
        except Exception as e:
            logger.error(f"Streaming inference failed: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

async def call_foundry_inference(
    prompt: str,
    parameters: Optional[dict] = None,
    stream: bool = False
) -> dict:
    """
    Call the Foundry inference endpoint.

    Args:
        prompt: The input prompt for the model
        parameters: Optional inference parameters (temperature, max_tokens, etc.)
        stream: Whether to stream the response

    Returns:
        dict: Response from Foundry model

    Raises:
        HTTPException: If the Foundry call fails
    """
    if not parameters:
        parameters = {}

    headers = prepare_foundry_headers()

    # Prepare the request payload for Azure OpenAI API
    payload = {
        "model": FOUNDRY_DEPLOYMENT,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": parameters.get("temperature", 0.7),
        "max_tokens": parameters.get("max_tokens", 1024),
        "top_p": parameters.get("top_p", 1.0),
        "stream": stream
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{FOUNDRY_ENDPOINT}/openai/deployments/{FOUNDRY_DEPLOYMENT}/chat/completions?api-version={FOUNDRY_API_VERSION}"

            response = await client.post(url, json=payload, headers=headers)

            if response.status_code >= 400:
                logger.error(f"Foundry API error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=503, detail=f"Foundry error: {response.status_code}")

            if stream:
                return response.aiter_lines()
            else:
                return response.json()
    except httpx.RequestError as e:
        logger.error(f"Request to Foundry failed: {e}")
        raise HTTPException(status_code=503, detail="Failed to reach Foundry endpoint")

def prepare_foundry_headers() -> dict:
    """
    Prepare request headers for Foundry API calls.

    Returns:
        dict: Headers including authorization and content-type
    """
    return {
        "api-key": FOUNDRY_KEY,
        "Content-Type": "application/json"
    }

if __name__ == "__main__":
    import uvicorn

    # Validate configuration on startup
    if not validate_configuration():
        logger.error("Configuration validation failed. Please check environment variables.")
        exit(1)

    # Run the application
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
