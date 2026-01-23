---
lab:
    topic: Azure Container Apps
    title: 'Configure autoscaling using KEDA triggers'
    description: 'Learn how to configure KEDA-based autoscaling in Azure Container Apps using Service Bus queue triggers and managed identity.'
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

    **Bash**
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

    **PowerShell**
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

1. Run the deployment script and enter **4** to launch the **Configure managed identity for queue-processor app** option. This assigns the **Azure Service Bus Data Receiver** and **Azure Service Bus Data Owner** roles to the container app's managed identity. When the operation finishes enter **6** to exit.

    **Bash**
    ```bash
    ./azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```
    >**Note:** Role assignments can take 1-2 minutes to propagate. Wait a few minutes before performing the next step.

1. Run the following command to verify the application deployed with zero replicas. The application shows zero running replicas because no scale rule triggers scaling and the minimum is set to zero.

    **Bash**
    ```bash
    az containerapp show \
        --name queue-processor \
        --resource-group $RESOURCE_GROUP \
        --query "properties.runningStatus"
    ```

    **PowerShell**
    ```powershell
    az containerapp show `
        --name queue-processor `
        --resource-group $env:RESOURCE_GROUP `
        --query "properties.runningStatus"
    ```

## Configure Service Bus scaling

In this section you add a Service Bus scale rule that monitors queue depth and triggers scaling when messages accumulate. The scale rule uses the container app's managed identity to query queue metrics.

1. Run the following command to update the container app with a Service Bus scale rule using managed identity. The **--scale-rule-identity system** parameter tells KEDA to use the container app's managed identity instead of a connection string. This scale rule monitors the **orders** queue and requests additional replicas when more than five messages are present per replica.

    **Bash**
    ```bash
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

    **PowerShell**
    ```powershell
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

1. Run the following command to verify the scale rule is configured. Look for the **servicebus-scaling** rule in the output with **minReplicas** set to **0** and **maxReplicas** set to **10**.

    **Bash**
    ```bash
    az containerapp show \
        --name queue-processor \
        --resource-group $RESOURCE_GROUP \
        --query "properties.template.scale"
    ```

    **PowerShell**
    ```powershell
    az containerapp show `
        --name queue-processor `
        --resource-group $env:RESOURCE_GROUP `
        --query "properties.template.scale"
    ```

## Test scaling behavior

In this section you send messages to the Service Bus queue and observe the application scaling in response. The queue processor has a 2-second processing delay per message, giving you time to observe scaling.

1. Open a second terminal window for monitoring. In that window, load the environment variables and run the following command to start monitoring replicas in real-time. Press **Ctrl+C** to stop monitoring when you're done observing.

    **Bash**
    ```bash
    source .env
    watch -n 2 "az containerapp replica list \
        --name queue-processor \
        --resource-group $RESOURCE_GROUP \
        --query '[].name' \
        --output table"
    ```

    **PowerShell**
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

1. In your original terminal, run the following command to send 100 messages to the queue.

    **Bash**
    ```bash
    for i in {1..100}; do
        az servicebus queue send \
            --namespace-name $SERVICE_BUS_NAMESPACE \
            --name $QUEUE_NAME \
            --resource-group $RESOURCE_GROUP \
            --body "Order $i"
    done
    ```

    **PowerShell**
    ```powershell
    1..100 | ForEach-Object {
        az servicebus queue send `
            --namespace-name $env:SERVICE_BUS_NAMESPACE `
            --name $env:QUEUE_NAME `
            --resource-group $env:RESOURCE_GROUP `
            --body "Order $_"
    }
    ```

1. Watch the monitoring terminal. With 100 messages and a **messageCount** threshold of **5**, the scaler requests up to 20 replicas (capped at max 10). You should see replicas scale up as messages accumulate.

1. Run the following command to view the system logs and observe scaling events. Look for log entries indicating replica scheduling and scaling decisions.

    **Bash**
    ```bash
    az containerapp logs show \
        --name queue-processor \
        --resource-group $RESOURCE_GROUP \
        --type system \
        --tail 50
    ```

    **PowerShell**
    ```powershell
    az containerapp logs show `
        --name queue-processor `
        --resource-group $env:RESOURCE_GROUP `
        --type system `
        --tail 50
    ```

