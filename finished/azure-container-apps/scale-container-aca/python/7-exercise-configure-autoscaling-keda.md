In this exercise, you deploy a container app that processes messages from an Azure Service Bus queue and configure KEDA-based autoscaling. You observe the application scaling in response to queue depth, configure multiple scale rules, and validate scaling behavior under load.

## Set up the Azure environment

You start by creating the Azure resources needed for this exercise. You create a resource group, a Container Apps environment, and an Azure Service Bus namespace with a queue.

1. Sign in to your Azure subscription using the Azure CLI:

    ```azurecli
    az login
    ```

1. Set variables for the resources you create in this exercise:

    ```bash
    RESOURCE_GROUP="rg-scaling-exercise"
    LOCATION="eastus"
    ENVIRONMENT_NAME="env-scaling-exercise"
    SERVICE_BUS_NAMESPACE="sb-scaling-$RANDOM"
    QUEUE_NAME="orders"
    ```

1. Create a resource group:

    ```azurecli
    az group create \
      --name $RESOURCE_GROUP \
      --location $LOCATION
    ```

1. Create a Container Apps environment:

    ```azurecli
    az containerapp env create \
      --name $ENVIRONMENT_NAME \
      --resource-group $RESOURCE_GROUP \
      --location $LOCATION
    ```

1. Create an Azure Service Bus namespace:

    ```azurecli
    az servicebus namespace create \
      --name $SERVICE_BUS_NAMESPACE \
      --resource-group $RESOURCE_GROUP \
      --location $LOCATION \
      --sku Standard
    ```

1. Create a queue in the Service Bus namespace:

    ```azurecli
    az servicebus queue create \
      --name $QUEUE_NAME \
      --namespace-name $SERVICE_BUS_NAMESPACE \
      --resource-group $RESOURCE_GROUP
    ```

## Deploy a queue processor application

You deploy a sample container app configured to process messages from the Service Bus queue. The initial deployment uses minimum scale settings to observe scaling behavior.

1. Get the Service Bus connection string:

    ```bash
    SERVICE_BUS_CONNECTION=$(az servicebus namespace authorization-rule keys list \
      --name RootManageSharedAccessKey \
      --namespace-name $SERVICE_BUS_NAMESPACE \
      --resource-group $RESOURCE_GROUP \
      --query primaryConnectionString \
      --output tsv)
    ```

1. Create the container app with initial scale settings. The application starts with zero replicas and can scale up to 10:

    ```azurecli
    az containerapp create \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --environment $ENVIRONMENT_NAME \
      --image mcr.microsoft.com/azuredocs/containerapps-queuereader:latest \
      --min-replicas 0 \
      --max-replicas 10 \
      --secrets "sb-connection=$SERVICE_BUS_CONNECTION" \
      --env-vars "ServiceBusConnection=secretref:sb-connection" \
                 "QueueName=$QUEUE_NAME"
    ```

1. Verify the application deployed with zero replicas:

    ```azurecli
    az containerapp show \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --query "properties.runningStatus"
    ```

    The application shows zero running replicas because no scale rule triggers scaling and the minimum is set to zero.

## Configure Service Bus scaling

You add a Service Bus scale rule that monitors queue depth and triggers scaling when messages accumulate.

1. Update the container app to add a Service Bus scale rule:

    ```azurecli
    az containerapp update \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --scale-rule-name servicebus-scaling \
      --scale-rule-type azure-servicebus \
      --scale-rule-metadata "queueName=$QUEUE_NAME" \
                            "namespace=$SERVICE_BUS_NAMESPACE" \
                            "messageCount=5" \
      --scale-rule-auth "connection=sb-connection"
    ```

    This scale rule monitors the `orders` queue and requests additional replicas when more than five messages are present per replica.

1. Verify the scale rule is configured:

    ```azurecli
    az containerapp show \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --query "properties.template.scale"
    ```

## Test scaling behavior

You send messages to the Service Bus queue and observe the application scaling in response.

1. Send 50 messages to the queue using the Azure CLI:

    ```bash
    for i in {1..50}; do
      az servicebus queue send \
        --namespace-name $SERVICE_BUS_NAMESPACE \
        --name $QUEUE_NAME \
        --resource-group $RESOURCE_GROUP \
        --body "Order $i"
    done
    ```

1. Monitor the replica count as the application scales. Run this command multiple times to observe scaling:

    ```azurecli
    az containerapp replica list \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --query "[].name" \
      --output table
    ```

    With 50 messages and a `messageCount` threshold of 5, the scaler requests 10 replicas. The actual count may vary as messages are processed.

1. View the system logs to observe scaling events:

    ```azurecli
    az containerapp logs show \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --type system \
      --tail 50
    ```

    Look for log entries indicating replica scheduling and scaling decisions.

1. Wait for the queue to empty and observe scale-down behavior. After messages are processed, the application eventually scales back to zero replicas after the 300-second cool-down period.

## Add HTTP scaling for API endpoints

You add an HTTP scale rule to handle scenarios where the application also receives HTTP requests.

1. Enable ingress for the container app:

    ```azurecli
    az containerapp ingress enable \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --target-port 80 \
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

## Implement traffic splitting (optional)

If time permits, you can enable multiple revision mode and configure traffic splitting.

1. Enable multiple revision mode:

    ```azurecli
    az containerapp update \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --revision-mode multiple
    ```

1. Deploy a new revision by updating an environment variable:

    ```azurecli
    az containerapp update \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --set-env-vars "VERSION=v2"
    ```

1. List the available revisions:

    ```azurecli
    az containerapp revision list \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --query "[].name" \
      --output table
    ```

1. Configure traffic splitting between the two revisions (replace revision names with your actual revision names):

    ```azurecli
    az containerapp ingress traffic set \
      --name queue-processor \
      --resource-group $RESOURCE_GROUP \
      --revision-weight <first-revision-name>=80 <second-revision-name>=20
    ```

1. Observe that each revision scales independently based on its traffic share.

## Clean up resources

When you complete the exercise, delete the resource group to remove all resources and stop incurring charges.

```azurecli
az group delete \
  --name $RESOURCE_GROUP \
  --yes \
  --no-wait
```

This command deletes the resource group and all resources within it, including the Container Apps environment, the container app, and the Service Bus namespace.
