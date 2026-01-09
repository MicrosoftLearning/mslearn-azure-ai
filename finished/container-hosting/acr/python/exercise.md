In this exercise, you create an Azure Container Registry, build a container image using ACR Tasks, and run the image to verify it works correctly. You complete all steps without requiring a local Docker installation.

## Prerequisites

To complete this exercise, you need:

- An Azure subscription with permissions to create resources
- Azure CLI installed and configured, or access to Azure Cloud Shell
- Basic familiarity with Docker concepts and Dockerfiles

## Create an Azure Container Registry

Start by creating a resource group and container registry to store your images. The registry name must be globally unique across all of Azure.

```azurecli
# Set variables for the exercise
RESOURCE_GROUP="rg-acr-exercise"
ACR_NAME="acr$RANDOM"
LOCATION="eastus"

# Create the resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create the container registry with Basic tier
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Basic
```

The Basic SKU provides sufficient capabilities for this exercise. Production workloads typically use Standard or Premium tiers for additional storage, throughput, and features like geo-replication.

Verify the registry was created and note the login server URL:

```azurecli
az acr show --name $ACR_NAME --query loginServer --output tsv
```

The output shows your registry's login server in the format `<registry-name>.azurecr.io`.

## Review the application files

The exercise files include a simple Python API application to containerize. This application simulates an AI inference endpoint with health check and prediction routes.

Review the Python application file in `api/app.py`:

```python
from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route('/health')
def health():
    """Health check endpoint for container orchestrators."""
    return jsonify({
        "status": "healthy",
        "version": os.getenv("APP_VERSION", "1.0.0")
    })

@app.route('/predict')
def predict():
    """Simulated inference endpoint."""
    return jsonify({
        "prediction": "sample-result",
        "confidence": 0.95,
        "model_version": os.getenv("MODEL_VERSION", "v1")
    })

@app.route('/')
def root():
    """Root endpoint with API information."""
    return jsonify({
        "name": "Inference API",
        "version": os.getenv("APP_VERSION", "1.0.0"),
        "endpoints": ["/health", "/predict"]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

Review the `api/Dockerfile` that packages the application:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir flask

# Copy application code
COPY app.py .

# Set environment variables
ENV APP_VERSION=1.0.0
ENV MODEL_VERSION=v1

# Expose the application port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
```

The Dockerfile uses `python:3.11-slim` as the base image, installs Flask, copies the application code, and configures the container to run the API on port 5000.

## Build the image with ACR Tasks

Use a quick task to build the image in Azure without requiring Docker on your local machine. The `az acr build` command uploads your source files, builds the image in the cloud, and pushes it to your registry.

```azurecli
az acr build \
  --registry $ACR_NAME \
  --image inference-api:v1.0.0 \
  ./api
```

Watch the output as ACR Tasks:

1. Packs and uploads your source context to Azure
2. Queues and starts the build task
3. Streams the Docker build output showing each layer
4. Pushes the completed image to your registry
5. Reports the image digest and task status

The build completes entirely in Azure. No local Docker installation is required.

## Verify the image in the registry

Confirm the image exists in your registry by listing repositories and tags.

List all repositories in the registry:

```azurecli
az acr repository list --name $ACR_NAME --output table
```

The output shows the `inference-api` repository you created.

List tags for the inference-api repository:

```azurecli
az acr repository show-tags \
  --name $ACR_NAME \
  --repository inference-api \
  --output table
```

The output shows the `v1.0.0` tag you assigned during the build.

View detailed manifest information including the digest:

```azurecli
az acr repository show-manifests \
  --name $ACR_NAME \
  --repository inference-api \
  --output table
```

Note the digest value. This SHA-256 hash uniquely identifies your image regardless of tags.

## Run the image with ACR Tasks

ACR Tasks can run containers to verify they work correctly. Use the `az acr run` command to execute a command inside your built image.

Run the container and check that Python is available:

```azurecli
az acr run \
  --registry $ACR_NAME \
  --cmd "$ACR_NAME.azurecr.io/inference-api:v1.0.0 python --version" \
  /dev/null
```

The output shows the Python version installed in the container, confirming the base image configuration is correct.

Run the container and verify the application starts:

```azurecli
az acr run \
  --registry $ACR_NAME \
  --cmd "$ACR_NAME.azurecr.io/inference-api:v1.0.0 python -c 'from app import app; print(\"Application loaded successfully\")'" \
  /dev/null
```

This command imports the Flask application and confirms it loads without errors.

## Build with a different tag

Demonstrate versioning by building a new version of the image with an updated tag and version number.

Build the image again with a new version tag:

```azurecli
az acr build \
  --registry $ACR_NAME \
  --image inference-api:v1.1.0 \
  --build-arg APP_VERSION=1.1.0 \
  ./api
```

> [!NOTE]
> The `--build-arg` flag passes build-time variables to the Dockerfile. For this to update the `APP_VERSION` environment variable in the image, the Dockerfile would need an `ARG APP_VERSION` instruction. In this exercise, the environment variable remains at the Dockerfile default, but the image gets a new tag.

List all tags to see both versions:

```azurecli
az acr repository show-tags \
  --name $ACR_NAME \
  --repository inference-api \
  --output table
```

Both `v1.0.0` and `v1.1.0` appear in the output, demonstrating how the registry maintains multiple versions.

## View build history

Review the ACR task run history to see all builds you've performed.

```azurecli
az acr task list-runs \
  --registry $ACR_NAME \
  --output table
```

The output shows each build task with its run ID, status, trigger type, and duration. This history helps you track builds and diagnose issues.

View detailed logs for a specific run by using its run ID:

```azurecli
az acr task logs --registry $ACR_NAME
```

Without specifying a run ID, this command shows logs from the most recent task run.

## Lock a production image

Protect your v1.0.0 image from accidental deletion or modification by locking it.

```azurecli
az acr repository update \
  --name $ACR_NAME \
  --image inference-api:v1.0.0 \
  --write-enabled false
```

Verify the lock is in place:

```azurecli
az acr repository show \
  --name $ACR_NAME \
  --image inference-api:v1.0.0 \
  --output table
```

The `writeEnabled` field shows `False`, indicating the image is protected.

## Clean up resources

When you finish the exercise, remove the resource group to delete all resources and avoid charges.

```azurecli
az group delete --name $RESOURCE_GROUP --yes --no-wait
```

The `--no-wait` flag returns immediately while deletion continues in the background.

## Summary

In this exercise, you:

- Created an Azure Container Registry to store container images
- Built a container image using ACR Tasks without local Docker
- Verified the image in the registry using Azure CLI commands
- Ran the container to validate the application works correctly
- Applied different tags to manage image versions
- Locked a production image to prevent accidental deletion

These skills enable you to manage container images for AI applications entirely from the cloud, supporting consistent builds and reliable deployments.
