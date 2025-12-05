I'm working on an exercise to go along with a module of content covering deploying apps to AKS. Trying to make the content/exercise as AI-relevant as possible. The proposed exercise would deploy a FastAPI to AKS that sits between the client and an inference model hosted in Microsoft Foundry.

## Architecture

- The API would be containerized and hosted in Azure Container Registry
- AKS will host the container
- The inference model will be gpt-4o-mini and hosted in Microsoft Foundry
- The client will be a console app that gives students different options to interact with the API.

## API details

The API will manage auth to the model. It should have the following functionality/endpoints.

1. Liveness & readiness
    - GET /healthz — returns 200 OK when the pod is alive; include dependency checks (e.g., Foundry credentials loaded, network reachable).
    - GET /readyz — verifies downstream (Foundry) connectivity and any required caches/secrets.

2. Basic inference (synchronous)

 - POST /v1/inference — your primary gateway endpoint.

 - Body: { "deployment": "gpt-4o-mini", "inputs": {...}, "parameters": {...}, "user": "anon|contoso:alice" }
Behavior:

Validate & normalize requests.
Inject headers/tokens required by Foundry’s Model Inference API.
Enforce per‑user/per‑app quotas and rate limits.
Optional server‑side caching of idempotent calls (e.g., embeddings).

Downstream: Foundry unified inference endpoint

3. Streaming responses (chat / generation)

- POST /v1/inference/stream — websockets or Server‑Sent Events (SSE) to stream tokens/chunks to the client for chat UX.

Streaming support mirrors common client expectations and lets you demonstrate backpressure and cancellation.

## Client details

A console app that has a menu that lets the student verify the health of the pod and the downstream connectivity of the model. It should also have an option that lets the student have a chat session with the model. This will be start as a console-app only and possibly transition to a tkinter app if that makes better sense from a usability standpoint.

## Solution

The API and console app should probably be in separate folders to make it easy to separate the varying requirements. These should both be written in Python.

The API folder should contain the app and the necessary Docker information for the deployment to Container Registry. The API will contain the host and API key information for the model. That should be stored in a .env file in the project folder.

These will be short-lived apps so I don't think we need to secure the API with a key.

## Deployment

In the past I've used a combination of AZD and AZ CLI commands to do the deployments. I only need the script to deploy the model, use ACR Tasks to put the containerized API into ACR, and create the AKS instance. The AKS instance should be the smallest tier/SKU. Students will be creating the deployment manifest for AKS and finalizing that deployment.

In the past I've used the combination of AZD and bash script with CLI this link has an example: https://github.com/MicrosoftLearning/mslearn-ai-language/tree/main/Labfiles/11-voice-live-agent/python

There are more recent examples of AZ CLI deployments in this repo, look at the azdeploy.sh files in the finished/amr folders.

During deployment the model name, endpoint, and API key should be saved to the .env file for the API.
