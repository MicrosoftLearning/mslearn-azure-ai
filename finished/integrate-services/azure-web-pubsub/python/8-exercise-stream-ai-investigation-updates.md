In this proposed exercise, you connect a provided Flask-based AI incident-investigation assistant to Azure Web PubSub so an on-call developer and a database specialist can follow one investigation from separate browsers. You complete Python business-logic functions that authorize operation access and publish progress, batched findings, and completion updates to a shared operation group. You verify that both responders receive the updates without starting duplicate backend work. You also test access isolation and recovery after a disconnect through a ready-made browser interface without editing rendering or interaction code.

The starter application uses a deterministic simulator that generates investigation progress and findings from a fictional production incident. An on-call developer and a database specialist observe one investigation from separate browser sessions. You can focus on the delivery behavior without provisioning an AI model or depending on variable model output. The backend retains operation state independently of the browser connections.

## Before you start

The exercise requires a real Azure Web PubSub resource so learners can observe managed connection and group delivery. The starter supplies Flask routes, authentication, and durable status retrieval. The official exercise is implemented in a separate repository from this proposal.

- An Azure subscription with permission to create a Web PubSub resource.
- Permission to assign the required data-plane role to the development identity, or an administrator who can provide the assignment.
- [Visual Studio Code](https://code.visualstudio.com/) on a supported platform.
- [Python 3.12 or later](https://www.python.org/downloads/).
- The latest [Azure CLI](/cli/azure/install-azure-cli).

> [!NOTE]
> Azure Web PubSub tiers, quotas, and pricing change regularly. Check [Azure Web PubSub pricing](https://azure.microsoft.com/pricing/details/web-pubsub/) before creating the exercise resource.

## Inspect the provided application

The starter separates background work from browser delivery so a disconnected client doesn't interrupt the operation. Its durable status endpoint provides the source of truth after a page reload. Learners edit only Python business-logic modules that the Flask application calls.

The starter includes:

- **Flask application:** Complete routes, authentication, and calls into the business-logic functions. Learners don't create route handlers or templates.
- **Connection business logic:** A suggested `operation_access.py` module with a function to authorize the operation and generate its scoped client access URL.
- **Notification business logic:** A suggested `notifications.py` module for event envelopes and group publishing.
- **Worker business logic:** A suggested `worker_logic.py` module for batched progress, generated findings, and completion. A deterministic simulator supplies text fragments about log analysis and database connection exhaustion.
- **Durable operation storage:** Current text, progress, terminal status, and a snapshot sequence watermark.
- **Notification support:** Stable operation event identifiers and a persistence boundary for updates.
- **Provided browser client:** A shared incident workspace with complete connection negotiation, group joining, message handlers, rendering, and state recovery. No client-code edits or frontend build steps are learner tasks.
- **Test identities:** An on-call developer and a database specialist authorized for the same investigation, plus a user without access. These identities let you verify shared delivery and operation isolation.

The simulator's output isn't an AI quality evaluation. It makes the delivery checks repeatable so you can distinguish a transport or client problem from changes in model behavior.

## Complete the real-time delivery path

The integration connects the existing worker to an operation-scoped Web PubSub group. The provided negotiation route calls the learner's Python function to authorize the operation and create its connection details. The completed browser client uses those details for group membership and status recovery.

The suggested learner tasks are:

1. You can download the starter project and identify the Python business-logic functions called by the provided Flask application.
1. You can provision Azure Web PubSub and configure the backend endpoint and development identity.
1. You can complete the connection-access function to authorize the operation and return a short-lived URL plus its permitted group.
1. You can complete the notification functions to construct event envelopes and publish to the operation group. The provided state helper supplies stable event IDs and sequence values.
1. You can update the worker's business logic to batch text fragments and record progress through the provided persistence helpers.
1. You can flush remaining text before recording completion. You can then publish completion with a reference to the stored result.
1. You can start one investigation as the on-call developer. You can then open that existing investigation as the database specialist in a separate browser session without submitting duplicate backend work.

The browser doesn't receive service keys or a role that allows arbitrary group publishing. Authentication and operation access checks remain backend responsibilities.

## Verify delivery and recovery

A successful WebSocket handshake isn't enough to prove that the AI experience works. You need to verify group isolation, complete text delivery, and state restoration after interruptions. The following checks cover the exercise's required outcomes.

| Check | Expected outcome |
|---|---|
| Start one investigation with an on-call developer and a database specialist as authorized observers | Both responders receive the same progress and generated findings; backend work starts once |
| Attempt negotiation as a user without access to the investigation | The backend denies access before issuing an operation token |
| Observe text generation | Notifications contain batches rather than one message for every simulated token |
| Inspect completion | The final text batch appears before completion; the stored result is available |
| Briefly interrupt one responder's network connection | The other responder continues receiving updates; the disconnected responder recovers without starting a second investigation |
| Reload the page after processing completes | The status snapshot restores completed state and the result reference |

You can also inspect the client's connection indicator during the interruption. A delivery problem should appear separately from the operation's processing status. If the SDK establishes a new session, the client restores membership and reconciles its durable snapshot.

The exercise doesn't require Flask scaffolding, client-side implementation, full event-history replay, a distributed sequence allocator, a human approval workflow, or production load testing. It doesn't connect to production logs or execute remediation actions. The conceptual client algorithms explain the provided browser behavior rather than introduce additional learner implementation tasks.

## Clean up exercise resources

The Web PubSub resource remains provisioned after you close the local application. You can remove the exercise resources when you finish to avoid charges for resources you no longer use. The external exercise identifies the resource group created specifically for this lab so cleanup doesn't affect unrelated applications.

After completing cleanup, you can return to the module to complete the assessment and review the summary. Keep the distinction between live delivery and durable operation state in mind when applying the pattern to a production AI solution.
