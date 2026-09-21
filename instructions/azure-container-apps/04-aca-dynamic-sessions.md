---
lab:
  topic: Azure Container Apps
  title: Execute code in a dynamic session in Azure Container Apps
  description: Learn how to securely execute AI-generated Python code, exchange files, and manage an isolated Azure Container Apps dynamic session.
  level: 300
  duration: 30
  islab: true
  primarytopics:
    - Azure
    - Azure Container Apps
---

# Execute code in a dynamic session in Azure Container Apps

Azure Container Apps dynamic sessions provide fast access to isolated execution environments for running AI-generated or user-submitted code. A code interpreter session keeps generated code outside the application process, preserves temporary files across related requests, and automatically removes the environment after a configurable idle period.

In this exercise, you deploy a Python code interpreter session pool, authorize your account with Microsoft Entra ID, and complete a Flask app that calls the Dynamic Sessions REST API. The app uploads sample data, executes a supplied analysis payload, validates the result, retrieves a generated chart from the reused session, detects an expected code failure, and explicitly deletes the session.

Tasks performed in this exercise:

- Download the project starter files and deploy a dynamic session pool
- Create a secure client with an application-generated session identifier
- Authenticate REST requests using Microsoft Entra ID
- Upload data and execute Python code in an isolated session
- List and download files from the reused session
- Detect an execution failure and explicitly delete the session
- Run the Flask app and inspect the REST operation results

This exercise takes approximately **30** minutes to complete.

## Before you start

In this section you review the tools and Azure permissions required to complete the exercise.

To complete the exercise, you need:

- An [Azure subscription](https://azure.microsoft.com/) with permissions to create a resource group and Azure Container Apps session pool, and to assign an Azure role.
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).
- A region that supports Azure Container Apps dynamic sessions.

## Download project starter files and deploy a dynamic session pool

In this section you download the project starter files, create a Python code interpreter session pool, assign the session executor role, and load the generated environment variables before you begin coding. The deployment typically completes within a few minutes.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/aca-dynamic-sessions-python.zip
    ```

1. Copy, or move, the file to a location in your system where you want to work on the project. Then unzip the file into a folder.

1. Launch Visual Studio Code (VS Code) and select **File > Open Folder...** in the menu, then choose the folder containing the project files.

1. Open the *azdeploy.py* deployment script and change the two values at the top of the script to meet your needs, then save your changes. **Note:** Do not change anything else in the script.

    ```
    "<your-resource-group-name>" # Resource Group name
    "<your-azure-region>" # Azure region for the resources
    ```

1. In the menu bar select **Terminal > New Terminal** to open a terminal window in VS Code.

1. Run the following command to **sign in to your Azure account**. Answer the prompts to select the Azure account and subscription for the exercise.

    ```
    az login
    ```

1. Run the following command to **install or upgrade the Azure Container Apps extension**. Dynamic session commands are provided by this extension.

    ```
    az extension add --name containerapp --upgrade --allow-preview true --yes
    ```

1. Run the following command to **register the Azure Container Apps resource provider**.

    ```
    az provider register --namespace Microsoft.App
    ```

### Create resources in Azure

In this section you run the deployment script to create the session pool, assign the role required to call the pool management API, and save the resource values used by the client.

1. Run the following command to **start the deployment script**. The script provides a menu for provisioning the exercise resources in the required order.

    ```
    python azdeploy.py
    ```

1. When the script is running, enter **1** to select **Create the code interpreter session pool**. This option creates the resource group and a PythonLTS session pool with a five-session concurrency limit, a 300-second idle cooldown, and outbound network access disabled.

    When the operation succeeds, the script saves the resource group, pool name, management endpoint, and location to *.env* and *.env.ps1*.

1. Enter **2** to select **Assign the session executor role**. This option assigns the **Azure ContainerApps Session Executor** role to your signed-in identity at the session pool scope. The role allows the client to execute code and exchange files using Microsoft Entra authentication.

1. Enter **3** to select **Check deployment status**. Confirm that the session pool status is **Succeeded** and the executor role shows **Yes**.

1. Enter **4** to exit the deployment script.

1. Run the following command to **load the resource values into your terminal session**.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

    Keep this terminal open. If you open a new terminal later, run the appropriate command again before starting the app.

## Complete the app

In this section you add the Dynamic Sessions REST client code to *dynamic_sessions_functions.py*. The prewritten Flask app in *app.py* calls these functions and presents the session workflow and REST operation results in the browser. You don't need to edit *app.py*.

1. Open the *client/dynamic_sessions_functions.py* file to begin adding code.

> **Tip:** Several code sections contain methods inside the **DynamicSessionClient** class. Make sure those methods remain indented four spaces so they align with the corresponding BEGIN and END markers.

### Add code to create the session client

In this section you create a Dynamic Sessions client with an unpredictable identifier controlled by the application. Reusing the identifier routes related requests to the same temporary environment, while keeping the complete value away from the browser prevents a user from targeting another session.

The **get_session_client()** function reads the pool management endpoint from **SESSION_POOL_ENDPOINT**, generates a UUID, and creates **DefaultAzureCredential**. The credential uses your Azure CLI sign-in during local development and can use a managed identity when an application is hosted in Azure.

1. Locate the **# BEGIN CREATE SESSION CLIENT CODE SECTION** comment and add the following code under the comment.

    ```python
    def get_session_client() -> "DynamicSessionClient":
        """Create a client from the session pool endpoint in the environment."""
        endpoint = os.environ.get("SESSION_POOL_ENDPOINT", "").strip()
        if not endpoint:
            raise ValueError("SESSION_POOL_ENDPOINT environment variable must be set")

        # The backend creates the identifier instead of accepting one from the
        # browser. Reusing this unpredictable value keeps related operations in the
        # same session without letting a user target another session.
        identifier = str(uuid4())

        # DefaultAzureCredential uses developer credentials locally and can use a
        # managed identity after the application is hosted in Azure.
        credential = DefaultAzureCredential()
        return DynamicSessionClient(
            endpoint,
            credential=credential,
            identifier=identifier,
        )
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to authenticate session requests

