---
lab:
    topic: 'Container hosting'
    title: 'Deploy an AI API with a local model-serving sidecar'
    description: 'Deploy a chat API and a local Phi-3 model sidecar to Azure App Service, then use a local Flask client to test the application.'
    level: 300
    duration: 45
---

# Deploy an AI API with a local model-serving sidecar

In this exercise, you deploy a Python chat API as the main App Service container and a local model server as a sidecar. The deployment script builds both images in Azure Container Registry. A separate Flask client runs on your development computer and calls the public chat API. You configure managed-identity image pulls, `localhost` communication, a shared temporary volume, and container-specific diagnostics.

> [!NOTE]
> The model-server image runs the Microsoft Phi-3 Mini 4K Instruct CPU INT4 ONNX model with Microsoft ONNX Runtime GenAI. The model is approximately 2.7 GB and is distributed under the MIT license. The deployment script pins the model repository revision and includes its license in the image.

> [!IMPORTANT]
> The deployment uses a P1v3 App Service plan because the main API and model sidecar share the plan's 2 vCPUs and 8 GB of memory. The plan incurs charges while it exists. Complete the exercise in one session, which should take approximately 30-45 minutes after deployment, and delete the resource group immediately afterward. If P1v3 capacity is unavailable in the selected region, choose another region and run the deployment again. P0v3 has less memory and is not recommended for the initial deployment.

> [!NOTE]
> The first model-server image build downloads the Phi-3 model and can take 10-20 minutes. The first container start also takes several minutes while App Service pulls the image and ONNX Runtime loads the model. Keep the deployment terminal open during the build and use the readiness endpoint before sending an inference request.

## Download project starter files and deploy Azure resources

In this section you download the project starter files and run the deployment script. The script creates the resource group, builds both container images in Azure Container Registry, creates the P1V3 App Service plan and sidecar-enabled web app, and configures a user-assigned managed identity with permission to pull the private images.

1. Open a browser and enter the following URL to download the starter files. The file is saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/app-svc-sidecar-python.zip
    ```

1. Copy or move the downloaded file to a working folder, and then extract its contents.

1. Open the extracted folder in Visual Studio Code.

1. Open *azdeploy.py*, change the **rg** and **location** values at the top of the file, and save your changes. Do not change anything below the **DON'T CHANGE ANYTHING BELOW THIS LINE** comment.

1. Open a new terminal in Visual Studio Code.

1. Run the following command to sign in to Azure. This authenticates Azure CLI and lets you select the subscription where the exercise resources are created.

    ```
    az login
    ```

1. Run the following commands to register the Azure resource providers used by the exercise. Registration enables the subscription to create Azure Container Registry and App Service resources.

    ```
    az provider register --namespace Microsoft.ContainerRegistry
    az provider register --namespace Microsoft.Web
    ```

1. Run the following command to start the deployment script. The script provides a menu for provisioning the exercise resources in the required order.

    ```
    python azdeploy.py
    ```

1. Enter **1** to select **Create Azure Container Registry and build both images**. This option creates the registry and uses ACR Tasks to build and push the chat API and Phi-3 model-server images.

    The first model-server build downloads the approximately 2.7 GB Phi-3 CPU INT4 model and can take 10-20 minutes. Keep the terminal open until both builds finish. If the deployment fails, review the **Troubleshooting** section.

1. Enter **2** to select **Create App Service resources and configure managed identity**. This option creates the P1V3 plan and sidecar-enabled web app. It also creates and assigns the user-assigned managed identity, grants it the **AcrPull** role, updates the values in *sitecontainers-spec.json*, and writes the resource values to *.env* and *.env.ps1*.

1. Enter **3** to select **Check deployment status**. Confirm that the registry, both images, plan, web app, and managed identity are available.

1. Enter **4** to exit the deployment script.

1. Run the following command to load the resource values in Bash. The command exports the values from *.env* so the remaining Azure CLI commands and the local client can use them.

    ```bash
    source .env
    ```

    If you use PowerShell, run the following command instead:

    ```powershell
    . .\.env.ps1
    ```

The exercise images use port **8000** for the main API and port **11434** for the model server. The main API reads **MODEL_ENDPOINT** and sends inference requests to the sidecar through **http://localhost:11434**. The web app doesn't serve the chat API until you define and apply a container with **isMain** set to **true**.

## Define the main and sidecar containers

In this section you configure the main chat API container and the Phi-3 model sidecar in the provided *sitecontainers-spec.json* file. The main API receives external traffic on port **8000**, while the model server remains internal on port **11434**. Both containers use the user-assigned managed identity to pull their private images.

The project includes *sitecontainers-spec.template.json* with placeholders for subscription-specific values. The deployment script preserves that template and generates *sitecontainers-spec.json* with your registry name and managed identity client ID, but it doesn't apply the specification. In this section you review the generated configuration and then deploy both containers.

1. Open *sitecontainers-spec.json* in Visual Studio Code.

1. Review the **main-api** container definition and identify the following settings:

    - **image** points to the **chat-api:v1** image in your Azure Container Registry.
    - **targetPort** is **8000**, which is the port that receives external App Service traffic.
    - **isMain** is **true**, which designates this container as the public application.
    - **authType** is **UserAssigned**, and **userManagedIdentityClientId** contains the client ID of the managed identity created by the deployment script.
    - **MODEL_ENDPOINT** is **http://localhost:11434**, which uses the shared network namespace to reach the model sidecar.
    - The **models/current** volume is mounted at **/app/models** as read-only.

1. Review the **model-server** container definition and identify the following settings:

    - **image** points to the **model-server:v1** image in your Azure Container Registry.
    - **targetPort** is **11434** and **isMain** is **false**, so the model server remains an internal sidecar.
    - The container uses the same user-assigned managed identity as the main API.
    - **MODEL_NAME** identifies the Microsoft Phi-3 Mini ONNX model.
    - The **models/current** volume is mounted at **/models** with write access so the sidecar can create the model manifest.

1. Run the following command to apply the main and sidecar container definitions. This creates the runtime relationship between the public chat API and its internal model sidecar.

    **Bash**

    ```bash
    az webapp sitecontainers create \
      --name "$APP_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --sitecontainers-spec-file ./sitecontainers-spec.json
    ```

    **PowerShell**

    ```powershell
    az webapp sitecontainers create `
      --name $env:APP_NAME `
      --resource-group $env:RESOURCE_GROUP `
      --sitecontainers-spec-file .\sitecontainers-spec.json
    ```

