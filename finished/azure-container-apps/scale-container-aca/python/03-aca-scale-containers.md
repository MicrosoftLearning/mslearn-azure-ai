---
lab:
    topic: Azure Container Apps
    title: 'Configure autoscaling using KEDA triggers'
    description: 'Learn how to troubleshoot Azure Container Apps by diagnosing missing environment variables, ingress misconfigurations, and querying Log Analytics for historical troubleshooting.'
---


# Configure autoscaling using KEDA triggers

In this exercise, you deploy a container app that processes messages from an Azure Service Bus queue and configure KEDA-based autoscaling. You observe the application scaling in response to queue depth and validate scaling behavior under load using managed identity authentication.

Tasks performed in this exercise:

- Create Azure Container Registry, Container Apps environment, and Service Bus resources
- Deploy a queue processor application with managed identity
- Configure a Service Bus scale rule using KEDA
- Test scaling behavior by sending messages to the queue
- Monitor replica count changes in real-time

This exercise takes approximately **30** minutes to complete.

>**Important:** Azure Container Registry task runs are temporarily paused from Azure free credits. This exercise requires a Pay-As-You-Go, or another paid plan.

## Before you start

To complete the exercise, you need:

- An Azure subscription with the permissions to deploy the necessary Azure services. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli?view=azure-cli-latest).
- Optional: [Python 3.12](https://www.python.org/downloads/) or greater.

This exercise takes approximately **30** minutes to complete.

>**Important:** Azure Container Registry task runs are temporarily paused from Azure free credits. This exercise requires a Pay-As-You-Go, or another paid plan.

## Download project starter files and deploy Azure services

In this section you download the project starter files and use a script to deploy the necessary services to your Azure subscription. The Azure Container Registry and Container Apps environment deployment takes a few minutes to complete.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/aca-scale-python.zip
    ```

1. Copy, or move, the file to a location in your system where you want to work on the project. Then unzip the file into a folder.

1. Launch Visual Studio Code (VS Code) and select **File > Open Folder...** in the menu, then choose the folder containing the project files.

1. The project contains deployment scripts for both Bash (*azdeploy.sh*) and PowerShell (*azdeploy.ps1*). Open the appropriate file for your environment and change the two values at the top of the script to meet your needs, then save your changes. **Note:** Do not change anything else in the script.

    ```
    "<your-resource-group-name>" # Resource Group name
    "<your-azure-region>" # Azure region for the resources
    ```

1. In the menu bar select **Terminal > New Terminal** to open a terminal window in VS Code.

1. Run the following command to login to your Azure account. Answer the prompts to select your Azure account and subscription for the exercise.

    ```
    az login
    ```

1. Run the following command to ensure you have the **containerapp** extension for Azure CLI.

    ```azurecli
    az extension add --name containerapp
    ```

1. Run the following commands to ensure your subscription has the necessary resource providers for the exercise.

    ```azurecli
    az provider register --namespace Microsoft.App
    az provider register --namespace Microsoft.OperationalInsights
    ```

### Create resources in Azure

In this section you run the deployment script to deploy the necessary services to your Azure subscription.

1. Make sure you are in the root directory of the project and run the appropriate command in the terminal to launch the deployment script. The deployment script will deploy ACR and create a file with environment variables needed for exercise.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

1. When the script is running, enter **1** to launch the **Create Azure Container Registry and build container image** option. This option creates the ACR service and uses ACR Tasks to build and push the image to the registry.

1. When the previous operation is finished, enter **2** to launch the **Create Container Apps environment** options. Creating the environment is necessary before deploying the container.

1. When the previous operation is finished, enter **3** to launch the **Create Service Bus namespace and queue** option.

    >**Note:** A file containing environment variables is created after the container app is created. You use these variables throughout the exercise.

1. When the previous operation is finished, enter **6** to exit the deployment script.

1. Run the appropriate command to load the environment variables into your terminal session from the file created in a previous step.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

    >**Note:** Keep the terminal open. If you close it and create a new terminal, you might need to run the command to create the environment variable again.

## Deploy a queue processor application

You deploy a container app configured to process messages from the Service Bus queue using managed identity. The application includes a configurable processing delay to make scaling behavior observable.

1. Run the following command to create the container app with system-assigned managed identity and initial scale settings. The **--system-assigned** flag enables managed identity, and **--registry-identity system** allows the app to pull images from ACR using that identity.

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

Cleaning up avoids ongoing cost. Delete the resource group, which deletes the Container Apps environment, container app, and registry.

```azurecli
az group delete --name $RESOURCE_GROUP --no-wait --yes
```

## Troubleshooting

If you encounter issues during this exercise, try these steps:

**Container app not responding**
- Check if the revision is active using **az containerapp revision list**
- Verify ingress is configured using **az containerapp show**

**Cannot see logs**
- Console logs are recent only. Use Log Analytics for historical data.
- Log Analytics data may take 2-5 minutes to appear.

**Environment variables not taking effect**
- Container Apps creates a new revision when you change environment variables. Verify the new revision is active.
- Use **--replace-env-vars** carefully—it replaces all environment variables, not just the ones you specify.
