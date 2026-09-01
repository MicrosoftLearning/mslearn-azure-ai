---
lab:
  topic: Integrate backend services
  title: Build a durable document-processing workflow
  description: Learn how to build, test, and deploy a durable document-processing workflow that coordinates parallel activities, retries, human approval, and compensation.
  level: 300
  duration: 45
  islab: true
  primarytopics:
    - Azure
    - Azure Functions
---

# Build a durable document-processing workflow

Durable Functions extends Azure Functions with stateful orchestration, allowing serverless apps to coordinate long-running work without manually managing checkpoints, queues, or polling loops. Orchestrator functions record their progress so workflows can recover after interruptions, retry failed activities, wait efficiently for external events, and resume from durable timers.

In this exercise, you complete a Python Durable Functions app that processes claim documents in parallel. You add idempotent result persistence, activity retries, failure compensation, a human approval path with a timeout, fan-out/fan-in orchestration, and external event delivery. You first run and test the workflow locally with Azurite, and then use a deployment script to create a Flex Consumption function app and test the workflow in Azure.

Tasks performed in this exercise:

- Download the project starter files
- Add durable workflow code to the Function App
- Run and test the workflow locally
- Deploy the Function App to Azure
- Test the deployed workflow

This exercise takes approximately **45** minutes to complete.

## Before you start

In this section you review the tools and access required to complete the exercise.

To complete the exercise, you need:

- An Azure subscription. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- [Azure Functions Core Tools](https://learn.microsoft.com/azure/azure-functions/functions-run-local) v4 or later.
- The [Azurite](https://marketplace.visualstudio.com/items?itemName=Azurite.azurite) extension for Visual Studio Code.
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).

Durable Functions requires a storage provider to save orchestration history and state. This exercise uses Azurite as the local storage provider and an Azure Storage account after deployment.

## Download project starter files

In this section you download the starter project and open it in Visual Studio Code. The project contains the Functions host configuration, sample workflow requests, deployment script, and a partially completed Function App.

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
    - *azdeploy.py* creates the Azure resources and deploys the completed app.

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
        blob = container.get_blob_client(f"{request['operation_id']}.json")
        serialized = json.dumps(request, sort_keys=True)

        try:
            blob.upload_blob(serialized, overwrite=False)
            write_status = "Created"
            stored_result = request
        except ResourceExistsError:
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
        operation_id = str(context.new_uuid())
        process_request = {**document, "operation_id": operation_id}
        retry_options = df.RetryOptions(2_000, 3)

        try:
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

            approval = context.wait_for_external_event("ApprovalResponse")
            deadline = context.current_utc_datetime + timedelta(
                seconds=APPROVAL_TIMEOUT_SECONDS
            )
            timeout = context.create_timer(deadline)
            winner = yield context.task_any([approval, timeout])

            if winner == approval:
                if not timeout.is_completed:
                    timeout.cancel()
                approval_payload = approval.result
                if isinstance(approval_payload, str):
                    approval_payload = json.loads(approval_payload)
                final_status = approval_payload["decision"]
            else:
                final_status = "ApprovalTimedOut"

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

In this section you start Azurite and the local Functions host, then test automatic completion, human approval, retry, and timeout behavior before creating any Azure resources.

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

## Deploy the app to Azure

In this section you configure and run the deployment script. The script creates an Azure Storage account, user-assigned managed identity, Application Insights resource, and Linux Flex Consumption function app. It assigns the Blob, Queue, and Table data roles required by Durable Functions, configures identity-based storage access, and deploys the project with a remote Python build.

1. Open *azdeploy.py* and change the two values at the top of the script to meet your needs, then save your changes. Select an Azure region that supports the Flex Consumption plan.

    ```python
    rg = "<your-resource-group-name>"
    location = "<your-azure-region>"
    ```

1. Run the following command to sign in to your Azure account. Answer the prompts to select your Azure account and subscription for the exercise.

    ```
    az login
    ```

1. Run the following commands to register the resource providers used by the deployment.

    ```
    az provider register --namespace Microsoft.Web
    az provider register --namespace Microsoft.Storage
    az provider register --namespace Microsoft.Insights
    az provider register --namespace Microsoft.ManagedIdentity
    ```

1. Run the following command to start the deployment script.

    ```
    python azdeploy.py
    ```

1. Enter **1** to run the **1. Create Azure resources** option.

    The script verifies that the selected region supports Flex Consumption, creates the resources, assigns the managed identity roles, and configures the function app. The operation can take several minutes. If deployment fails because the selected region isn't available or has insufficient capacity, refer to the Troubleshooting section.

1. When the menu returns, enter **2** to run the **2. Deploy the Function App** option. The script creates a deployment package and uses a remote build so the Python dependencies are built for the Linux Functions environment.

1. Enter **3** to run the **3. Check deployment status** option. Confirm that the storage account reports **Succeeded**, the Function App reports **Running**, and the script creates *.env* and *.env.ps1* with the deployed Function App settings.

1. Enter **4** to exit the deployment script.

## Test the app in Azure

In this section you load the deployed Function App settings and use the interactive test menu to exercise approval, rejection, retry, and timeout behavior in Azure.

1. Run the appropriate command to load the deployed Function App settings into your terminal session.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

1. Run the following command to start the interactive workflow test menu.

    ```
    python tests/run_workflow_tests.py
    ```

1. Enter **1** to start a mixed-confidence workflow, then enter **2**. Confirm **Runtime status** is **Running**, **claim-001** has a **Completed** status, and **claim-002** has a **Pending** status.

1. Enter **3** to approve **claim-002**. Wait a few seconds, then enter **2** again.

1. Confirm **Runtime status** is **Completed**, **claim-001** has a **Completed** status, and **claim-002** has an **Approved** status.

1. Enter **1** to start a new mixed-confidence workflow, then enter **4** to reject **claim-002**. Wait a few seconds and enter **2**. Confirm **claim-001** has a **Completed** status and **claim-002** has a **Rejected** status. The rejected status confirms compensation after an explicit rejection.

1. Enter **5** to run the retry scenario in Azure. Confirm the output lists **claim-003-retry** with **status=Completed** and **retry_occurred=True**, followed by **PASS: retry scenario**.

1. Enter **6** to run the timeout scenario in Azure. The test waits approximately 30 seconds for the approval timer to expire. Confirm the output lists **claim-002** with an **ApprovalTimedOut** status, followed by **PASS: timeout scenario**. The timeout status confirms timer-based compensation when no external event arrives.

1. Enter **7** to exit the test menu.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

In this section you review common problems that can occur during local testing and Azure deployment.

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

**Flex Consumption isn't available**
- Run **az functionapp list-flexconsumption-locations -o table** to list supported regions.
- Change the **location** value at the top of *azdeploy.py*, rerun the script, and select option 1.
- If a supported region reports a capacity or quota error, select another supported region and retry. The script deletes a failed Function App before recreating it.

**Managed identity authorization fails**
- The deployment script assigns **Storage Blob Data Contributor**, **Storage Queue Data Contributor**, and **Storage Table Data Contributor** to the Function App identity.
- Role assignments can take several minutes to propagate. Wait briefly, then rerun deployment option 2 or repeat the workflow request.
- Run deployment option 3 and confirm the Function App is **Running** before testing it.

**The deployed endpoint returns 401 Unauthorized**
- Rerun the command that retrieves **functionKeys.default** and rebuild the workflow URL.
- Confirm both the workflow and approval URLs include the **code** query parameter.
- Confirm the Function App and resource group variables match the values displayed by *azdeploy.py*.

**Remote build or deployment fails**
- Confirm the local project root contains *function_app.py*, *host.json*, and *requirements.txt*.
- Confirm your Azure CLI session is still authenticated by running **az account show**.
- Rerun option 2. The script creates a new temporary deployment package for each attempt.
