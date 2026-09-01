---
lab:
  topic: Integrate backend services
  title: Build a durable document-processing workflow with Azure Functions
  description: Learn how to build and test a durable document-processing workflow that coordinates parallel activities, retries, human approval, and failure compensation.
  level: 300
  duration: 35
  islab: true
  primarytopics:
    - Azure
    - Azure Functions
---

# Build a durable document-processing workflow

Durable Functions extends Azure Functions with stateful orchestration, allowing serverless apps to coordinate long-running work without manually managing checkpoints, queues, or polling loops. Orchestrator functions record their progress so workflows can recover after interruptions, retry failed activities, wait efficiently for external events, and resume from durable timers.

In this exercise, you complete a Python Durable Functions app that processes claim documents in parallel. You add idempotent result persistence, activity retries, failure compensation, a human approval path with a timeout, fan-out/fan-in orchestration, and external event delivery. You then run and test the workflow locally with Azurite.

Tasks performed in this exercise:

- Download the project starter files
- Add durable workflow code to the Function App
- Run and test the workflow locally

This exercise takes approximately **35** minutes to complete.

## Before you start

In this section you review the tools and access required to complete the exercise.

To complete the exercise, you need:

- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- [Azure Functions Core Tools](https://learn.microsoft.com/azure/azure-functions/functions-run-local) v4 or later.
- The [Azurite](https://marketplace.visualstudio.com/items?itemName=Azurite.azurite) extension for Visual Studio Code.

Durable Functions requires a storage provider to save orchestration history and state. This exercise uses Azurite as the local storage provider.

## Download project starter files

In this section you download the starter project and open it in Visual Studio Code. The project contains the Functions host configuration, sample workflow requests, local test runner, and a partially completed Function App.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/durable-functions-python.zip
    ```

1. Copy, or move, the file to a location in your system where you want to work on the project. Then unzip the file into a folder.

1. Launch Visual Studio Code and select **File > Open Folder...** in the menu, then choose the folder containing the project files.

1. Review the project files in the Explorer sidebar:

    - *function_app.py* contains the HTTP endpoints, activity functions, and orchestrator functions.
    - *host.json* configures the Durable Functions extension and task hub.
    - *local.settings.json* configures the Functions host to use Azurite locally.
    - *requirements.txt* contains the pinned Python dependencies.
    - The *samples* folder contains JSON request bodies for testing normal and retry behavior.
    - The *tests* folder contains the interactive workflow test runner.

## Complete the app

In this section you add the Durable Functions code that coordinates document processing, handles retries and human decisions, and persists terminal results. The request validation, simulated document activities, storage client, and HTTP boilerplate are already provided so you can focus on durable workflow concepts.

1. Open *function_app.py* in the Visual Studio Code Explorer sidebar.

>**Note:** Add each code block between its matching BEGIN and END comments. Some blocks are inside existing functions and must remain indented by four spaces.

### Add idempotent result persistence

In this section you add an activity function that writes one compact result record to Blob Storage. Durable Functions can execute an activity again if the host fails after an external write but before the activity completion is recorded, so externally visible writes should be idempotent.

The **persist_result()** activity uses the deterministic operation ID as the blob name and sets **overwrite** to false. If the blob already exists, the function reads the stored record and returns **AlreadyExists** instead of creating a duplicate. It also checks the document ID so an unexpected operation ID collision fails explicitly.

1. Locate the **# BEGIN IDEMPOTENT RESULT PERSISTENCE** comment and add the following code under the comment.

    ```python
    @app.activity_trigger(input_name="request")
    def persist_result(request):
        container = _get_or_create_container(RESULTS_CONTAINER)
        # The operation ID is the idempotency key for this external write.
        blob = container.get_blob_client(f"{request['operation_id']}.json")
        serialized = json.dumps(request, sort_keys=True)

        try:
            blob.upload_blob(serialized, overwrite=False)
            write_status = "Created"
            stored_result = request
        except ResourceExistsError:
            # A replay returns the original result instead of writing a duplicate.
            stored_result = json.loads(blob.download_blob().readall())
            if stored_result.get("document_id") != request["document_id"]:
                raise RuntimeError(
                    f"Operation ID collision for '{request['operation_id']}'."
                )
            write_status = "AlreadyExists"

        return {
            **stored_result,
            "result_url": blob.url,
            "write_status": write_status,
        }
    ```

1. Save your changes and take a few minutes to review the code.

### Add activity retries and failure compensation

In this section you add the first part of the per-document orchestrator. Each document receives a deterministic operation ID, and its extraction, classification, and summarization activities run in sequence with a bounded retry policy.

The **document_orchestrator()** function creates **RetryOptions** that allow each activity up to three attempts with a two-second first retry interval. Each activity receives the output of the previous activity. If an activity still fails after its retries, the orchestrator schedules **compensate_document()** and rethrows the exception so the workflow reports a technical failure instead of returning a success-shaped result.

1. Locate the **# BEGIN ACTIVITY RETRY WORKFLOW** comment and add the following code under the comment. The code must remain indented inside the **document_orchestrator()** function.

    ```python
        document = context.get_input()
        # new_uuid() remains deterministic when the orchestrator replays.
        operation_id = str(context.new_uuid())
        process_request = {**document, "operation_id": operation_id}
        retry_options = df.RetryOptions(2_000, 3)

        try:
            # Each activity can run up to three times before the workflow fails.
            extracted = yield context.call_activity_with_retry(
                "extract_text",
                retry_options,
                process_request,
            )
            classified = yield context.call_activity_with_retry(
                "classify_document",
                retry_options,
                extracted,
            )
            summarized = yield context.call_activity_with_retry(
                "generate_summary",
                retry_options,
                classified,
            )
        except Exception:
            # Compensate only after the activity exhausts its retry policy.
            yield context.call_activity(
                "compensate_document",
                {
                    "operation_id": operation_id,
                    "reason": "ProcessingFailed",
                },
            )
            raise
    ```

1. Save your changes and take a few minutes to review the code.

### Add human approval with a durable timeout

In this section you route low-confidence documents to a human decision without keeping a function invocation running. High-confidence documents complete automatically, while low-confidence documents wait for either an external approval event or a durable timer.

The orchestrator uses **wait_for_external_event()** and **create_timer()** to create two durable tasks, then calls **task_any()** to continue when the first task completes. An approval cancels the unused timer. A rejection or timeout schedules compensation and records an explicit terminal status.

1. Locate the **# BEGIN HUMAN APPROVAL WORKFLOW** comment and add the following code under the comment. The code must remain indented inside the **document_orchestrator()** function.

    ```python
        # High-confidence documents do not require a human decision.
        if summarized["confidence"] >= APPROVAL_CONFIDENCE_THRESHOLD:
            final_status = "Completed"
        else:
            yield context.call_activity(
                "notify_approver",
                {
                    **summarized,
                    "instance_id": context.instance_id,
                },
            )

            # Race the external event against a durable timer without blocking a worker.
            approval = context.wait_for_external_event("ApprovalResponse")
            deadline = context.current_utc_datetime + timedelta(
                seconds=APPROVAL_TIMEOUT_SECONDS
            )
            timeout = context.create_timer(deadline)
            winner = yield context.task_any([approval, timeout])

            if winner == approval:
                # Cancel the timer so the orchestration has no outstanding work.
                if not timeout.is_completed:
                    timeout.cancel()
                approval_payload = approval.result
                if isinstance(approval_payload, str):
                    approval_payload = json.loads(approval_payload)
                final_status = approval_payload["decision"]
            else:
                final_status = "ApprovalTimedOut"

            # Rejection and timeout both require a compensating action.
            if final_status != "Approved":
                yield context.call_activity(
                    "compensate_document",
                    {
                        "operation_id": operation_id,
                        "reason": final_status,
                    },
                )
    ```

1. Save your changes and take a few minutes to review the code.

### Add fan-out and fan-in orchestration

In this section you add the parent orchestrator that starts one sub-orchestration for each document. Scheduling the sub-orchestrations before waiting for them allows independent documents to process concurrently.

The **document_workflow()** function builds a deterministic child instance ID from the parent instance and document ID. It calls **call_sub_orchestrator()** for each document, then uses **task_all()** to wait for every child and return the compact result collection.

1. Locate the **# BEGIN FAN OUT FAN IN ORCHESTRATION** comment and add the following code under the comment.

    ```python
    @app.orchestration_trigger(context_name="context")
    def document_workflow(context: df.DurableOrchestrationContext):
        workflow_input = context.get_input()
        tasks = []

        # Schedule every child before yielding so documents run concurrently.
        for document in workflow_input["documents"]:
            child_instance_id = f"{context.instance_id}-{document['document_id']}"
            tasks.append(
                context.call_sub_orchestrator(
                    "document_orchestrator",
                    {
                        **document,
                        "batch_id": workflow_input["batch_id"],
                    },
                    child_instance_id,
                )
            )

        # Fan in after every child reaches a terminal state.
        results = yield context.task_all(tasks)
        return {
            "batch_id": workflow_input["batch_id"],
            "documents": results,
        }
    ```

1. Save your changes and take a few minutes to review the code.

### Add approval event delivery

In this section you complete the approval HTTP endpoint. The prewritten code validates the event ID and decision before the code you add sends the event to the waiting document sub-orchestration.

The **raise_event()** method targets the child instance ID and sends the named **ApprovalResponse** event. The event data becomes the result of the waiting task inside **document_orchestrator()**, allowing the durable workflow to resume from its saved state.

1. Locate the **# BEGIN APPROVAL EVENT DELIVERY** comment and add the following code under the comment. The code must remain indented inside the **submit_approval()** function.

    ```python
        instance_id = req.route_params["instance_id"]
        # Deliver the decision to the exact child waiting for this named event.
        await client.raise_event(
            instance_id,
            "ApprovalResponse",
            {
                "event_id": event_id,
                "decision": decision,
            },
        )
        return _json_response({"status": "Accepted"}, 202)
    ```

1. Save your changes and take a few minutes to review the code.

## Configure the Python environment

In this section you create a Python virtual environment and install the dependencies required by Azure Functions, Durable Functions, Azure Identity, and Blob Storage.

1. Run the following command in the VS Code terminal to create the Python environment.

    ```
    python -m venv .venv
    ```

1. Run the following command to activate the Python environment. On Linux or macOS, use the Bash command. On Windows, use the PowerShell command. If you use Git Bash on Windows, use **source .venv/Scripts/activate**.

    **Bash**
    ```bash
    source .venv/bin/activate
    ```

    **PowerShell**
    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

1. Run the following command to install the project dependencies.

    ```
    pip install -r requirements.txt
    ```

## Run the app locally

In this section you start Azurite and the local Functions host, then test automatic completion, human approval, retry, and timeout behavior.

1. Select **View > Command Palette...** in Visual Studio Code and run the **Azurite: Start** command. Installing the Azurite extension does not automatically start its local storage services. Confirm that the Visual Studio Code status bar shows **[Azurite Blob Service] Running on http://127.0.0.1:10000**. You can also open the Visual Studio Code notifications to review the Blob, Queue, and Table service startup messages.

1. Run the following command in the terminal with the virtual environment activated to start the local Functions host.

    ```
    func start
    ```

    The host lists the **start_workflow** and **submit_approval** HTTP endpoints along with the activity and orchestration triggers.

1. Open a second terminal in Visual Studio Code and activate the virtual environment using the appropriate command from the previous section.

1. Run the following command to start the interactive workflow test menu.

    ```
    python tests/run_workflow_tests.py
    ```

1. Enter **1** to start a mixed-confidence workflow. The test submits one high-confidence document that completes automatically and one low-confidence document that waits for an external approval event. Note the parent and child orchestration IDs displayed by the test.

1. Enter **2** to check the active workflow status. Confirm **Runtime status** is **Running**. In the **Documents** list, confirm **claim-001** has a **Completed** status and **claim-002** has a **Pending** status while it waits for approval.

    ```
    Instance ID: <ID for instance>
    Runtime status: Running
    Created: 2026-09-01T19:52:57Z
    Last updated: 2026-09-01T19:52:57Z
    Documents:
      - id=claim-001, orchestration=Completed, status=Completed
      - id=claim-002, orchestration=Running, status=Pending

    Press Enter to return to the menu...
    ```

1. Enter **3** to approve **claim-002**, the low-confidence document. The test sends an **ApprovalResponse** external event to its waiting child orchestration.

1. Wait a few seconds, then enter **2** again. Confirm **Runtime status** is **Completed**. In the **Documents** list, confirm **claim-001** has a **Completed** status and **claim-002** has an **Approved** status.

1. Enter **1** to start a new mixed-confidence workflow, then enter **4** to reject **claim-002**. Wait a few seconds and enter **2**. Confirm **claim-001** has a **Completed** status and **claim-002** has a **Rejected** status. The rejected status confirms that the workflow followed its compensation path.

1. Enter **5** to run the retry scenario. Confirm the output lists **claim-003-retry** with **status=Completed** and **retry_occurred=True**. Also confirm the test reports that **claim-003-retry** recovered from one simulated transient failure, followed by **PASS: retry scenario**.

1. Enter **6** to run the timeout scenario. The test waits approximately 30 seconds for the approval timer to expire.

1. Confirm the output lists **claim-002** with an **ApprovalTimedOut** status and the test reports **PASS: timeout scenario**. The timeout status confirms that the workflow followed its compensation path.

1. Enter **7** to exit the test menu. Return to the Functions host terminal and press **Ctrl+C** to stop the host. Then run **Azurite: Close** from the Visual Studio Code Command Palette to stop the local storage services.

## Troubleshooting

In this section you review common problems that can occur during local testing.

**Azurite or the Functions host doesn't start**
- Confirm Azure Functions Core Tools v4 or later is installed by running **func --version**.
- Run **Azurite: Start** before running **func start**. Having the Azurite extension installed is not sufficient; Durable Functions needs its Blob, Queue, and Table services to be running for local orchestration state.
- Confirm that the Visual Studio Code status bar shows **[Azurite Blob Service] Running on http://127.0.0.1:10000**, and review the Visual Studio Code notifications for the Blob, Queue, and Table service startup messages. An **Azurite** channel appears under **View > Output** only when the extension's debug logging setting is enabled.
- A connection-refused error for **127.0.0.1:10000** means that the Azurite Blob service is not running.
- Confirm *local.settings.json* contains **AzureWebJobsStorage** with the value **UseDevelopmentStorage=true**.
- If a previous Azurite process is still using ports 10000, 10001, or 10002, run **Azurite: Close** and start it again.

**Check code completeness and indentation**
- Ensure all five code blocks were added between the matching BEGIN and END comments in *function_app.py*.
- The activity retry, human approval, and approval event delivery blocks are inside existing functions and must be indented by four spaces.
- Confirm no prewritten code outside the designated sections was removed or modified.

**Workflow remains in the Running state**
- A low-confidence document intentionally waits for approval for up to 30 seconds. Send the approval event or wait for the durable timer to expire.
- Confirm the approval URL contains the parent instance ID followed by **-claim-002**.
- Review the Functions host terminal for the child orchestration ID and activity errors.
