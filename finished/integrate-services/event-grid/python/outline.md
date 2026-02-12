# Develop event-driven AI workflows with Azure Event Grid

## Module overview

AI solutions on Azure depend on coordinated responses to system changes. When a new dataset lands in storage, a model finishes retraining, or a batch of documents completes processing, downstream components need to react immediately without polling for updates. Azure Event Grid provides a fully managed event-routing service that connects event sources to handlers with low latency and high reliability, enabling developers to build reactive AI architectures that respond to state changes as they happen.

This module teaches developers how to use Azure Event Grid to trigger AI pipelines, react to system events from Azure services, design events using the CloudEvents schema, configure delivery and retry policies for reliable event processing, and publish custom events from AI applications. The content focuses on practical patterns for event-driven AI workflows using Azure Event Grid custom topics, system topics, event subscriptions, and the Azure SDKs.

## Learning objectives

After completing this module, you'll be able to:

- Explain how Azure Event Grid enables event-driven patterns in AI solutions and identify the core components (topics, event subscriptions, and event handlers) that form an event-routing architecture.
- Design events using the CloudEvents schema for AI operations, define custom event types, and configure event subscriptions with filters that route events based on type, subject, or data attributes.
- Configure delivery and retry policies to handle transient failures in AI pipelines, set dead-letter destinations for undeliverable events, and monitor delivery outcomes.
- Publish custom events from AI applications to signal completed inferences, model updates, or pipeline stage transitions using the Event Grid SDK and REST API.

---

## Unit 1: Introduction

**Filename:** `1-introduction.md`

Opening paragraph (two to three sentences): AI applications require immediate, coordinated responses to system events such as new data arrivals, completed model training, or pipeline stage transitions. This module guides you through using Azure Event Grid to build event-driven AI workflows on Azure that react to state changes in real time.

Scenario paragraph (eight to twelve sentences, no heading): Imagine you're a developer building an AI-powered content moderation platform that processes images and text uploaded to Azure Blob Storage. Each upload triggers a series of downstream operations: an embeddings service generates vector representations, a classification model assigns content categories, and a notification service alerts reviewers when content is flagged. Currently, each service polls for new data on a fixed interval, creating delays between upload and processing, wasting compute resources on empty polls, and making it difficult to add new processing steps without modifying existing services. During traffic spikes, the polling intervals can't keep up, and newly uploaded content waits minutes before processing begins. Your team needs an architecture where each component reacts to events as they occur rather than checking for changes on a schedule. When a new image arrives in storage, the system should immediately trigger the embeddings pipeline without any service needing to know about the others. Failed processing attempts should retry automatically, and permanently failed events should route to a dead-letter destination for investigation. The platform also needs to emit its own custom events when processing completes, so additional downstream services can subscribe without modifying the existing pipeline. Azure Event Grid provides the event-driven routing, filtering, and delivery guarantees that this architecture requires.

Learning objectives: After completing this module, you'll be able to:

- Explain how Azure Event Grid enables event-driven patterns in AI solutions and identify the core components (topics, event subscriptions, and event handlers) that form an event-routing architecture.
- Design events using the CloudEvents schema for AI operations, define custom event types, and configure event subscriptions with filters that route events based on type, subject, or data attributes.
- Configure delivery and retry policies to handle transient failures in AI pipelines, set dead-letter destinations for undeliverable events, and monitor delivery outcomes.
- Publish custom events from AI applications to signal completed inferences, model updates, or pipeline stage transitions using the Event Grid SDK and REST API.

---

## Unit 2: Understand Azure Event Grid concepts and event-driven patterns for AI solutions

**Filename:** `2-understand-event-grid-concepts.md`

This unit introduces Azure Event Grid as a fully managed event-routing service and explains why event-driven architecture matters for AI backends. Developers learn the core Event Grid components (topics, event subscriptions, event handlers) and how event-driven patterns address common AI architecture challenges such as triggering embeddings refresh on data changes, initiating batch processing in response to model updates, and coordinating multi-stage AI pipelines.

### Key content areas

- **What Azure Event Grid provides:** A fully managed publish-subscribe service that routes events from sources to handlers with per-event pricing and no infrastructure to manage. Event Grid supports both push delivery (events sent to an endpoint) and pull delivery (consumers connect to Event Grid to read events). Event Grid natively integrates with Azure services through system topics and supports custom application events through custom topics. The service handles millions of events per second with subsecond latency.

