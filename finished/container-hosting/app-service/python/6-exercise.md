In this exercise, you deploy a document processing service to Azure App Service. You configure the container runtime settings, application settings, and diagnostic logging. Then you verify the deployment and use diagnostic tools to inspect the running application.

## Prerequisites

To complete this exercise, you need:

- An Azure subscription with permissions to create resources
- Azure CLI installed and signed in to your subscription


## Create the resource group

Create a resource group to contain all resources for this exercise:

```azurecli
az group create \
    --name rg-docprocessor \
    --location eastus
```

## Create the container registry

Create an Azure Container Registry to store the container image:

```azurecli
az acr create \
    --resource-group rg-docprocessor \
    --name acrdocprocessor$RANDOM \
    --sku Basic
```

Note the registry name from the output. You'll use it in subsequent commands. Store it in a variable for convenience:

```azurecli
ACR_NAME=$(az acr list --resource-group rg-docprocessor --query "[0].name" --output tsv)
echo "Registry name: $ACR_NAME"
```

## Build and push the container image

For this exercise, use a sample container image that simulates a document processing service. The image provides a simple HTTP API that accepts requests and returns processing results.

Import a sample Python web application image to your registry:

```azurecli
az acr import \
    --name $ACR_NAME \
    --source mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
    --image docprocessor:v1
```

This command imports a sample container image into your registry. In a production scenario, you would build your own image from a Dockerfile and push it to the registry.

## Create the App Service plan

Create an App Service plan that supports Linux containers:

```azurecli
az appservice plan create \
    --resource-group rg-docprocessor \
    --name plan-docprocessor \
    --is-linux \
    --sku B1
```

The B1 SKU provides a basic tier that supports always-on and custom containers. Production workloads typically use Standard (S1) or Premium tiers for better performance and features.

## Create the web app

Create a Web App for Containers configured to pull from your container registry:

```azurecli
az webapp create \
    --resource-group rg-docprocessor \
    --plan plan-docprocessor \
    --name app-docprocessor-$RANDOM \
    --container-image-name $ACR_NAME.azurecr.io/docprocessor:v1

At this point, the app might not be able to start successfully because the web app doesn't yet have permission to pull from your private registry. In the next section, you enable a managed identity and grant it the AcrPull role.
```

Store the web app name for later use:

```azurecli
APP_NAME=$(az webapp list --resource-group rg-docprocessor --query "[0].name" --output tsv)
echo "Web app name: $APP_NAME"
```

## Configure managed identity for ACR access

Enable system-assigned managed identity on the web app:

```azurecli
az webapp identity assign \
    --resource-group rg-docprocessor \
    --name $APP_NAME
```

Get the principal ID and grant ACR pull permissions:

```azurecli
PRINCIPAL_ID=$(az webapp identity show \
    --resource-group rg-docprocessor \
    --name $APP_NAME \
    --query principalId \
    --output tsv)

ACR_ID=$(az acr show \
    --resource-group rg-docprocessor \
    --name $ACR_NAME \
    --query id \
    --output tsv)

az role assignment create \
    --assignee $PRINCIPAL_ID \
    --scope $ACR_ID \
    --role AcrPull
```

Configure the web app to use managed identity for registry authentication:

```azurecli
az webapp config set \
    --resource-group rg-docprocessor \
    --name $APP_NAME \
    --acr-use-identity true \
    --acr-identity [system]
```

Update the container settings to use the registry with managed identity:

```azurecli
az webapp config container set \
    --resource-group rg-docprocessor \
    --name $APP_NAME \
    --container-image-name $ACR_NAME.azurecr.io/docprocessor:v1 \
    --container-registry-url https://$ACR_NAME.azurecr.io
```

## Configure application settings

Configure app settings for the document processing service:

```azurecli
az webapp config appsettings set \
    --resource-group rg-docprocessor \
    --name $APP_NAME \
    --settings \
        ENVIRONMENT=production \
        LOG_LEVEL=INFO \
        MAX_DOCUMENT_SIZE_MB=50 \
        PROCESSING_TIMEOUT_SECONDS=30
```

The sample application reads these values as environment variables. In a real document processing service, these settings would control processing behavior.

## Configure runtime settings

Configure the container port. The sample image listens on port 80, which is the default, so this step demonstrates the configuration without changing behavior:

```azurecli
az webapp config appsettings set \
    --resource-group rg-docprocessor \
    --name $APP_NAME \
    --settings WEBSITES_PORT=80
```

Enable persistent storage for processed documents:

```azurecli
az webapp config appsettings set \
    --resource-group rg-docprocessor \
    --name $APP_NAME \
    --settings WEBSITES_ENABLE_APP_SERVICE_STORAGE=true
```

Enable always-on to reduce cold start latency:

```azurecli
az webapp config set \
    --resource-group rg-docprocessor \
    --name $APP_NAME \
    --always-on true
```

## Enable container logging

Enable logging to capture container output:

```azurecli
az webapp log config \
    --resource-group rg-docprocessor \
    --name $APP_NAME \
    --docker-container-logging filesystem
```

## Verify the deployment

Get the web app URL and verify the application responds:

```azurecli
APP_URL=$(az webapp show \
    --resource-group rg-docprocessor \
    --name $APP_NAME \
    --query defaultHostName \
    --output tsv)

echo "Application URL: https://$APP_URL"
```

Open the URL in a browser or use curl to verify the application responds:

```azurecli
curl https://$APP_URL
```

The application should return a response indicating it's running. The first request may take longer as App Service pulls the container image and starts the application.

## Stream container logs

View real-time logs from the container:

```azurecli
az webapp log tail \
    --resource-group rg-docprocessor \
    --name $APP_NAME
```

Generate some requests to the application by refreshing the browser or using curl. You should see log entries appear in the stream. Press Ctrl+C to stop streaming.

## Inspect the diagnostic console

Open the SCM (Kudu) site to inspect configuration views and mounted storage paths. This view is useful when you need to confirm that App Service is applying the settings you configured and to quickly locate log files.

```azurecli
echo "Kudu URL: https://$APP_NAME.scm.azurewebsites.net"
```

Open this URL in a browser. Navigate to:

1. **Environment** to view environment variables and verify your app settings are present
2. **Debug console > Bash** to browse the mounted file system (such as `/home`)
3. In the file browser, navigate to `/home/LogFiles/` to view log files

The SCM site is separate from your app container, so it doesn't provide a complete view of the container's file system or running processes.

## View application settings

Verify the configured settings from the CLI:

```azurecli
az webapp config appsettings list \
    --resource-group rg-docprocessor \
    --name $APP_NAME \
    --output table
```

Confirm that your settings appear in the list along with system-provided settings.

## Clean up resources

When you're finished exploring, delete the resource group to remove all resources:

```azurecli
az group delete \
    --name rg-docprocessor \
    --yes \
    --no-wait
```

## Summary

In this exercise, you:

- Created an Azure Container Registry and imported a container image
- Created a Web App for Containers with managed identity authentication
- Configured app settings for environment-specific values
- Enabled persistent storage and always-on for production readiness
- Enabled container logging and used diagnostic tools to inspect the application

These skills apply to deploying any containerized application to Azure App Service.
