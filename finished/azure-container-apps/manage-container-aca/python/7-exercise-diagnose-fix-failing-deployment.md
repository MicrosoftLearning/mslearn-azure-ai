# Exercise - Diagnose and fix a failing deployment

In this exercise, you troubleshoot a failing container app and apply targeted fixes. You use revision status, logs, and the Azure CLI to isolate deployment issues. This workflow is common in AI solutions because startup behavior changes frequently when you update models and dependencies.

Tasks performed in this exercise:

- Deploy a working container app using the API from the deploy exercise
- Introduce and diagnose a missing environment variable error
- Introduce and diagnose a secret misconfiguration
- Introduce and diagnose an ingress configuration issue
- Query Log Analytics for historical troubleshooting data
- Clean up Azure resources

This exercise takes approximately **30-40** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription with permissions to deploy the necessary Azure services.
- The latest version of the [Azure CLI](/cli/azure/install-azure-cli).
- A working deployment from the "Deploy a containerized backend API to Container Apps" exercise, or you can run the setup script below to create one.

## Deploy a working container app

If you completed the deploy exercise and still have the resources, skip to the next section. Otherwise, follow these steps to deploy a working container app.

1. Clone or download the exercise files and navigate to the `finished/azure-container-apps/deploy-container-aca/python` folder.

1. Run the deployment script to create the Azure Container Registry and Container Apps environment.

    ```bash
    bash azdeploy.sh
    ```

    Select option **1** to create the ACR and build the image, then option **2** to create the Container Apps environment.

1. Load the environment variables.

    ```bash
    source .env
    ```

1. Create the container app.

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

1. Configure the secret and environment variable.

    ```bash
    az containerapp secret set -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP \
        --secrets embeddings-api-key=$EMBEDDINGS_API_KEY

    az containerapp update -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP \
        --set-env-vars EMBEDDINGS_API_KEY=secretref:embeddings-api-key
    ```

1. Verify the deployment is working.

    ```bash
    FQDN=$(az containerapp show -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP \
        --query properties.configuration.ingress.fqdn -o tsv)

    curl -s "https://$FQDN/health"
    ```

    You should see `{"status":"healthy"}`.

## Diagnose a missing environment variable

When a container app depends on an environment variable that isn't set, the app may fail to start or behave unexpectedly. In this section, you remove a required environment variable and observe the symptoms.

1. Update the container app to remove the `MODEL_NAME` environment variable. The `--replace-env-vars` flag replaces all environment variables, so you must include any variables you want to keep.

    ```bash
    az containerapp update -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP \
        --replace-env-vars EMBEDDINGS_API_KEY=secretref:embeddings-api-key
    ```

1. List revisions to confirm a new revision was created.

    ```bash
    az containerapp revision list -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP -o table
    ```

1. Check the root endpoint to observe the misconfiguration. The `model.name` field now shows the default value instead of the configured value.

    ```bash
    curl -s "https://$FQDN/" | jq .
    ```

    The response shows `"name": "not-configured"` (the default) instead of `"gpt-4o-mini"` which you configured. In a real AI app, this could mean the wrong model is being used.

1. View the current environment variables to confirm `MODEL_NAME` is missing.

    ```bash
    az containerapp show -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP \
        --query "properties.template.containers[0].env" -o table
    ```

1. Fix the issue by adding the `MODEL_NAME` environment variable back.

    ```bash
    az containerapp update -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP \
        --set-env-vars MODEL_NAME=$MODEL_NAME
    ```

1. Verify the fix by checking the root endpoint again.

    ```bash
    curl -s "https://$FQDN/" | jq .model
    ```

    The response should now show the configured model name.

You diagnosed and fixed a missing environment variable. Next, you diagnose a secret misconfiguration.

## Diagnose a secret misconfiguration

Secrets in Container Apps are referenced by name. If you reference a secret that doesn't exist, the revision fails to provision. In this section, you introduce an invalid secret reference.

1. Update the container app to reference a secret that doesn't exist.

    ```bash
    az containerapp update -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP \
        --set-env-vars EMBEDDINGS_API_KEY=secretref:wrong-secret-name
    ```

    This command fails because the secret `wrong-secret-name` doesn't exist. The CLI validates secret references before creating the revision.

1. View the error message. The CLI output indicates the secret reference is invalid.

    > [!NOTE]
    > Container Apps validates secret references at deployment time, which prevents broken revisions. This is different from Kubernetes, where you might see a pod stuck in a pending state due to missing secrets.

1. List the secrets currently configured on the container app.

    ```bash
    az containerapp secret list -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP -o table
    ```

1. Confirm the correct secret name is `embeddings-api-key`, then fix the environment variable reference.

    ```bash
    az containerapp update -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP \
        --set-env-vars EMBEDDINGS_API_KEY=secretref:embeddings-api-key
    ```