In this section you authenticate each REST request and add the query parameters that select the API version and session. Every call to the pool management endpoint requires a Microsoft Entra token for the Dynamic Sessions audience.

The **_headers()** method requests a valid token for **https://dynamicsessions.io/.default** and adds it as a bearer token. The **_params()** method sends the same application-generated identifier with every operation so uploads, executions, and downloads use one session.

1. Locate the **# BEGIN AUTHENTICATE SESSION REQUESTS CODE SECTION** comment and add the following code under the comment. Ensure the methods are indented inside the **DynamicSessionClient** class.

    ```python
        def _headers(self) -> dict[str, str]:
            # Request a token for the dynamic sessions audience on every operation.
            # DefaultAzureCredential handles token caching and renewal.
            token = self.credential.get_token(TOKEN_SCOPE).token
            return {"Authorization": f"Bearer {token}"}

        def _params(self) -> dict[str, str]:
            # The identifier routes every request to the same temporary environment.
            # A request allocates the session automatically if it does not exist.
            return {
                "api-version": API_VERSION,
                "identifier": self.identifier,
            }
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to upload a file to the session

In this section you upload the sample CSV file that the supplied analysis code processes. The code interpreter stores uploaded files in */mnt/data*, and subsequent requests with the same identifier can access them.

The **upload_file()** method opens the local file in binary mode and sends it to the **POST /files** endpoint as multipart form data. The context manager closes the file after the request, including when the API returns an error.

1. Locate the **# BEGIN UPLOAD SESSION FILE CODE SECTION** comment and add the following code under the comment. Ensure the method is indented inside the **DynamicSessionClient** class.

    ```python
        def upload_file(self, file_path: Path) -> dict[str, Any]:
            """Upload a local file into the session's /mnt/data directory."""
            # The service stores uploaded files in /mnt/data. Analysis code sent
            # with the same identifier can access the file without another upload.
            with file_path.open("rb") as source:
                response = self._request(
                    "POST",
                    "/files",
                    files={"file": (file_path.name, source, "text/csv")},
                    timeout=(5, 30),
                )
            return self._json_object(response)
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to execute and validate Python code

In this section you send the supplied analysis payload to the isolated Python interpreter and distinguish REST transport success from code execution success. Isolation protects the Flask process, but the application must still validate whether the submitted code completed successfully.

