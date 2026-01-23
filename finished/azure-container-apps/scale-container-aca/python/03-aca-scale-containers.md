# Configure autoscaling using KEDA triggers

In this exercise, you deploy a container app that processes messages from an Azure Service Bus queue and configure KEDA-based autoscaling. You observe the application scaling in response to queue depth and validate scaling behavior under load using managed identity authentication.

## Set up the Azure environment

Before starting the exercise, use the provided deployment script to create the required Azure resources.

1. Run the deployment script and complete options 1, 2, and 3:

    **Bash:**
    ```bash
    ./azdeploy.sh
    ```

    **PowerShell:**
    ```powershell
    ./azdeploy.ps1
    ```

    - Option 1: Creates Azure Container Registry and builds the queue processor image
    - Option 2: Creates the Container Apps environment
    - Option 3: Creates the Service Bus namespace and queue

1. Load the environment variables created by the script:

    **Bash:**
    ```bash
    source .env
    ```

    **PowerShell:**
    ```powershell
    . .\.env.ps1
    ```

1. Verify the variables are set:

    **Bash:**
    ```bash
    echo "ACR: $ACR_SERVER"
    echo "Environment: $ACA_ENVIRONMENT"
    echo "Service Bus: $SERVICE_BUS_NAMESPACE"
    ```

    **PowerShell:**
    ```powershell
    Write-Host "ACR: $env:ACR_SERVER"
    Write-Host "Environment: $env:ACA_ENVIRONMENT"
    Write-Host "Service Bus: $env:SERVICE_BUS_NAMESPACE"
    ```

## Deploy a queue processor application

You deploy a container app configured to process messages from the Service Bus queue using managed identity. The application includes a configurable processing delay to make scaling behavior observable.

1. Create the container app with system-assigned managed identity and initial scale settings:

    **Bash:**
    ```azurecli
    az containerapp create \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --environment $ACA_ENVIRONMENT \
      --image $ACR_SERVER/$CONTAINER_IMAGE \
      --registry-server $ACR_SERVER \
      --registry-identity system \
      --system-assigned \
      --min-replicas 0 \
      --max-replicas 10 \
      --env-vars "SERVICE_BUS_NAMESPACE=$SERVICE_BUS_NAMESPACE" \
                 "QUEUE_NAME=$QUEUE_NAME" \
                 "PROCESSING_DELAY_SECONDS=2"
    ```

    **PowerShell:**
    ```azurecli
    az containerapp create `
      --name queue-processor `
      --resource-group $env:RESOURCE_GROUP `
      --environment $env:ACA_ENVIRONMENT `
      --image "$env:ACR_SERVER/$env:CONTAINER_IMAGE" `
      --registry-server $env:ACR_SERVER `
      --registry-identity system `
      --system-assigned `
      --min-replicas 0 `
      --max-replicas 10 `
      --env-vars "SERVICE_BUS_NAMESPACE=$env:SERVICE_BUS_NAMESPACE" `
                 "QUEUE_NAME=$env:QUEUE_NAME" `
                 "PROCESSING_DELAY_SECONDS=2"
    ```

    The `--system-assigned` flag enables managed identity, and `--registry-identity system` allows the app to pull images from ACR using that identity.

1. Configure managed identity permissions for Service Bus. Run the deployment script and select option 4:

    **Bash:**
    ```bash
    ./azdeploy.sh
    # Select option 4: Configure managed identity for queue-processor app
    ```

    **PowerShell:**
    ```powershell
    ./azdeploy.ps1
    # Select option 4: Configure managed identity for queue-processor app
    ```

    This assigns the **Azure Service Bus Data Receiver** and **Azure Service Bus Data Owner** roles to the container app's managed identity.

    > **Note:** Role assignments can take 1-2 minutes to propagate. If the app fails to connect to Service Bus initially, wait a moment before testing.

1. Verify the application deployed with zero replicas:

    ```azurecli
    az containerapp show \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --query "properties.runningStatus"
    ```

    The application shows zero running replicas because no scale rule triggers scaling and the minimum is set to zero.

## Configure Service Bus scaling

You add a Service Bus scale rule that monitors queue depth and triggers scaling when messages accumulate. The scale rule uses the container app's managed identity to query queue metrics.

