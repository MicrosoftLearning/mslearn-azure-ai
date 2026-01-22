# Exercise - Deploy a containerized backend API to Container Apps

In this exercise, you deploy a containerized backend API that represents an AI document-processing service. You use a private registry for the image, configure secrets and environment variables, and verify the deployment using logs and revision status. The goal is to practice an end-to-end workflow that you can adapt for real AI services.

> [!NOTE]
> This exercise focuses on deployment workflow, not application development. The API implementation is intentionally simple so you can focus on Container Apps concepts.

1. Student does this: Install or update the Container Apps extension and register resource providers.

    ```azurecli
    az upgrade
    az extension add --name containerapp --upgrade

    az provider register --namespace Microsoft.App
    az provider register --namespace Microsoft.OperationalInsights
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

## Deploy the container app and configure secrets

You deploy the API as a container app with external ingress. Because the image is in a private registry, you must configure registry authentication at create time so the first revision can pull the image. You then configure a secret and reference it from an environment variable. This pattern mirrors how AI apps store provider API keys.

1. Create the container app with a system-assigned managed identity and configure registry authentication at create time. The `--registry-identity` flag tells Container Apps to use the app's managed identity to pull images from the specified registry. The CLI automatically assigns the `AcrPull` role when you use this flag with an Azure Container Registry.

    ```bash
    az containerapp create \
        --name $CONTAINER_APP_NAME \
        --resource-group $RESOURCE_GROUP \
        --environment $ACA_ENVIRONMENT \
        --image "$ACR_SERVER/$CONTAINER_IMAGE" \
        --ingress external \
        --target-port $TARGET_PORT \
        --env-vars MODEL_NAME=$MODEL_NAME \
        --registry-server "$ACR_SERVER" \
        --registry-identity system
    ```

1. Create a secret and reference it from an environment variable.

    ```azurecli
    az containerapp secret set -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP \
        --secrets embeddings-api-key=$EMBEDDINGS_API_KEY
    ```

1. Reference the secret from an environment variable. This command creates a new revision, which restarts the app so the secret change takes effect.

    ```azurecli
        az containerapp update -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP \
        --set-env-vars EMBEDDINGS_API_KEY=secretref:embeddings-api-key
    ```

1. List revisions to confirm a new revision was created.

    ```azurecli
    az containerapp revision list -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP -o table
    ```

    The revision name ends with a suffix like `--0000002`, indicating this is the second revision. Container Apps creates a new revision whenever you change environment variables or secrets, which restarts the app with the updated configuration. Old inactive revisions may be pruned over time.

1. Verify the secret is configured by calling the root endpoint.

    ```bash
    curl -s "https://$FQDN/"
    ```

## Verify the deployment

You should validate that the app starts and that ingress works. You also use logs to confirm the app is behaving as expected.

1. Get the app FQDN.

    ```bash
    FQDN=$(az containerapp show -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP \
        --query properties.configuration.ingress.fqdn -o tsv)

    echo "$FQDN"
    ```

1. Call the health endpoint.

    ```bash
    curl -s "https://$FQDN/health"
    ```

1. Test the document processing endpoint.

    ```bash
    curl -s -X POST "https://$FQDN/process" \
        -H "Content-Type: text/plain" \
        -d @document.txt
    ```

1. Review logs for startup and runtime signals. This command shows recent console output only. For historical logs and advanced troubleshooting, logs persist in the Log Analytics workspace associated with your Container Apps environment.

    ```azurecli
    az containerapp logs show -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP
    ```

    Look for gunicorn startup messages showing workers spawned and listening on port 8000. You should also see HTTP request logs from your curl commands (GET /health, POST /process, etc.).

## Clean up resources