- **Core components of Event Grid architecture:**
    - **Events:** Lightweight notifications that describe a state change. An event indicates something happened (such as "blob created" or "model training completed") without carrying the full changed resource. The subscriber retrieves the resource separately if needed.
    - **Event sources:** Azure services or custom applications that emit events. Azure services such as Blob Storage, Azure Key Vault, and Azure Container Registry automatically publish events as system topics. Custom applications publish events to custom topics.
    - **Topics:** Endpoints that receive events from sources. System topics are created automatically for Azure service events. Custom topics are user-defined endpoints where applications post their own events. Namespace topics are part of the Event Grid namespace resource and support both push and pull delivery.
    - **Event subscriptions:** Configuration resources that define which events to receive and where to send them. Each subscription specifies a topic to listen on, optional filters to select specific events, and a destination endpoint (the event handler).
    - **Event handlers:** Destinations that process events. Supported handlers include Azure Functions, Azure Event Hubs, Azure Service Bus queues and topics, webhooks, and Azure Storage queues.

- **Why AI architectures benefit from event-driven patterns:** AI workflows involve multiple loosely coupled components that need to coordinate without tight dependencies. Event-driven architecture replaces polling with reactive triggers, reducing latency and eliminating wasted compute. When a new dataset arrives in Blob Storage, Event Grid immediately notifies the embeddings pipeline rather than waiting for a polling interval. When a model finishes retraining, a custom event can trigger downstream validation and deployment services. Components subscribe to only the events they care about, and new consumers can be added without modifying producers.

- **Event-driven patterns for AI workloads:**
    - **Reactive data processing:** Subscribe to Blob Storage events (`Microsoft.Storage.BlobCreated`) to trigger an AI pipeline whenever new training data, documents, or images arrive. The pipeline receives the event, retrieves the blob, and processes it without any polling loop.
    - **Pipeline stage coordination:** Use custom events to signal stage transitions in a multi-step AI pipeline. When an embeddings generation step completes, it publishes an event that triggers the indexing step. Each stage operates independently and scales based on its own workload.
    - **Model lifecycle management:** Publish custom events for model training completion, validation results, and deployment promotions. Downstream services subscribe to these events to update serving endpoints, refresh caches, or notify stakeholders.

- **System topics versus custom topics:** System topics represent events from Azure services. Event Grid creates them automatically when you create an event subscription for a supported Azure resource. Custom topics are endpoints that your application creates and publishes events to. For AI workflows, you typically use system topics for infrastructure events (data arrival, key rotation, container image push) and custom topics for application-level events (inference completed, pipeline stage transition, anomaly detected).

### Additional resources

- [What is Azure Event Grid?](/azure/event-grid/overview)
- [Concepts in Azure Event Grid](/azure/event-grid/concepts)
- [System topics in Azure Event Grid](/azure/event-grid/system-topics)

---

## Unit 3: Work with event schemas and properties

**Filename:** `3-event-schemas-properties.md`

This unit covers how to structure events for AI operations using the CloudEvents schema, define custom event types that reflect AI workflow state changes, and configure event subscription filters to route events based on type, subject, or data attributes. Developers learn how the event schema affects filtering, interoperability, and downstream processing.

### Key content areas

- **Event Grid schema versus CloudEvents schema:** Event Grid supports two event schemas: the proprietary Event Grid schema and the open CloudEvents v1.0 schema. CloudEvents is the recommended format for new implementations because it provides a standardized, protocol-agnostic event structure backed by the Cloud Native Computing Foundation (CNCF). CloudEvents simplifies interoperability across platforms and tooling. Event Grid natively supports CloudEvents JSON format and HTTP protocol binding. Existing Azure system events can be delivered in CloudEvents format by configuring the output schema on the event subscription.

- **CloudEvents schema structure for AI events:** A CloudEvents event contains required attributes (`specversion`, `type`, `source`, `id`) and optional attributes (`subject`, `time`, `datacontenttype`, `data`). For AI operations, the `type` field identifies the kind of event (such as `com.contoso.ai.InferenceCompleted` or `com.contoso.ai.ModelRetrained`). The `source` field identifies the originating system or service. The `subject` field provides a path for filtering (such as `/models/sentiment-v2` or `/pipelines/embeddings`). The `data` field carries the event payload with operation-specific details. Include a code fragment showing a CloudEvents JSON event for a completed inference operation.

