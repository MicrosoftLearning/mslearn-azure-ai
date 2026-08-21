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

## Download project starter files and deploy Azure resources

In this section you download the project starter files and run the deployment script. The script creates the resource group, Azure Container Registry, both container images, a user-assigned managed identity granted **AcrPull** on the registry, the App Service plan, and the sidecar-enabled web app with the identity attached at creation.

1. Open a browser and enter the following URL to download the starter files. The file is saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/app-svc-sidecar-python.zip
    ```

1. Copy or move the downloaded file to a working folder, and then extract its contents.

1. Open the extracted folder in Visual Studio Code.

1. 1. Open the *azdeploy.py* deployment script and change the two values at the top of the script to meet your needs, then save your changes. **Note:** Do not change anything else in the script.

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

1. Enter **1** to select **Create Azure Container Registry and build both images**. This option creates the registry, verifies that its authentication-as-ARM policy supports managed-identity image pulls, and uses ACR Tasks to build and push the chat API and Phi-3 model-server images.

    The first model-server build downloads the approximately 2.7 GB Phi-3 CPU INT4 model and can take 5-10 minutes. Keep the terminal open until both builds finish. If the deployment fails, review the **Troubleshooting** section.

1. Enter **2** to select **Create user-assigned managed identity and assign AcrPull**. This option creates a user-assigned managed identity and grants it the **AcrPull** role on your registry so App Service can pull the private images.

1. Enter **3** to select **Create App Service resources with the managed identity attached**. This option creates the App Service plan and sidecar-enabled web app with the user-assigned managed identity attached at creation, configures App Service to wait for the model readiness operation during warmup, generates *sitecontainers-spec.json* with your registry name and the identity's client ID, and writes the resource values to *.env* and *.env.ps1*.

1. Enter **4** to select **Check deployment status**. Confirm that the registry, both images, managed identity, AcrPull assignment, plan, and web app are all available.

1. Enter **5** to exit the deployment script.

1. Run the following command to load the resource values in Bash. The command exports the values from *.env* so the remaining Azure CLI commands and the local client can use them.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

The exercise images use port **8080** for the main API and port **11434** for the model server. The main API reads **MODEL_ENDPOINT** and sends inference requests to the sidecar through **http://localhost:11434**. The web app doesn't serve the chat API until you define and apply a container with **isMain** set to **true**.

## Define the main and sidecar containers

In this section you configure the main chat API container and the Phi-3 model sidecar in the provided *sitecontainers-spec.json* file. The main API receives external traffic on port **8080**, while the model server remains internal on port **11434**. Both containers use the shared user-assigned managed identity to pull their private images.

The project includes *sitecontainers-spec.template.json* with a placeholder for the registry name. The deployment script preserves that template and generates *sitecontainers-spec.json* with your registry name, but it doesn't apply the specification. In this section you review the generated configuration and then deploy both containers.

1. Open *sitecontainers-spec.json* in Visual Studio Code.

1. Review the **chat-api** container definition and identify the following settings:

    - **image** points to the **chat-api:v1** image in your Azure Container Registry.
    - **targetPort** is **8080**, which is the supported port that receives external App Service traffic.
    - **isMain** is **true**, which designates this container as the public application.
    - **authType** is **UserAssigned**, which instructs App Service to use a user-assigned managed identity to pull the image.
    - **userManagedIdentityClientId** is the client ID of the shared user-assigned managed identity that has the **AcrPull** role on your registry.
    - **MODEL_ENDPOINT** references the app setting of the same name. App Service resolves its value to **http://localhost:11434**, which uses the shared network namespace to reach the model sidecar.
    - The **models/current** volume is mounted at **/app/models** as read-only.

1. Review the **model-server** container definition and identify the following settings:

    - **image** points to the **model-server:v1** image in your Azure Container Registry.
    - **targetPort** is **11434** and **isMain** is **false**, so the model server remains an internal sidecar.
    - The container uses the same user-assigned managed identity as the main API to pull its image.
    - **MODEL_NAME** references the app setting of the same name, which identifies the Microsoft Phi-3 Mini ONNX model.
    - The **models/current** volume is mounted at **/models** with write access so the sidecar can create the model manifest.

1. Run the following command to enable **Always On** for the web app. Always On tells App Service to keep the containers resident and to send a lightweight internal ping to the site every few minutes. Without it, App Service unloads idle containers after about 20 minutes, and the next request pays the full cold-start cost of pulling the images and reloading the Phi-3 model into memory. Enabling Always On is standard practice for containerized workloads that hold a model in memory.

    **Bash**
    ```bash
    az webapp config set \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --always-on true
    ```

    **PowerShell**
    ```powershell
    az webapp config set `
        --name $env:APP_NAME `
        --resource-group $env:RESOURCE_GROUP `
        --always-on true
    ```

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
        --sitecontainers-spec-file ./sitecontainers-spec.json
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

1. Confirm that **chat-api** is the main container, **model-server** is the sidecar, the target ports are different, and both definitions use **UserAssigned** authentication with the same **userManagedIdentityClientId**.

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

1. Run the following command to activate the Python environment.

    > **Note:** On Linux/macOS, use the Bash command. On Windows, use the PowerShell command. If using Git Bash on Windows, use **source .venv/Scripts/activate**.

    **Bash**
    ```bash
    source .venv/bin/activate
    ```

    **PowerShell**
    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

