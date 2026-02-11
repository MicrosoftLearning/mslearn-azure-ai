In this exercise, you create an Event Grid custom topic with the CloudEvents schema, publish custom events representing AI pipeline operations, configure event subscriptions with filters, and verify event delivery to handler endpoints. By the end, you'll have hands-on experience with the core Event Grid patterns covered in this module.

> [!NOTE]
> This exercise requires an Azure subscription. If you don't have an Azure subscription, create a [free account](https://azure.microsoft.com/free/) before you begin.

## Create a custom topic and event handler endpoint

You can start by creating a resource group, an Event Grid custom topic configured for the CloudEvents schema, and a web app that serves as the event handler endpoint. The Event Grid Viewer sample app displays incoming events in the browser so you can verify delivery and inspect event payloads.

1. Set environment variables for your resource names. You can replace the values with names that are unique in your subscription.

    ```bash
    RESOURCE_GROUP="rg-eventgrid-lab"
    LOCATION="eastus"
    TOPIC_NAME="ai-pipeline-events-$RANDOM"
    SITE_NAME="egviewer-$RANDOM"
    ```

1. Create a resource group and register the Event Grid resource provider if you haven't used Event Grid before.

    ```bash
    az group create --name $RESOURCE_GROUP --location $LOCATION

    az provider register --namespace Microsoft.EventGrid
    ```

1. Create a custom topic with the CloudEvents v1.0 input schema. This topic serves as the endpoint where your AI application publishes events.

    ```bash
    az eventgrid topic create \
        --name $TOPIC_NAME \
        --resource-group $RESOURCE_GROUP \
        --location $LOCATION \
        --input-schema cloudeventschemav1_0
    ```

1. Deploy the Event Grid Viewer sample web app. This app provides a webhook endpoint that displays received events in a browser interface.

    ```bash
    az deployment group create \
        --resource-group $RESOURCE_GROUP \
        --template-uri "https://raw.githubusercontent.com/Azure-Samples/azure-event-grid-viewer/master/azuredeploy.json" \
        --parameters siteName=$SITE_NAME hostingPlanName=viewerhost
    ```

    After the deployment completes, open `https://$SITE_NAME.azurewebsites.net` in a browser to confirm the viewer app is running. You should see the site with no events displayed yet.

## Create event subscriptions with filters

You can now create event subscriptions that route specific events to the viewer endpoint. Each subscription uses filters to control which events it receives, demonstrating how Event Grid directs events to the right handler based on event type and subject.

1. Store the topic resource ID and viewer endpoint URL in variables.

    ```bash
    TOPIC_ID=$(az eventgrid topic show \
        --name $TOPIC_NAME \
        --resource-group $RESOURCE_GROUP \
        --query "id" \
        --output tsv)

    ENDPOINT="https://$SITE_NAME.azurewebsites.net/api/updates"
    ```

1. Create a subscription that receives only inference completion events by filtering on event type. This subscription represents an analytics dashboard that tracks completed AI inferences.

    ```azurecli
    az eventgrid event-subscription create \
        --name inference-dashboard-sub \
        --source-resource-id $TOPIC_ID \
        --endpoint $ENDPOINT \
        --event-delivery-schema cloudeventschemav1_0 \
        --included-event-types com.contoso.ai.InferenceCompleted
    ```

1. Create a second subscription that receives only events from the embeddings pipeline by filtering on the subject prefix. This subscription represents a monitoring service that tracks embeddings processing.

    ```azurecli
    az eventgrid event-subscription create \
        --name embeddings-monitor-sub \
        --source-resource-id $TOPIC_ID \
        --endpoint $ENDPOINT \
        --event-delivery-schema cloudeventschemav1_0 \
        --subject-begins-with /pipelines/embeddings
    ```

1. Create a third subscription that receives all events from the topic without any filters. This subscription represents a logging service that captures every event for auditing.

    ```azurecli
    az eventgrid event-subscription create \
        --name audit-log-sub \
        --source-resource-id $TOPIC_ID \
        --endpoint $ENDPOINT \
        --event-delivery-schema cloudeventschemav1_0
    ```

    You should see subscription validation events appear in the Event Grid Viewer web app as each subscription is created.

## Set up the Python environment

1. Create a working directory and set up a Python virtual environment with the Event Grid SDK.

    ```bash
    mkdir eventgrid-lab && cd eventgrid-lab
    python -m venv .venv
    source .venv/bin/activate
    pip install azure-eventgrid azure-core
    ```

