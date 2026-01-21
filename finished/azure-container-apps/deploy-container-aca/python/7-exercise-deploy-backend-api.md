# Exercise - Deploy a containerized backend API to Container Apps

In this exercise, you deploy a containerized backend API that represents an AI document-processing service. You use a private registry for the image, configure secrets and environment variables, and verify the deployment using logs and revision status. The goal is to practice an end-to-end workflow that you can adapt for real AI services.

> [!NOTE]
> This exercise focuses on deployment workflow, not application development. The API implementation is intentionally simple so you can focus on Container Apps concepts.

## Set up the environment

You need a resource group and a Container Apps environment to host the API. You also need Azure CLI with the Container Apps extension installed.

1. Create a resource group.

    ```azurecli
    az group create --name rg-aca-exercise --location centralus
    ```

1. Install or update the Container Apps extension and register resource providers.

    ```azurecli
    az upgrade
    az extension add --name containerapp --upgrade

    az provider register --namespace Microsoft.App
    az provider register --namespace Microsoft.OperationalInsights
    ```

1. Create a Container Apps environment.

    ```azurecli
    az containerapp env create \
        --name aca-env-exercise \
        --resource-group rg-aca-exercise \
        --location centralus
    ```

## Create a minimal containerized API

You need a container image to deploy. This repo already includes a small containerized backend API in the `api/` folder. The API simulates an AI document-processing service and reads configuration from environment variables and secrets.

The API supports:

- `GET /health` for health checks
- `POST /process` to simulate processing a document
- `GET /` to return service configuration (including whether the secret is configured)

Environment variables used by the API:

- `MODEL_NAME` (for example: `document-processor`)
- `EMBEDDINGS_API_KEY` (a secret reference in Container Apps)

## Build and push the image to Azure Container Registry

To practice private registry authentication, you build the image in Azure Container Registry. This avoids requiring Docker to run on your local machine. The image name becomes the artifact you deploy to Container Apps.

1. Create an Azure Container Registry.

    ```bash
    ACR_NAME="acraiexercise$RANDOM"

    az acr create \
        --name "$ACR_NAME" \
        --resource-group rg-aca-exercise \
        --location centralus \
        --sku Basic
    ```

1. Build and push the image using ACR.

    ```bash
    az acr build \
    --registry "$ACR_NAME" \
    --image ai-api:v1 \
    --file api/Dockerfile \
    api/
    ```

## Deploy the container app and configure secrets

You deploy the API as a container app with external ingress. Because the image is in a private registry, you must configure registry authentication at create time so the first revision can pull the image. You then configure a secret and reference it from an environment variable. This pattern mirrors how AI apps store provider API keys.

1. Get the registry server name.

    ```bash
    ACR_SERVER=$(az acr show -n "$ACR_NAME" --query loginServer -o tsv)
    ```

1. Create the container app with a system-assigned managed identity and configure registry authentication at create time. The `--registry-identity` flag tells Container Apps to use the app's managed identity to pull images from the specified registry. The CLI automatically assigns the `AcrPull` role when you use this flag with an Azure Container Registry.

    ```bash
    az containerapp create \
        --name ai-api \
        --resource-group rg-aca-exercise \
        --environment aca-env-exercise \
        --image "$ACR_SERVER/ai-api:v1" \
        --ingress external \
        --target-port 8000 \
        --env-vars MODEL_NAME=document-processor \
        --registry-server "$ACR_SERVER" \
        --registry-identity system
    ```

1. Create a secret and reference it from an environment variable.

    ```azurecli
    az containerapp secret set -n ai-api -g rg-aca-exercise \
        --secrets embeddings-api-key="REPLACE_WITH_REAL_VALUE"

    az containerapp update -n ai-api -g rg-aca-exercise \
        --set-env-vars EMBEDDINGS_API_KEY=secretref:embeddings-api-key
    ```

## Verify the deployment

You should validate that the app starts, that ingress works, and that a revision is active. You also use logs to confirm the app is behaving as expected.

1. Get the app FQDN.

    ```bash
    FQDN=$(az containerapp show -n ai-api -g rg-aca-exercise \
        --query properties.configuration.ingress.fqdn -o tsv)

    echo "$FQDN"
    ```

1. Call the health endpoint.

    ```bash
    curl -s "https://$FQDN/health"
    ```

1. Review logs for startup and runtime signals.

    ```azurecli
    az containerapp logs show -n ai-api -g rg-aca-exercise
    ```

1. List revisions and confirm a revision is active.

    ```azurecli
    az containerapp revision list -n ai-api -g rg-aca-exercise
    ```

## Clean up resources

Cleaning up avoids ongoing cost. You delete the resource group, which deletes the Container Apps environment, container app, and registry.

1. Delete the resource group.

    ```azurecli
    az group delete --name rg-aca-exercise
    ```