- **Design custom event types for AI workflows:** Define event types that represent meaningful state changes in your AI system. Use a reverse-DNS naming convention for custom event types (such as `com.contoso.ai.EmbeddingsRefreshed`, `com.contoso.ai.BatchProcessingStarted`, `com.contoso.ai.AnomalyDetected`). Keep the event payload small. Include enough context for the subscriber to start processing (such as a resource URI, model name, and result summary) without embedding the full result in the event. The subscriber retrieves detailed results from a data store if needed.

- **Configure event type filtering:** Event subscriptions can filter events by type to ensure that each handler receives only the events it cares about. For AI workflows, you can configure a subscription that listens for `com.contoso.ai.InferenceCompleted` events and ignores all other types. This keeps handlers focused and avoids unnecessary invocations. Event type filtering uses the `includedEventTypes` property on the event subscription.

- **Subject filtering for granular routing:** The `subject` field enables path-based filtering using prefix and suffix matches. For AI applications, set the subject to a hierarchical path that reflects the event context, such as `/pipelines/embeddings/batch-42` or `/models/classification/v3`. Subscribers can filter using `subjectBeginsWith` to match all events from a pipeline or `subjectEndsWith` to match events for a specific file type. This approach routes events to the right handler without requiring custom logic in each subscriber.

- **Advanced filtering on data attributes:** Event Grid supports advanced filters that match on values within the event body or extension attributes. Advanced filters use operators such as `StringContains`, `NumberGreaterThan`, `StringBeginsWith`, and `BoolEquals`. For AI events, you can filter on data attributes like `data.confidence` (route only high-confidence results) or `data.modelName` (subscribe to events from a specific model). Advanced filters support up to 25 filter conditions per subscription with AND logic between conditions and OR logic within each condition's values.

- **Configure the input and output schema:** When creating a custom topic, set the `input-schema` parameter to `cloudeventschemav1_0` to accept events in CloudEvents format. When creating an event subscription, set the `event-delivery-schema` to control the format delivered to the handler. Event Grid can convert between Event Grid schema and CloudEvents schema during delivery, but CloudEvents-to-Event Grid conversion isn't supported because CloudEvents supports extension attributes that the Event Grid schema doesn't.

### Additional resources

- [CloudEvents v1.0 schema with Azure Event Grid](/azure/event-grid/cloud-event-schema)
- [Azure Event Grid event schema](/azure/event-grid/event-schema)
- [Understand event filtering for Event Grid subscriptions](/azure/event-grid/event-filtering)

---

## Unit 4: Configure delivery and retry policies for reliable event processing

**Filename:** `4-delivery-retry-policies.md`

This unit teaches developers how to configure Event Grid delivery and retry behavior to handle the transient failures that commonly occur in AI pipelines. Developers learn how Event Grid retries failed deliveries, how to customize retry policies, how to set up dead-letter destinations for events that can't be delivered, and how to monitor delivery outcomes.

### Key content areas

- **How Event Grid delivers events:** Event Grid delivers events by sending an HTTP POST request to the subscriber's endpoint. The subscriber must respond with a success status code (200, 201, 202, 203, or 204) to acknowledge receipt. If the endpoint returns an error or doesn't respond within 30 seconds, Event Grid queues the message for retry. Event Grid delivers one event at a time by default, but you can configure output batching to group multiple events per delivery for improved throughput.

- **Retry schedule and exponential backoff:** When Event Grid receives an error response, it evaluates the error type. Configuration-related errors (400 Bad Request, 413 Request Entity Too Large, 403 Forbidden) aren't retried because they indicate permanent issues. For all other errors, Event Grid applies an exponential backoff retry schedule: 10 seconds, 30 seconds, one minute, five minutes, 10 minutes, 30 minutes, one hour, three hours, six hours, then every 12 hours up to 24 hours. Event Grid adds randomization to retry intervals and might skip retries if an endpoint appears consistently unhealthy.