1. Retrieve the topic endpoint and access key, then export them as environment variables.

    ```bash
    TOPIC_ENDPOINT=$(az eventgrid topic show \
        --name $TOPIC_NAME \
        --resource-group $RESOURCE_GROUP \
        --query "endpoint" \
        --output tsv)

    TOPIC_KEY=$(az eventgrid topic key list \
        --name $TOPIC_NAME \
        --resource-group $RESOURCE_GROUP \
        --query "key1" \
        --output tsv)

    export EVENTGRID_TOPIC_ENDPOINT=$TOPIC_ENDPOINT
    export EVENTGRID_TOPIC_KEY=$TOPIC_KEY
    ```

    > [!NOTE]
    > In production applications, you should use Microsoft Entra ID with managed identity instead of access keys. This exercise uses an access key for simplicity in a learning environment.

## Publish custom events to the topic

1. Create a file named `publish_events.py` that publishes several CloudEvents to the custom topic. The events represent different AI pipeline operations with varying types and subjects, so you can observe how each subscription's filters determine which events it receives.

    ```python
    import os
    import uuid
    from azure.core.credentials import AzureKeyCredential
    from azure.core.messaging import CloudEvent
    from azure.eventgrid import EventGridPublisherClient

    endpoint = os.environ["EVENTGRID_TOPIC_ENDPOINT"]
    key = os.environ["EVENTGRID_TOPIC_KEY"]

    client = EventGridPublisherClient(endpoint, AzureKeyCredential(key))

    events = [
        CloudEvent(
            type="com.contoso.ai.InferenceCompleted",
            source="/services/content-moderation",
            data={
                "requestId": "req-001",
                "modelName": "content-classifier-v3",
                "processingDurationMs": 1250,
                "resultLocation": "https://results.blob.core.windows.net/output/req-001.json",
                "status": "completed",
                "itemsProcessed": 1
            },
            subject="/pipelines/moderation/image-classifier",
            id=str(uuid.uuid4())
        ),
        CloudEvent(
            type="com.contoso.ai.StageCompleted",
            source="/services/embeddings",
            data={
                "pipelineRunId": "run-42",
                "stage": "embeddings",
                "status": "completed",
                "documentsProcessed": 150
            },
            subject="/pipelines/embeddings/run-42",
            id=str(uuid.uuid4())
        ),
        CloudEvent(
            type="com.contoso.ai.InferenceCompleted",
            source="/services/content-moderation",
            data={
                "requestId": "req-002",
                "modelName": "content-classifier-v3",
                "processingDurationMs": 980,
                "resultLocation": "https://results.blob.core.windows.net/output/req-002.json",
                "status": "completed",
                "itemsProcessed": 1
            },
            subject="/pipelines/moderation/text-classifier",
            id=str(uuid.uuid4())
        ),
        CloudEvent(
            type="com.contoso.ai.ModelRetrained",
            source="/services/training",
            data={
                "modelName": "sentiment-v2",
                "modelVersion": "2.1.0",
                "accuracy": 0.94,
                "trainingDurationMinutes": 45
            },
            subject="/models/sentiment-v2",
            id=str(uuid.uuid4())
        ),
        CloudEvent(
            type="com.contoso.ai.StageCompleted",
            source="/services/indexing",
            data={
                "pipelineRunId": "run-42",
                "stage": "indexing",
                "status": "completed",
                "recordsIndexed": 150
            },
            subject="/pipelines/embeddings/run-42",
            id=str(uuid.uuid4())
        ),
    ]

    client.send(events)
    print(f"Published {len(events)} events to the custom topic.")
    for event in events:
        print(f"  Type: {event.type}, Subject: {event.subject}")
    ```

1. Run the publisher script.

    ```bash
    python publish_events.py
    ```

    You should see confirmation that five events were published.

## Verify filtered event delivery

You can now check the Event Grid Viewer web app to verify that each subscription received only the events matching its filters.

1. Open `https://$SITE_NAME.azurewebsites.net` in your browser (replace `$SITE_NAME` with the actual site name you set earlier). The viewer displays all events received by the endpoint.