1. Verify the fix by checking the root endpoint.

    ```bash
    curl -s "https://$FQDN/" | jq .secrets
    ```

    The response should show `"embeddings_api_key_configured": true`.

You diagnosed and fixed a secret misconfiguration. Next, you diagnose an ingress issue.

## Diagnose an ingress configuration issue

Container Apps uses the `target-port` setting to route traffic to your container. If the port doesn't match what your application listens on, requests fail. In this section, you introduce a port mismatch.

1. Update the container app to use the wrong target port.

    ```bash
    az containerapp ingress update -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP \
        --target-port 3000
    ```

1. Try to access the health endpoint.

    ```bash
    curl -s "https://$FQDN/health"
    ```

    The request fails or times out because Container Apps is routing traffic to port 3000, but the application listens on port 8000.

1. Check the current ingress configuration.

    ```bash
    az containerapp show -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP \
        --query "properties.configuration.ingress" -o yaml
    ```

    Notice the `targetPort` is set to 3000.

1. Check the container logs to see if the application is running.

    ```bash
    az containerapp logs show -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP
    ```

    You should see gunicorn startup messages indicating the app is listening on port 8000, confirming the mismatch.

1. Fix the ingress configuration by setting the correct target port.

    ```bash
    az containerapp ingress update -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP \
        --target-port 8000
    ```

1. Verify the fix by calling the health endpoint.

    ```bash
    curl -s "https://$FQDN/health"
    ```

    You should see `{"status":"healthy"}`.

You diagnosed and fixed an ingress configuration issue. Next, you learn how to query historical logs.

## Query Log Analytics for historical troubleshooting

Console logs shown by `az containerapp logs show` are recent only. For historical troubleshooting, logs persist in the Log Analytics workspace associated with your Container Apps environment.

1. Get the Log Analytics workspace ID from the Container Apps environment.

    ```bash
    WORKSPACE_ID=$(az containerapp env show -n $ACA_ENVIRONMENT -g $RESOURCE_GROUP \
        --query properties.appLogsConfiguration.logAnalyticsConfiguration.customerId -o tsv)

    echo "Workspace ID: $WORKSPACE_ID"
    ```

1. Query the console logs for your container app. This returns the last 50 log entries.

    ```bash
    az monitor log-analytics query -w $WORKSPACE_ID \
        --analytics-query "ContainerAppConsoleLogs_CL | where ContainerAppName_s == '$CONTAINER_APP_NAME' | order by TimeGenerated desc | take 50" \
        -o table
    ```

    > [!NOTE]
    > Log Analytics data may take a few minutes to appear after events occur. If you don't see recent logs, wait a few minutes and try again.

1. Query for error-level logs specifically.

    ```bash
    az monitor log-analytics query -w $WORKSPACE_ID \
        --analytics-query "ContainerAppConsoleLogs_CL | where ContainerAppName_s == '$CONTAINER_APP_NAME' and Log_s contains 'error' | order by TimeGenerated desc | take 20" \
        -o table
    ```

These queries help you investigate issues that occurred in the past, even after container restarts or revision changes.

## Verify the final state

After completing all troubleshooting scenarios, confirm the application is fully functional.

1. Test all endpoints.

    ```bash
    echo "Health check:"
    curl -s "https://$FQDN/health"

    echo -e "\n\nService info:"
    curl -s "https://$FQDN/" | jq .

    echo -e "\n\nDocument processing:"
    curl -s -X POST "https://$FQDN/process" \
        -H "Content-Type: application/json" \
        -d '{"content": "Test document for processing", "filename": "test.txt"}'
    ```

1. Verify the revision is healthy.

    ```bash
    az containerapp revision list -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP -o table
    ```

    The active revision should show `Healthy` in the HealthState column.

## Clean up resources

Cleaning up avoids ongoing cost. Delete the resource group, which deletes the Container Apps environment, container app, and registry.

```bash
az group delete --name $RESOURCE_GROUP --no-wait --yes
```

## Troubleshooting

If you encounter issues during this exercise, try these steps:

**Container app not responding**
- Check if the revision is active: `az containerapp revision list -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP -o table`
- Verify ingress is configured: `az containerapp show -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP --query properties.configuration.ingress`

**Cannot see logs**
- Console logs are recent only. Use Log Analytics for historical data.
- Log Analytics data may take 2-5 minutes to appear.

**Secret reference errors**
- List available secrets: `az containerapp secret list -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP`
- Secret names are case-sensitive.

**Environment variables not taking effect**
- Container Apps creates a new revision when you change environment variables. Verify the new revision is active.
- Use `--replace-env-vars` carefully—it replaces all environment variables, not just the ones you specify.