The **execute_code()** method calls **POST /executions** with an inline, synchronous execution request and a bounded timeout. After validating the HTTP response, the method checks for a **Succeeded** execution status. If Python raises an exception or the service reports an execution error, the method raises **CodeExecutionError** instead of returning a success-shaped result.

1. Locate the **# BEGIN EXECUTE CODE AND CHECK RESULT CODE SECTION** comment and add the following code under the comment. Ensure the method is indented inside the **DynamicSessionClient** class.

    ```python
        def execute_code(self, code: str) -> dict[str, Any]:
            """Execute Python code synchronously and verify its final status."""
            # The code runs in the isolated interpreter session, not in the Flask
            # process. The backend must still authorize and validate the task.
            response = self._request(
                "POST",
                "/executions",
                json={
                    "codeInputType": "Inline",
                    "executionType": "Synchronous",
                    "code": code,
                    "timeoutInSeconds": 60,
                    "outputStreamsMaxLength": 4096,
                },
                timeout=(5, 90),
            )
            execution = self._json_object(response)

            # A successful HTTP request only proves that the service accepted and
            # ran the operation. Python can still raise an execution-level error.
            if execution.get("status") != "Succeeded":
                result = execution.get("result")
                stderr = result.get("stderr") if isinstance(result, dict) else None
                error = execution.get("error")
                message = None
                if isinstance(error, dict):
                    message = error.get("message")
                    nested_error = error.get("error")
                    if not message and isinstance(nested_error, dict):
                        message = nested_error.get("message")
                raise CodeExecutionError(
                    str(stderr or message or "Code execution failed")
                )
            return execution
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to list and download session files

In this section you list the files retained in the reused session and download the SVG chart generated by the analysis payload. The file listing demonstrates that the uploaded CSV and generated artifact remain available across related calls.

The **list_files()** method calls **GET /files** and validates the returned collection. The **download_file()** method rejects directory components in the requested name, URL-encodes the safe filename, and calls **GET /files/{name}/content**. Validating the name prevents a caller from using path traversal to address an unintended location.

1. Locate the **# BEGIN MANAGE SESSION FILES CODE SECTION** comment and add the following code under the comment. Ensure both methods are indented inside the **DynamicSessionClient** class.

    ```python
        def list_files(self) -> list[dict[str, Any]]:
            """List files retained in the current session."""
            # The same identifier used for upload and execution exposes both the
            # original input and artifacts created by the generated code.
            response = self._request("GET", "/files", timeout=(5, 15))
            body = self._json_object(response)
            files = body.get("value", [])
            if not isinstance(files, list) or not all(
                isinstance(item, dict) for item in files
            ):
                raise DynamicSessionRequestError(
                    "Dynamic sessions API returned an unexpected file list"
                )
            return files

        def download_file(self, file_name: str) -> bytes:
            """Download one file from the current session."""
            # Reject directory components before placing the name in the URL. This
            # keeps file retrieval within the session's managed data directory.
            if Path(file_name).name != file_name:
                raise ValueError("A file name without a directory is required")
            safe_name = quote(file_name, safe="")
            response = self._request(
                "GET",
                f"/files/{safe_name}/content",
                timeout=(5, 30),
            )
            return response.content
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to delete the session

In this section you explicitly delete the session when the workflow is complete. The pool eventually removes an idle session after its cooldown period, but early deletion immediately releases temporary data and concurrent-session capacity.

The **delete_session()** method calls **DELETE /session** with the retained identifier and returns the HTTP status code. The app displays **204 No Content** when the service confirms that the session was deleted.

1. Locate the **# BEGIN DELETE SESSION CODE SECTION** comment and add the following code under the comment. Ensure the method is indented inside the **DynamicSessionClient** class.

    ```python
        def delete_session(self) -> int:
            """Immediately release the current dynamic session."""
            # The pool cooldown eventually removes idle sessions, but explicit
            # deletion releases capacity and temporary data as soon as work ends.
            response = self._request("DELETE", "/session", timeout=(5, 15))
            return response.status_code
    ```

1. Save your changes and take a few minutes to review the code.

## Configure the Python environment

In this section you create an isolated Python environment and install the Flask, Requests, and Azure Identity packages required by the client.

1. Run the following command to **navigate to the client directory**.

    ```
    cd client
    ```

1. Run the following command to **create a Python virtual environment**.

    ```
    python -m venv .venv
    ```