1. Verify the following delivery behavior based on the filters you configured:

    - **`inference-dashboard-sub`:** Should receive two events, both with type `com.contoso.ai.InferenceCompleted`. The model retrained event and stage completed events should not appear for this subscription.
    - **`embeddings-monitor-sub`:** Should receive two events, both with subjects starting with `/pipelines/embeddings`. One is a `StageCompleted` event from the embeddings service with subject `/pipelines/embeddings/run-42`, and the other is a `StageCompleted` event from the indexing service with the same subject prefix.
    - **`audit-log-sub`:** Should receive all five events regardless of type or subject.

1. Click on individual events in the viewer to inspect their CloudEvents payload. Verify that each event contains the `specversion`, `type`, `source`, `id`, `subject`, and `data` attributes you defined in the publishing script.

## Configure retry policy and dead-letter destination

You can configure an event subscription with a custom retry policy and a dead-letter destination so that events that can't be delivered are stored for later investigation rather than being dropped.

1. Create a storage account and a blob container for dead-lettered events.

    ```bash
    STORAGE_NAME="egdeadletter$RANDOM"

    az storage account create \
        --name $STORAGE_NAME \
        --resource-group $RESOURCE_GROUP \
        --location $LOCATION \
        --sku Standard_LRS

    az storage container create \
        --name dead-letters \
        --account-name $STORAGE_NAME
    ```

1. Get the storage account resource ID and create an event subscription with a custom retry policy. This subscription uses a five-minute TTL and a maximum of three delivery attempts, and routes undeliverable events to the storage container.

    ```bash
    STORAGE_ID=$(az storage account show \
        --name $STORAGE_NAME \
        --resource-group $RESOURCE_GROUP \
        --query "id" \
        --output tsv)
    ```

    ```azurecli
    az eventgrid event-subscription create \
        --name retry-demo-sub \
        --source-resource-id $TOPIC_ID \
        --endpoint https://nonexistent-endpoint.example.com/api/events \
        --event-delivery-schema cloudeventschemav1_0 \
        --max-delivery-attempts 3 \
        --event-ttl 5 \
        --deadletter-endpoint "$STORAGE_ID/blobServices/default/containers/dead-letters"
    ```

    This subscription intentionally points to an endpoint that doesn't exist. Events published to the topic that match this subscription fail delivery and eventually move to the dead-letter container after the retry attempts are exhausted.

1. Publish an event to trigger the dead-letter flow.

    ```bash
    python -c "
    import os, uuid
    from azure.core.credentials import AzureKeyCredential
    from azure.core.messaging import CloudEvent
    from azure.eventgrid import EventGridPublisherClient

    client = EventGridPublisherClient(
        os.environ['EVENTGRID_TOPIC_ENDPOINT'],
        AzureKeyCredential(os.environ['EVENTGRID_TOPIC_KEY'])
    )
    client.send(CloudEvent(
        type='com.contoso.ai.DeadLetterTest',
        source='/services/testing',
        data={'test': 'dead-letter-verification'},
        subject='/tests/dead-letter',
        id=str(uuid.uuid4())
    ))
    print('Published dead-letter test event.')
    "
    ```

1. Wait several minutes for Event Grid to exhaust its retry attempts. Then list the blobs in the dead-letter container to confirm the event was stored.

    ```bash
    az storage blob list \
        --container-name dead-letters \
        --account-name $STORAGE_NAME \
        --query "[].name" \
        --output tsv
    ```

    You should see one or more blobs representing the dead-lettered events. Each blob contains the original event along with diagnostic properties such as `deadLetterReason`, `deliveryAttempts`, and `lastDeliveryOutcome`.

1. Download and inspect a dead-lettered event to see the diagnostic properties.

    ```bash
    BLOB_NAME=$(az storage blob list \
        --container-name dead-letters \
        --account-name $STORAGE_NAME \
        --query "[0].name" \
        --output tsv)

    az storage blob download \
        --container-name dead-letters \
        --account-name $STORAGE_NAME \
        --name "$BLOB_NAME" \
        --file dead-letter-event.json

    cat dead-letter-event.json
    ```

    The output shows the original event data alongside delivery failure information, including the `deadLetterReason` (such as `MaxDeliveryAttemptsExceeded`) and the `lastDeliveryOutcome` (such as `NotFound`).

## Clean up resources

When you're finished with the exercise, you can delete the resource group to remove all the resources you created.

```bash
az group delete --name $RESOURCE_GROUP --yes --no-wait
```