- **Customize retry policy settings:** Developers can adjust two parameters when creating an event subscription to control retry behavior:
    - **Maximum number of attempts:** An integer between one and 30 (default: 30). Event Grid stops retrying after this many delivery attempts.
    - **Event time-to-live (TTL):** An integer between one and 1,440 minutes (default: 1,440 minutes, or 24 hours). Event Grid stops retrying after this time elapses.
    Event Grid uses whichever limit is reached first. For AI pipelines with time-sensitive operations (such as real-time classification requests), set a shorter TTL so stale events don't consume handler resources. For batch processing pipelines that can tolerate delays, use longer TTL values with more retry attempts. Include a code fragment showing Azure CLI commands to create an event subscription with custom retry settings.

- **Dead-letter destinations for undeliverable events:** When Event Grid exhausts all retry attempts or the event TTL expires, it can send the undelivered event to a dead-letter destination. Dead-lettering is disabled by default. To enable it, specify an Azure Blob Storage container as the dead-letter endpoint when creating the event subscription. Each dead-lettered event includes diagnostic properties such as `deadLetterReason` (for example, `MaxDeliveryAttemptsExceeded`), `deliveryAttempts`, `lastDeliveryOutcome`, and `lastDeliveryAttemptTime`. These properties help developers diagnose why events failed and determine whether the failures are transient or permanent.

- **Handle transient failures in AI pipelines:** AI handler endpoints can fail for various reasons: model service restarts, GPU memory pressure, cold-start latency on serverless functions, or downstream dependency outages. Event Grid's retry mechanism automatically handles these transient failures without developer intervention. Ensure that handler endpoints are idempotent because Event Grid provides at-least-once delivery and might redeliver events. Use the event `id` field to detect and deduplicate repeated deliveries.

- **Monitor delivery outcomes:** Event Grid publishes delivery metrics through Azure Monitor, including delivery success count, delivery failure count, matched events, dropped events, and dead-lettered events. You can set up alerts on dead-letter count or delivery failure rate to detect systemic issues in your AI pipeline. For example, a sudden increase in dead-lettered events might indicate that a model service is down or that a handler endpoint URL changed.

- **Output batching for high-throughput AI workloads:** For AI systems that generate or consume events at high volume (such as processing thousands of document uploads), enable output batching on the event subscription. Configure the maximum events per batch (one to 5,000) and preferred batch size in kilobytes (one to 1,024). Batching reduces the number of HTTP requests to the handler, improving throughput and reducing overhead. The handler receives an array of events and must process all or none, since Event Grid uses all-or-none batch delivery semantics.

### Additional resources

- [Event Grid message delivery and retry](/azure/event-grid/delivery-and-retry)
- [Dead letter and retry policies](/azure/event-grid/manage-event-delivery)
- [Monitor Event Grid message delivery](/azure/event-grid/monitor-event-delivery)

---

## Unit 5: Publish custom events from AI applications

**Filename:** `5-publish-custom-events.md`

This unit covers how to publish custom events from AI applications to Event Grid custom topics. Developers learn to create custom topics, construct well-structured events for AI operations, and use the Event Grid SDK and REST API to emit events that signal completed inferences, model updates, pipeline stage transitions, and other application-level state changes.

### Key content areas

- **Create a custom topic for AI events:** A custom topic provides a user-defined endpoint where your application posts events. You create a custom topic using the Azure CLI, Azure portal, or infrastructure-as-code tools. Set the input schema to CloudEvents when creating the topic so events use the standardized format. The topic endpoint URL and access key (or Microsoft Entra ID authentication) are needed for publishing. Microsoft Entra authentication provides stronger security than access keys because it eliminates the need to manage and rotate shared secrets. Include a code fragment showing Azure CLI commands to create a custom topic with the CloudEvents input schema.

- **Construct events for AI operations:** Build CloudEvents-formatted events that describe meaningful state changes in your AI system. Each event needs a unique `id`, a `type` that categorizes the operation (such as `com.contoso.ai.InferenceCompleted`), a `source` that identifies the originating component, and a `data` payload with operation details. Keep the data payload focused on metadata needed for routing and initial processing: include the result location, model name, processing duration, and a confidence score or status indicator rather than embedding full inference results. Subscribers retrieve detailed outputs from a data store using identifiers in the event data.