1. Run the following command to **activate the Python environment**.

    **Bash**
    ```bash
    source .venv/bin/activate
    ```

    **PowerShell**
    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

    If you use Git Bash on Windows, run **source .venv/Scripts/activate**.

1. Run the following command to **install the application dependencies**.

    ```
    pip install -r requirements.txt
    ```

## Run the app

In this section you run the completed Flask app and follow the dynamic session workflow. The left panel shows completed, next, and pending actions, while the right panel displays curated results from each REST operation.

1. Run the following command to **start the Flask app**. Make sure the virtual environment is active and the environment variables loaded earlier are still available in the terminal.

    ```
    python app.py
    ```

1. Open a browser and navigate to `http://localhost:5000`.

1. Select **1. Upload Sample Data**. The app generates a secure identifier and calls **POST /files**, which automatically allocates a session and uploads *operational-data.csv* to */mnt/data*.

    Confirm that step 1 changes to **Completed**, step 2 changes to **Next**, and the results show the shortened session identifier and uploaded file metadata.

1. Select **2. Execute Analysis**. The app reads *analysis_payload.py*, sends it to **POST /executions**, verifies the execution status, and validates the JSON written to standard output.

    Confirm that the results show a **Succeeded** status, the execution duration, and the following summary:

    - Four months
    - 1,000 total requests
    - An average of 250 requests
    - April as the peak month

1. Select **3. List Session Files**. The app calls **GET /files** using the same session identifier.

    Confirm that the results include both *operational-data.csv* and *trend.svg*. Their presence demonstrates that related operations reused the same temporary environment.

1. Select **4. Download Generated Chart**. The app calls **GET /files/trend.svg/content**, reports the content type and byte count, and downloads *trend.svg* to your browser's download location.

    Confirm that every workflow step now shows **Completed**. Open *trend.svg* and verify that the chart contains four bars with increasing heights.

1. Select **Test Failure Handling**. The app submits a small payload that raises a Python exception.

    Confirm that the results distinguish a completed REST request from a failed code execution and display the expected **RuntimeError**. This demonstrates why the client checks both the HTTP response and execution status.

1. Select **Delete Session**. The app calls **DELETE /session**, clears the local workflow state, and resets the workflow actions.

    Confirm that the result shows **204 No Content** and explains that the temporary data and session capacity were released before the idle cooldown expired.

# Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

In this section you review common deployment, authentication, environment, and code issues that can occur during the exercise.

**Resolve session pool deployment failures**
- If the session pool fails to deploy, the selected region might not support dynamic sessions or might not have available capacity.
- Change the **location** variable near the top of *azdeploy.py* to another supported region, run `python azdeploy.py` again, and select option 1.
- The script automatically deletes a session pool in the **Failed** or **Canceled** state before retrying.

**Check authentication and role assignment**
- Run `az account show` to confirm that Azure CLI is signed in to the intended subscription.
- Run the deployment script and select **Check deployment status** to confirm the session pool is ready and the executor role is assigned.
- If the app reports an authorization error immediately after deployment, wait a few minutes for the role assignment to propagate and try the action again.
- Confirm that your identity has the **Azure ContainerApps Session Executor** role scoped to the session pool.

**Verify environment variables**
- Confirm that both the *.env* and *.env.ps1* files exist in the project root and contain **SESSION_POOL_ENDPOINT**.
- Run `source .env` in Bash or `. .\.env.ps1` in PowerShell from the project root to load the environment values.
- If you open a new terminal, load the environment values again before running the app.

**Check code completeness and indentation**
- Ensure every code block was added between the matching BEGIN and END markers in *dynamic_sessions_functions.py*.
- Confirm that methods inside **DynamicSessionClient** are indented four spaces and that nested blocks use consistent indentation.
- Verify that no code outside the designated sections was removed or modified.

**Recover from an expired session**
- The session pool removes a session after 300 seconds without a request.
- If the app reports that *operational-data.csv* is missing after a long pause, select **1. Upload Sample Data** again to allocate a session and restore the input before continuing.

**Check Python environment and dependencies**
- Confirm that the virtual environment is active before running the app.
- Run `pip install -r requirements.txt` again if Flask, Requests, or Azure Identity can't be imported.
- If port 5000 is already in use, stop the other process before running `python app.py`.