1. Continue watching the monitoring terminal as messages are processed. The 2-second delay per message means processing takes several minutes across all replicas, giving you time to observe both scale-up and scale-down behavior. After messages are processed, the application eventually scales back to zero replicas after the **300-second** cool-down period.

## Configure multiple scale rules using YAML

In this section you learn how to configure multiple scale rules using YAML configuration. Adding a new scale rule via the CLI replaces the previous rule, so you use YAML to maintain multiple rules simultaneously.

1. Run the following command to enable ingress for the container app.

    **Bash**
    ```bash
    az containerapp ingress enable \
        --name queue-processor \
        --resource-group $RESOURCE_GROUP \
        --target-port 8080 \
        --type external
    ```

    **PowerShell**
    ```powershell
    az containerapp ingress enable `
        --name queue-processor `
        --resource-group $env:RESOURCE_GROUP `
        --target-port 8080 `
        --type external
    ```

1. Run the following command to export the app configuration to a YAML file.

    **Bash**
    ```bash
    az containerapp show \
        --name queue-processor \
        --resource-group $RESOURCE_GROUP \
        --output yaml > app-config.yaml
    ```

    **PowerShell**
    ```powershell
    az containerapp show `
        --name queue-processor `
        --resource-group $env:RESOURCE_GROUP `
        --output yaml > app-config.yaml
    ```

1. Open the *app-config.yaml* file in VS Code. Find the **scale** section under **properties > template** and locate the **rules** array. Add an HTTP scale rule alongside the existing Service Bus rule so both rules are present. The **rules** section should look similar to the following example.

    ```yaml
    scale:
      maxReplicas: 10
      minReplicas: 0
      rules:
      - name: servicebus-scaling
        custom:
          type: azure-servicebus
          metadata:
            messageCount: "5"
            namespace: <your-servicebus-namespace>
            queueName: orders
          identity: system
      - name: http-scaling
        http:
          metadata:
            concurrentRequests: "10"
    ```

1. Save the file and run the following command to apply the updated configuration.

    **Bash**
    ```bash
    az containerapp update \
        --name queue-processor \
        --resource-group $RESOURCE_GROUP \
        --yaml app-config.yaml
    ```

    **PowerShell**
    ```powershell
    az containerapp update `
        --name queue-processor `
        --resource-group $env:RESOURCE_GROUP `
        --yaml app-config.yaml
    ```

1. Run the following command to verify both scale rules are configured. You should see both the **servicebus-scaling** and **http-scaling** rules in the output.

    **Bash**
    ```bash
    az containerapp show \
        --name queue-processor \
        --resource-group $RESOURCE_GROUP \
        --query "properties.template.scale.rules[].name"
    ```

    **PowerShell**
    ```powershell
    az containerapp show `
        --name queue-processor `
        --resource-group $env:RESOURCE_GROUP `
        --query "properties.template.scale.rules[].name"
    ```

# Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues during this exercise, try these steps:

**App not scaling up when messages are sent**
- Verify the scale rule is configured using **az containerapp show --query "properties.template.scale"**
- Ensure the managed identity has the **Azure Service Bus Data Owner** role assigned (required for KEDA to query queue metrics)
- Check that the queue name and namespace in the scale rule match your Service Bus resources

**Managed identity permission errors**
- Role assignments can take 1-2 minutes to propagate after running option 4
- Verify the container app has a system-assigned identity using **az containerapp identity show**
- Ensure both **Azure Service Bus Data Receiver** and **Azure Service Bus Data Owner** roles are assigned

**App scales to zero and won't start**
- This is expected when the queue is empty and **minReplicas** is set to **0**
- Send messages to the queue to trigger scaling
- Check the scale rule configuration to ensure it references the correct queue

**Cannot see replicas in monitoring**
- The replica list command only shows running replicas
- If the app scaled to zero, no replicas will be shown
- Send messages to trigger scaling and wait for replicas to start

**YAML update fails**
- Ensure the YAML file syntax is valid
- Remove read-only properties like **id**, **systemData**, and **type** from the YAML before applying
- Verify the scale rules section follows the correct structure