- **Publish events using the Event Grid SDK:** Use the Azure SDK's `EventGridPublisherClient` to send events to a custom topic. The SDK handles serialization, authentication, and retries. You can publish single events or batches. For AI applications, publish events at natural checkpoint boundaries: after an inference completes, when a pipeline stage transitions, or when an anomaly is detected. Include code fragments showing how to create an `EventGridPublisherClient`, construct a `CloudEvent` object, and publish it to a custom topic using the Python SDK.

- **Publish events using the REST API:** You can post events to a custom topic by sending an HTTP POST request to the topic endpoint with an `aeg-sas-key` header for authentication. The request body is a JSON array of events (Event Grid schema) or a single JSON event (CloudEvents schema with `content-type: application/cloudevents+json`). The REST API is useful when publishing from languages without an official Event Grid SDK or from lightweight services that don't need the full SDK. Include an example of the HTTP request structure with the CloudEvents content type header.

- **Authenticate publishing clients:** Event Grid supports access key authentication (using the `aeg-sas-key` header), SAS token authentication, and Microsoft Entra ID authentication. For production AI applications, Microsoft Entra ID is the recommended approach because it avoids key management, supports managed identities, and benefits from features such as Conditional Access. When running on Azure services such as Azure Functions, Azure Container Apps, or Azure Kubernetes Service, you can assign a managed identity to the hosting service and grant it the Event Grid Data Sender role on the custom topic.

- **Event design patterns for AI applications:**
    - **Inference completion events:** Publish after each inference request completes. Include the request correlation ID, model name, processing duration, result location, and a summary status (success, partial, or failed). Downstream subscribers can trigger notification workflows, update dashboards, or initiate follow-up processing.
    - **Model update events:** Publish when a model is retrained, validated, or promoted to production. Include the model version, training metrics summary, and deployment target. Subscribers can refresh model caches, update routing tables, or trigger integration tests.
    - **Pipeline stage transition events:** Publish at each stage boundary in a multi-step pipeline. Include the pipeline run ID, stage name, stage status, and input/output references. Monitoring services subscribe to these events to build a real-time view of pipeline progress and detect bottlenecks.

### Additional resources

- [Publish events to Azure Event Grid custom topics](/azure/event-grid/post-to-custom-topic)
- [Authenticate publishing clients using Microsoft Entra ID](/azure/event-grid/authenticate-with-microsoft-entra-id)
- [Azure Event Grid client library for Python](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/eventgrid/azure-eventgrid)

---

## Unit 6: Exercise - Trigger and process AI events with Azure Event Grid

**Filename:** `6-exercise-trigger-process-events.md`

Hands-on exercise where developers create an Event Grid custom topic, publish custom events representing AI pipeline operations, configure event subscriptions with filters, and verify event delivery to handler endpoints.

### Exercise objectives

- Create an Event Grid custom topic with the CloudEvents input schema using the Azure CLI.
- Publish custom events to the topic that represent AI operations such as inference completion and pipeline stage transitions.
- Create event subscriptions with event type filters and subject filters to route events to specific handlers.
- Configure retry policies and a dead-letter destination on an event subscription.
- Verify event delivery by inspecting handler logs and dead-lettered events.

---

## Unit 7: Module assessment

**Filename:** `7-knowledge-check.yml`

Placeholder. Five knowledge check questions will be generated after content is complete during the `/yaml` phase. Questions will test decision-making about event-driven patterns, CloudEvents schema design, event filtering strategies, delivery and retry configuration, and custom event publishing. Questions will be based on content units only (not the exercise).

---

## Unit 8: Summary

**Filename:** `8-summary.md`

Summary paragraph starting with "In this module, you learned" that recaps each content unit: Event Grid concepts and event-driven patterns for AI architectures, designing events with the CloudEvents schema and configuring filters for targeted routing, configuring delivery and retry policies to handle failures in AI pipelines, and publishing custom events from AI applications to coordinate multi-stage workflows. The summary connects these skills back to building reactive AI systems that respond to state changes immediately, process events reliably, and scale by adding new event subscribers without modifying existing components.

### Additional resources

- [Azure Event Grid documentation](/azure/event-grid/)
- [CloudEvents v1.0 schema with Azure Event Grid](/azure/event-grid/cloud-event-schema)
- [Event Grid message delivery and retry](/azure/event-grid/delivery-and-retry)
- [Publish events to Azure Event Grid custom topics](/azure/event-grid/post-to-custom-topic)
