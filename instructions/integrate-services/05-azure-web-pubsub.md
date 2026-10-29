---
lab:
  topic: Integrate backend services
  title: Stream AI investigation updates with Azure Web PubSub
  description: Share one AI investigation's progress, batched findings, and completion updates with authorized incident responders through Azure Web PubSub
  level: 300
  duration: 30
  islab: true
  primarytopics:
    - Azure
    - Azure Web PubSub
---

# Stream AI investigation updates with Azure Web PubSub

Azure Web PubSub manages persistent client connections so a backend can broadcast updates to multiple observers without managing its own WebSocket infrastructure. For a long-running AI investigation, live notifications keep responders informed while durable storage preserves the findings independently of their browser connections.

In this exercise, you deploy Azure Web PubSub and Azure Blob Storage, then complete a Python Flask app that shares one investigation with an on-call developer and a database specialist on a single page. A deterministic simulator supplies progress and findings about a fictional database incident, so you can focus on delivery and recovery without deploying an AI model. You generate scoped connection details, record and publish events, and batch findings before notifying both responders.

Tasks performed in this exercise:

- Download the project starter files.
- Deploy Azure Web PubSub and Blob Storage with Microsoft Entra ID access.
- Add Python code to connect observers and publish stored investigation updates.
- Run the app to verify shared delivery, independent connections, and recovery after a disconnect.

This exercise takes approximately **30** minutes to complete.

## Before you start

In this section you review the tools and permissions required to provision the resources and run the local app.

To complete the exercise, you need:

- An [Azure subscription](https://azure.microsoft.com/) with permission and quota to create Azure Web PubSub and storage resources, register resource providers, and assign Azure roles. **Owner**, or **Contributor** combined with **Role Based Access Control Administrator**, at the appropriate scope provides the required resource and role-assignment permissions.
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- The latest [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli). A later step installs or upgrades its **webpubsub** extension.
- **Optional:** The [Ruff extension for Visual Studio Code](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff) for formatting and linting Python code.

The deployment uses the **Standard_S1** Web PubSub tier and a **Standard_LRS** storage account. These resources incur charges while provisioned. Review [Azure Web PubSub pricing](https://azure.microsoft.com/pricing/details/web-pubsub/) and delete the resources when you finish.

## Download project starter files and deploy Azure Web PubSub

In this section you download the project starter files and run the deployment script to create Azure Web PubSub, a storage account, and a private Blob container. You then verify Microsoft Entra ID access and load the resource values into your terminal.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/azure-web-pubsub-python.zip
    ```

1. Copy, or move, the file to a location in your system where you want to work on the project. Then unzip the file into a folder.

1. Launch Visual Studio Code (VS Code) and select **File > Open Folder...** in the menu, then choose the folder containing the project files.

1. Open the *azdeploy.py* deployment script and change the two values at the top of the script to meet your needs, then save your changes. **Note:** Do not change anything else in the script.

    ```python
    rg = "<your-resource-group-name>"  # Resource Group name
    location = "<your-azure-region>"   # Azure region for the resources
    ```

    Choose a resource group dedicated to this exercise and an Azure region that supports Azure Web PubSub.

1. In the menu bar, select **Terminal > New Terminal** to open a terminal window in VS Code.

1. Run the following command to **sign in to Azure**. Answer the prompts to select your Azure account and subscription for the exercise.

    ```
    az login
    ```

1. Run the following commands to **register the resource providers needed for this exercise**. They wait for registration to finish. The deployment script checks that both providers are registered before creating their resources.

    ```
    az provider register --namespace Microsoft.SignalRService --wait
    az provider register --namespace Microsoft.Storage --wait
    ```

1. Run the following command to **install or upgrade the Web PubSub CLI extension**. The deployment script uses the extension to provision Azure Web PubSub.

    ```
    az extension add --upgrade --name webpubsub
    ```

1. Run the following command to **start the deployment script**. The script provides a menu for provisioning the exercise resources in the required order.

    ```
    python azdeploy.py
    ```

1. When the script menu appears, enter **1** to run **1. Create Azure Web PubSub and assign its Entra role**. This option creates or configures:

    - The resource group, if it doesn't already exist.
    - An Azure Web PubSub resource with a unique name and key authentication disabled.
    - A **Web PubSub Service Owner** role assignment for your signed-in identity at the Web PubSub resource scope, allowing the backend to generate client connection tokens and publish updates using Microsoft Entra authentication.

    The script waits for the operation to finish and reports any deployment failure. If the deployment fails, refer to the **Troubleshooting** section. After each menu operation finishes, press **Enter** to return to the menu.

1. Enter **2** to run **2. Create storage account and assign its Entra role**. This option creates or configures:

    - A storage account with a unique name, shared-key access disabled, and anonymous Blob access disabled.
    - A **Storage Blob Data Contributor** role assignment for your signed-in identity at the storage account scope, allowing the app to create, read, and update investigation state and results using Microsoft Entra authentication.

1. Enter **3** to run **3. Create the private Blob container**. This option creates the private **investigations** container using your Microsoft Entra identity. The script retries briefly while a new storage role assignment takes effect.

1. Enter **4** to run **4. Verify deployment and create environment files**. Confirm that both resources show **Succeeded** and that the Web PubSub client-token API and Blob container read-access checks show **Ready**.

    After verification succeeds, this option creates *.env* and *.env.ps1* in the project root with the **WEBPUBSUB_ENDPOINT**, **WEBPUBSUB_HUB**, **BLOB_ACCOUNT_URL**, and **BLOB_CONTAINER** values used by the app.

1. Enter **5** to exit the deployment script.

1. Run the appropriate command to **load the Web PubSub and Blob Storage resource values into your terminal session**.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

    > **Note:** Keep the terminal open. If you open a new terminal later, run the appropriate command again to reload the environment variables.

## Complete the app

In this section you complete four functions in *client/webpubsub_functions.py* to generate scoped connection details, store and publish updates, and batch findings. The Flask app, storage helper, simulator, and browser interface are prewritten. The app uses **DefaultAzureCredential** for Web PubSub and Blob Storage, and **authorize()** restricts starting an investigation to its on-call owner. Both responder views are demo roles on one page, not separate signed-in users.

1. Open the *client/webpubsub_functions.py* file in VS Code. Leave the imports, constants, and helper functions outside the **BEGIN / END** markers unchanged.

> **Tip:** To maintain proper code indentation, paste the code flush with the left margin (column 1), select all of the pasted lines, and press **Tab** to align the block with the **BEGIN / END** markers. Press **Shift+Tab** to outdent if needed.

### Add code to generate connection details

In this section you generate a short-lived connection URL that permits an observer to join only the selected investigation's group.

The **connection_details()** function checks access and requests a short-lived URL with permission to join or leave only that investigation's group. The browser uses the URL to connect and join the group; it can't publish messages.

1. Locate the **# BEGIN GENERATE CONNECTION DETAILS** comment and add the following code under the comment.

    ```python
    def connection_details(
        client: WebPubSubServiceClient, operation: Operation, observer: str,
    ) -> dict[str, str]:
        """Issue a short-lived connection URL and the authorized investigation group."""
        authorize(operation, observer)
        group = group_name(operation.operation_id)
        # Scope group membership permission to this investigation; do not grant send permission.
        token = client.get_client_access_token(
            user_id=observer,
            roles=[f"webpubsub.joinLeaveGroup.{group}"],
            minutes_to_expire=5,
        )
        return {"url": token["url"], "group": group}
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to record an event

In this section you persist investigation updates before attempting live delivery so a disconnected observer can recover the current state later.

The **record_event()** function delegates to the provided **OperationStore.record()** method. That method updates the stored investigation and returns an event envelope containing the operation ID, event type, payload, sequence number, and stable event ID. The browser uses the sequence information to ignore duplicate events and reconcile its view with a stored snapshot when it detects a gap.

1. Locate the **# BEGIN RECORD EVENT** comment and add the following code under the comment.

    ```python
    def record_event(
        store: OperationStore, operation_id: str,
        event_type: EventType, payload: dict[str, object],
    ) -> Event:
        """Persist an investigation update and return its sequenced event envelope."""
        return store.record(operation_id, event_type, payload)
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to publish an event

In this section you publish each stored event to the investigation's Web PubSub group and handle temporary delivery failures without discarding the saved findings.

The **publish_event()** function calls **send_to_group()** with a JSON event. It makes up to three delivery attempts, waiting briefly between retries. If delivery still fails, it records a delivery warning and lets processing continue. A successful send clears the warning. Retries can produce duplicate notifications, so the browser uses the event's stable ID and sequence rather than assuming exactly-once delivery.

1. Locate the **# BEGIN PUBLISH EVENT** comment and add the following code under the comment.

    ```python
    def publish_event(
        client: WebPubSubServiceClient, store: OperationStore, event: Event,
    ) -> None:
        """Deliver a stored event with bounded retries and track live-delivery problems."""
        for attempt in range(PUBLISH_ATTEMPTS):
            try:
                client.send_to_group(
                    group=group_name(event["operation_id"]),
                    message=event, content_type="application/json",
                )
            except AzureError as exc:
                logger.warning(
                    "Delivery attempt %s failed for event %s (%s).",
                    attempt + 1, event["event_id"], type(exc).__name__,
                )
                if attempt + 1 < PUBLISH_ATTEMPTS:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                # Keep processing: observers can recover stored findings after reconnecting.
                store.delivery_problem(
                    event["operation_id"],
                    "Live delivery failed. Findings remain stored; reconnect this view to recover them.",
                )
                return
            store.delivery_problem(event["operation_id"], None)
            return
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to run the investigation

In this section you connect the simulator to persistence and delivery, batching findings before publishing them.

The **run_investigation()** function records progress and findings before publishing them, flushes the final batch, then publishes a reference to the stored result. If processing fails, it emits a failed event only while the investigation is still running. A delivery failure doesn't stop the worker.

1. Locate the **# BEGIN RUN INVESTIGATION** comment and add the following code under the comment.

    ```python
    def run_investigation(
        store: OperationStore,
        client: WebPubSubServiceClient,
        operation_id: str,
        fragments: Callable[[], Iterable[tuple[str, str, int]]] = simulate,
    ) -> None:
        """Batch simulated findings, store each update, and notify connected observers."""
        def emit(event_type: EventType, payload: dict[str, object]) -> None:
            # Persist first so a missed live message does not lose investigation state.
            event = record_event(store, operation_id, event_type, payload)
            publish_event(client, store, event)

        pending: list[str] = []
        current_stage = ""
        try:
            for stage, fragment, progress in fragments():
                if stage != current_stage:
                    emit("progress", {"stage": stage, "progress": progress})
                    current_stage = stage
                pending.append(fragment)
                # Batch small fragments to reduce live-message traffic.
                if len(pending) == BATCH_FRAGMENTS:
                    emit("findings", {"text": "".join(pending)})
                    pending.clear()
            if pending:
                emit("findings", {"text": "".join(pending)})
            # Publish a reference to the stored result rather than resending all findings.
            emit("completed", {"result_ref": f"/api/operations/{operation_id}/result"})
        except (AzureError, ValueError, RuntimeError) as exc:
            logger.exception("Investigation %s failed (%s).", operation_id, type(exc).__name__)
            operation, _ = store.load(operation_id)
            # Do not replace a terminal status if the failure occurred after completion.
            if operation.status == "running":
                emit("failed", {"error": "The investigation failed. Check the backend terminal for details."})
    ```

1. Save your changes and take a few minutes to review the code.

## Configure the Python environment

In this section you navigate to the client app directory, create a Python virtual environment, activate it, and install the pinned application dependencies.

1. Run the following command to **navigate to the client directory**. Use the same terminal where you loaded the generated resource values.

    ```
    cd client
    ```

1. Run the following command to **create a virtual environment**. The environment keeps the exercise dependencies separate from other Python projects.

    ```
    python -m venv .venv
    ```

1. Run the appropriate command to **activate the Python virtual environment**. If you use Git Bash on Windows, run **source .venv/Scripts/activate**.

    **Bash**
    ```bash
    source .venv/bin/activate
    ```

    **PowerShell**
    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

1. Run the following command to **install the app dependencies**. The requirements include Flask, Microsoft Entra authentication, and the Web PubSub and Blob Storage SDKs.

    ```
    pip install -r requirements.txt
    ```

## Run the app

In this section you verify that one backend investigation sends updates to both responder views, then disconnect one view and recover its findings without starting another worker.

1. Run the following command to **start the Flask app**. Make sure the virtual environment is active and the Web PubSub and Blob Storage environment variables are loaded in this terminal. Keep the terminal running while you use the browser.

    ```
    python app.py
    ```

1. Open a browser and navigate to `http://localhost:5000` to access the app. The page shows **Investigation actions**, **On-call developer**, and **Database specialist**.

1. Select **Create investigation**. The app saves a new investigation in Blob Storage and connects both responder views to its Web PubSub group. Confirm both **Connection** indicators show **Connected** and **Processing** shows **pending**.

1. Select **Start investigation**. The action runs as the on-call developer, who owns the investigation. Watch both views move through **Inspecting application logs**, **Inspecting database connections**, and **Preparing the investigation result**.

    Findings arrive in batches rather than one message for every simulated fragment. The **Live events** counters should increase, showing that the views receive Web PubSub messages rather than only retrieving stored snapshots.

1. Wait until both views show **Processing: completed** and full progress bars. Confirm both display the same accumulated findings, including the final recommendation to validate a fix in a non-production environment. Each view should show **Worker starts: 1**.

    **Sequence** includes updates recovered through stored snapshots; **Live events** counts only new Web PubSub notifications received on this page. **Duplicates ignored** can remain zero during normal delivery. **Worker starts: 1** confirms that connecting a second observer didn't start another investigation worker.

1. Select **Create investigation** again, then select **Start investigation**. As soon as findings begin appearing, select **Disconnect** in the **Database specialist** view.

    Confirm its connection changes to **Disconnected by you**. Its displayed findings stop updating, while the **On-call developer** view continues receiving findings from the same running investigation. The simulated analysis normally takes about 10 seconds, excluding service-request time.

1. Let the on-call view reach **completed**, then select **Reconnect** in the database specialist view.

    The view establishes a connection, rejoins the investigation group, and retrieves the current stored snapshot. Confirm it recovers the complete findings and **completed** status, with **Worker starts: 1**. Its **Live events** count can be lower because the snapshot restores state without replaying every missed notification.

1. Reload the page without changing its URL. The URL includes the selected investigation ID, so both views reconnect to that investigation and restore its saved state. Confirm the completed findings return without starting another investigation.

    The worker runs in the local Flask process, not in Azure Web PubSub. Blob Storage preserves saved state, but restarting Flask doesn't resume unfinished work. Keep the backend running during the disconnect and reload checks.

1. Close the browser and then return to the VS Code terminal and press **Ctrl+C** to stop the app.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

In this section you diagnose deployment, authentication, and delivery problems while keeping live connection state separate from investigation processing state.

**Resolve deployment failures**

- Confirm your account can create resources, register providers, and assign Azure roles. A **Contributor** role alone doesn't allow role assignment.
- If the Web PubSub SKU is unavailable, the region lacks capacity, or your subscription has insufficient quota, choose another supported region or request the required quota.
- To change regions, exit the script and update **location** above the divider in *azdeploy.py*. Existing resources can't move regions. Remove the exercise resources in the old region before redeploying with the same names, or use a new dedicated resource group.
- Retry menu option **1** for Web PubSub or **2** for storage. The script detects failed or canceled resources, deletes them, and waits for deletion before attempting creation again. Don't delete unrelated resources.
- If a provider registration is still in progress, wait for the registration command to finish before retrying deployment.

**Check Microsoft Entra access**

- Use the same Azure account for deployment and local SDK authentication. If your Azure CLI session has expired, repeat the sign-in step.
- Menu option **1** assigns **Web PubSub Service Owner**; option **2** assigns **Storage Blob Data Contributor**. New assignments can take several minutes to become effective.
- If container creation reports an authorization error, allow time for role propagation, then retry option **3**. Retry option **4** until both data-plane checks succeed before starting the app.
- Don't enable key authentication or add service keys to work around an access error. The exercise uses **DefaultAzureCredential** for service requests.

**Verify generated configuration**

- The app requires **WEBPUBSUB_ENDPOINT**, **WEBPUBSUB_HUB**, **BLOB_ACCOUNT_URL**, and **BLOB_CONTAINER** in its process environment.
- Menu option **4** generates *.env* and *.env.ps1* only after verification succeeds. Rerun that option to regenerate configuration; don't manually edit the files.
- Load the generated file in the terminal that will start the app. From the project root, run **source .env** in Bash or **. .\.env.ps1** in PowerShell, then navigate to *client*. From *client*, use **source ../.env** or **. ..\.env.ps1** instead.
- After changing deployment settings, regenerate and reload the values, then restart the app.

**Check code completeness and dependencies**

- Confirm all four code blocks are inside the matching **BEGIN / END** markers in *webpubsub_functions.py*. Keep the nested **emit()** helper inside **run_investigation()** and use consistent spaces for indentation.
- Leave the prewritten **authorize()** helper and the supporting app, storage, simulator, and browser files unchanged.

**Check the Python environment**

- Confirm the virtual environment is active before running the app.
- Verify that all packages from *requirements.txt* were installed successfully. If needed, activate the environment and run **pip install -r requirements.txt** from the *client* directory.
- Make sure you run **python app.py** from the *client* directory. On systems where Python is available only as **python3**, use that executable for the deployment script, virtual-environment creation, and app startup.

**Investigate connection failures or missing live updates**

- Check the Flask terminal and the browser's error messages. Both responder views must join the investigation group; a running backend alone doesn't confirm live delivery.
- Ensure your browser can reach the Web PubSub endpoint over secure WebSockets and load the JavaScript SDK from **esm.sh**. A corporate firewall, proxy, or browser extension can block either connection.
- If **Connection failed**, **Group recovery failed**, or **Stopped** appears, resolve the reported problem and select **Reconnect** in the affected view.
- A **completed** status with a zero **Live events** count can mean the view recovered through snapshots rather than live delivery. Create a new investigation, connect both views before starting it, and verify that the counters increase while it runs.
- If the app reports a live-delivery warning, the findings remain in Blob Storage. Resolve the service-access or network problem and reconnect the affected view to recover its stored state.
- If an action reports an unknown observer context or asks you to reload, refresh the page so it receives current demo context and request-protection tokens.

**Understand interrupted processing**

- Disconnecting a responder or reloading the browser doesn't stop a worker while Flask remains running.
- Stopping Flask stops its background worker. At the next startup, the app marks abandoned running investigations **interrupted** rather than resuming them.
- Create a new investigation to run the analysis again after a backend restart. Don't run multiple Flask instances against the same exercise container during this lab.