1. Run the following command to install the Python dependencies. This installs the **flask** and **requests** libraries.

    ```
    pip install -r requirements.txt
    ```

Next, you start the local Flask application and use it to communicate with the chat API and model sidecar in Azure.

## Run the chat client

In this section you start the local Flask web application and verify end-to-end inference through the chat API and Phi-3 model sidecar. The client reads the **CHAT_API_URL** value that you loaded from *.env* or *.env.ps1*.

1. Ensure you are still in the *client* directory with the virtual environment activated. You should see **(.venv)** in your terminal prompt.

1. Run the following command to start the Flask application.

    ```
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

## Troubleshooting

If you encounter issues while completing this exercise, try the following troubleshooting steps:

**Verify resource deployment**
- Navigate to the [Azure portal](https://portal.azure.com) and locate your resource group.
- Confirm that the Azure Container Registry, App Service plan, and web app show a **Provisioning State** of **Succeeded**.
- Run the deployment script's **Check deployment status** option and confirm the registry, both container images, plan, web app, and managed identity are all available before applying the sitecontainers specification.

**Resolve deployment failures**
- If option 1 or option 3 fails, it's most often due to a temporary lack of capacity for the container registry or App Service plan SKU in your chosen region.
- Exit the script, change the **location** variable near the top of *azdeploy.py* to a different region such as eastus2, australiaeast, or canadacentral, then run the script again and choose the failed option.
- The failed resource is deleted automatically before the next attempt.

**Model-server build times out or fails**
- The first model-server build downloads the approximately 2.7 GB Phi-3 CPU INT4 model and can take 5-10 minutes.
- If the build fails partway through, network instability during the model download is the most common cause. Run option 1 again to retry.
- If the second build consistently fails, check the ACR build logs in the Azure portal under your registry's **Services** > **Tasks** > **Runs** blade for the specific error.

**First container start returns 503 or Issues Detected**
- The first container start pulls both images from ACR, loads the 2.7 GB Phi-3 model into memory, and starts both containers. This can take several minutes on the initial start.
- During this window, **az webapp sitecontainers log** can return a 503 from the SCM endpoint, and the portal **Properties** > **Site status** page can briefly show **Issues Detected** with an **Unknown** state and empty last-error fields.
- Wait a few minutes and retry the command. Do not click **Repair** on the site-status page while the containers are still starting; it restarts the app and resets model-load progress.
- If the state remains **Unknown** or the log command keeps returning 503 after 10 minutes, open **Diagnose and solve problems** in the portal and run the **Linux Container Start Failure** and **Container Issues** detectors for a root cause.

**AcrPull role assignment not yet effective**
- If the web app reports an image pull error immediately after option 3 completes, the AcrPull role assignment to the user-assigned managed identity can take a short time to propagate.
- Wait a couple of minutes, then run **az webapp restart --name $APP_NAME --resource-group $RESOURCE_GROUP** to trigger a new pull attempt.

**Managed-identity image pull reports token validation failed**
- App Service managed-identity image pulls require the registry's authentication-as-ARM policy to be enabled. Option 1 verifies this policy before building the images.
- If the script reports that the policy is disabled, run the following command to enable it, then run option 1 again.

    **Bash**
    ```bash
    az acr config authentication-as-arm update \
        --registry "$ACR_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --status enabled
    ```

    **PowerShell**
    ```powershell
    az acr config authentication-as-arm update `
        --registry $env:ACR_NAME `
        --resource-group $env:RESOURCE_GROUP `
        --status enabled
    ```

**Verify environment variables**
- Check that both the *.env* and *.env.ps1* files exist in the project root and contain the **RESOURCE_GROUP**, **APP_NAME**, **ACR_NAME**, and **CHAT_API_URL** values.
- Run **source .env** in Bash or **. .\.env.ps1** in PowerShell to load the environment variables into your terminal session before running Azure CLI commands or the local client.

**Check the sitecontainers specification**
- Confirm *sitecontainers-spec.json* exists next to *azdeploy.py* and that the registry name in each **image** field matches your registry (**$ACR_NAME.azurecr.io**).
- If the file is missing or still contains the **\<registry-name>** or **\<managed-identity-client-id>** placeholder, run option 3 in the deployment script again to regenerate it.
- If **az webapp sitecontainers create** fails, run **az webapp sitecontainers list --name $APP_NAME --resource-group $RESOURCE_GROUP --output table** to see the current stored definitions.

**Chat API readiness check reports the model isn't available**
- The **/health/ready** operation reports the model dependency as available only after the model-server sidecar finishes loading Phi-3 and writes the shared manifest.
- Retrieve the model-server log with **az webapp sitecontainers log --container-name model-server** and confirm the log reports the model loaded successfully and that the model server listens on port **11434**.
- If the log shows the model is still loading, wait a few minutes and call **/health/ready** again.

**Check Python environment and dependencies**
- Confirm the virtual environment is activated before running the app; you should see **(.venv)** in your terminal prompt.
- Verify that all packages from *requirements.txt* were installed successfully by running **pip list**.
- If the local Flask app can't reach the chat API, confirm that **CHAT_API_URL** points to **https://\<your-app-name>.azurewebsites.net** and that the readiness operation returns a successful response.