1. Run the following command to verify the stored container definitions. This confirms that App Service saved both containers with their assigned roles and target ports.

    **Bash**

    ```bash
    az webapp sitecontainers list \
      --name "$APP_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --output table
    ```

    **PowerShell**

    ```powershell
    az webapp sitecontainers list `
      --name $env:APP_NAME `
      --resource-group $env:RESOURCE_GROUP `
      --output table
    ```

1. Confirm that **main-api** is the main container, **model-server** is the sidecar, the target ports are different, and both definitions use the expected managed identity client ID.

## Verify the model sidecar is ready

In this section you verify that App Service pulled both images and that the Phi-3 model sidecar finished loading before you start the local chat client. The first container start can take several minutes.

1. Run the following command to retrieve the model-server log. The container-specific log distinguishes model loading and startup issues from errors in the main API.

    **Bash**

    ```bash
    az webapp sitecontainers log \
      --name "$APP_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --container-name model-server
    ```

    **PowerShell**

    ```powershell
    az webapp sitecontainers log `
      --name $env:APP_NAME `
      --resource-group $env:RESOURCE_GROUP `
      --container-name model-server
    ```

1. Confirm that the log reports the model loaded successfully and that the model server listens on port **11434**.

1. Run the following command to call the API readiness operation. This confirms that the main API can reach the model sidecar through the shared network namespace. The response should report that the local model dependency is available without exposing model configuration or internal paths.

    **Bash**

    ```bash
    curl --fail-with-body "${CHAT_API_URL}/health/ready"
    ```

    **PowerShell**

    ```powershell
    Invoke-RestMethod -Uri "$env:CHAT_API_URL/health/ready"
    ```

## Verify the shared volume

In this section you verify that the main API and model sidecar access the same shared volume through different container paths. The model server writes a small manifest to **/models/manifest.json** after it loads the model, and the main API reads the same file through **/app/models/manifest.json**.

1. Run the following command to request the non-sensitive model manifest fields. A successful response proves that the sidecar wrote the manifest and the main API read it through the shared volume.

    **Bash**

    ```bash
    curl --fail-with-body "${CHAT_API_URL}/model-info"
    ```

    **PowerShell**

    ```powershell
    Invoke-RestMethod -Uri "$env:CHAT_API_URL/model-info"
    ```

1. Confirm that the response identifies the Microsoft Phi-3 Mini model, Microsoft ONNX Runtime GenAI, CPU INT4 quantization, and a ready state.

The two containers use different mount paths, but both definitions reference the **models/current** volume subpath. The model-server mount has write access so it can create the manifest, while the main API mount is read-only. The volume is non-persistent because the sidecar can recreate the manifest each time it starts. Data that must survive restarts or be shared across scaled-out instances belongs in durable storage.

## Set up the Python environment

In this section you create a Python virtual environment and install the dependencies needed for the local Flask client. The client provides the browser chat experience without adding a third container to the App Service application.

1. Run the following command to navigate to the *client* directory.

    ```
    cd client
    ```

1. Run the following command to create a virtual environment for the Python application. Depending on your environment, the command might be **python** or **python3**.

    ```
    python -m venv .venv
    ```

1. Run the following command to activate the Python environment. **Note:** On Linux/macOS, use the Bash command. On Windows, use the PowerShell command. If using Git Bash on Windows, use **source .venv/Scripts/activate**.

    **Bash**
    ```bash
    source .venv/bin/activate
    ```

    **PowerShell**
    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

1. Run the following command to install the Python dependencies. This installs the **flask** and **requests** libraries.

    ```bash
    pip install -r requirements.txt
    ```

Next, you start the local Flask application and use it to communicate with the chat API and model sidecar in Azure.

## Run the chat client

In this section you start the local Flask web application and verify end-to-end inference through the chat API and Phi-3 model sidecar. The client reads the **CHAT_API_URL** value that you loaded from *.env* or *.env.ps1*.

1. Ensure you are still in the *client* directory with the virtual environment activated. You should see **(.venv)** in your terminal prompt.

1. Run the following command to start the Flask application.

    ```bash
    python app.py
    ```

1. Open a browser and navigate to `http://127.0.0.1:5000`.

1. Confirm that the page reports **Model ready**, and then send a short message. The browser keeps up to eight recent user and assistant messages in the current tab and sends the bounded history through the local Flask client to the chat API. The history is not stored by either server and is cleared when you reload the page.

The response confirms several boundaries. App Service routes external traffic to the main container, the chat API connects to **localhost:11434**, and the model server returns a completion.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.