1. Update the container app to add a Service Bus scale rule with managed identity:

    **Bash:**
    ```azurecli
    az containerapp update \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --scale-rule-name servicebus-scaling \
      --scale-rule-type azure-servicebus \
      --scale-rule-metadata "queueName=$QUEUE_NAME" \
                            "namespace=$SERVICE_BUS_NAMESPACE" \
                            "messageCount=5" \
      --scale-rule-identity system
    ```

    **PowerShell:**
    ```azurecli
    az containerapp update `
      --name queue-processor `
      --resource-group $env:RESOURCE_GROUP `
      --scale-rule-name servicebus-scaling `
      --scale-rule-type azure-servicebus `
      --scale-rule-metadata "queueName=$env:QUEUE_NAME" `
                            "namespace=$env:SERVICE_BUS_NAMESPACE" `
                            "messageCount=5" `
      --scale-rule-identity system
    ```

    The `--scale-rule-identity system` parameter tells KEDA to use the container app's managed identity instead of a connection string. This scale rule monitors the `orders` queue and requests additional replicas when more than five messages are present per replica.

1. Verify the scale rule is configured:

    ```azurecli
    az containerapp show \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --query "properties.template.scale"
    ```

## Test scaling behavior

You send messages to the Service Bus queue and observe the application scaling in response. The queue processor has a 2-second processing delay per message, giving you time to observe scaling.

1. Open a second terminal window for monitoring. In that window, load the environment variables and start monitoring replicas in real-time:

    **Bash:**
    ```bash
    source .env
    watch -n 2 "az containerapp replica list \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --query '[].name' \
      --output table"
    ```

    **PowerShell:**
    ```powershell
    . .\.env.ps1
    while ($true) {
        Clear-Host
        az containerapp replica list `
            --name queue-processor `
            --resource-group $env:RESOURCE_GROUP `
            --query "[].name" `
            --output table
        Start-Sleep -Seconds 2
    }
    ```

    Press `Ctrl+C` to stop monitoring when you're done observing.

1. In your original terminal, send 100 messages to the queue:

    **Bash:**
    ```bash
    for i in {1..100}; do
      az servicebus queue send \
        --namespace-name $SERVICE_BUS_NAMESPACE \
        --name $QUEUE_NAME \
        --resource-group $RESOURCE_GROUP \
        --body "Order $i"
    done
    ```

    **PowerShell:**
    ```powershell
    1..100 | ForEach-Object {
        az servicebus queue send `
            --namespace-name $env:SERVICE_BUS_NAMESPACE `
            --name $env:QUEUE_NAME `
            --resource-group $env:RESOURCE_GROUP `
            --body "Order $_"
    }
    ```

1. Watch the monitoring terminal. With 100 messages and a `messageCount` threshold of 5, the scaler requests up to 20 replicas (capped at max 10). You should see replicas scale up as messages accumulate.

1. View the system logs to observe scaling events:

    ```azurecli
    az containerapp logs show \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --type system \
      --tail 50
    ```

    Look for log entries indicating replica scheduling and scaling decisions.

1. Continue watching the monitoring terminal as messages are processed. The 2-second delay per message means processing takes several minutes across all replicas, giving you time to observe both scale-up and scale-down behavior. After messages are processed, the application eventually scales back to zero replicas after the 300-second cool-down period.

## Add HTTP scaling for API endpoints (optional)

You can add an HTTP scale rule to handle scenarios where the application also receives HTTP requests.

1. Enable ingress for the container app:

    ```azurecli
    az containerapp ingress enable \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --target-port 8080 \
      --type external
    ```

1. Update the container app to add an HTTP scale rule alongside the existing Service Bus rule:

    ```azurecli
    az containerapp update \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --scale-rule-name http-scaling \
      --scale-rule-type http \
      --scale-rule-http-concurrency 10
    ```

    Note that adding a new scale rule via the CLI replaces the previous rule. To maintain multiple rules, use YAML configuration or the Azure portal.

1. To configure both rules simultaneously, export the app configuration and modify it:

    ```azurecli
    az containerapp show \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --output yaml > app-config.yaml
    ```

1. Edit `app-config.yaml` to include both scale rules under the `scale.rules` section, then apply the updated configuration:

    ```azurecli
    az containerapp update \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --yaml app-config.yaml
    ```

## Clean up resources

When you complete the exercise, delete the resource group to remove all resources and stop incurring charges.

```azurecli
az group delete \
  --name $RESOURCE_GROUP \
  --yes \
  --no-wait
```

This command deletes the resource group and all resources within it, including the Container Apps environment, the container app, and the Service Bus namespace.
