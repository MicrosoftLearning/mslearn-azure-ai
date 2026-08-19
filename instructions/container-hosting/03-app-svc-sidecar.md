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

1. Run the following command to **sign in to Azure**. Follow the prompts to select the subscription you want to use for the exercise.

    ```
    az login
    ```

1. Run the following commands to **register the Azure resource providers used by the exercise**.

    ```
    az provider register --namespace Microsoft.ContainerRegistry
    az provider register --namespace Microsoft.Web
    ```

1. Run the following command to **start the deployment script**.

    ```
    python azdeploy.py
    ```

1. Enter **1** to select **Create Azure Container Registry and build both images**. This option creates the registry and uses ACR Tasks to build and push the chat API and Phi-3 model-server images.

    The first model-server build downloads the approximately 2.7 GB Phi-3 CPU INT4 model and can take 10-20 minutes. Keep the terminal open until both builds finish. If the deployment fails, review the **Troubleshooting** section.

1. Enter **2** to select **Create App Service resources and configure managed identity**. This option creates the P1V3 plan and sidecar-enabled web app. It also creates and assigns the user-assigned managed identity, grants it the **AcrPull** role, and writes the resource values to *.env* and *.env.ps1*.

1. Enter **3** to select **Check deployment status**. Confirm that the registry, both images, plan, web app, and managed identity are available.

1. Enter **4** to exit the deployment script.

1. Run the following command to **load the resource values in Bash**. The command exports the values from *.env* so the remaining Azure CLI commands and the local client can use them.

    ```bash
    source .env
    ```

    If you use PowerShell, run the following command instead:

    ```powershell
    . .\.env.ps1
    ```

The exercise images use port **8000** for the main API and port **11434** for the model server. The main API reads **MODEL_ENDPOINT** and sends inference requests to the sidecar through **http://localhost:11434**. The web app doesn't serve the chat API until you define and apply a container with **isMain** set to **true**.

## Define the main and sidecar containers

You can place both container definitions in one JSON specification. The main API receives external traffic on port `8000`. The model server remains internal on port `11434`, and both definitions use managed identity for private image pulls.

You can create a file named `sitecontainers-spec.json` from the following pattern. Replace **\<registry-name>** with the value of **ACR_NAME** and **\<identity-client-id>** with the value of **IDENTITY_CLIENT_ID** from the environment file. JSON doesn't expand shell variables automatically.

```json
[
  {
    "name": "main-api",
    "properties": {
      "image": "<registry-name>.azurecr.io/chat-api:v1",
      "targetPort": "8000",
      "isMain": true,
      "authType": "UserAssigned",
      "userManagedIdentityClientId": "<identity-client-id>",
      "environmentVariables": [
        {
          "name": "MODEL_ENDPOINT",
          "value": "http://localhost:11434"
        }
      ],
      "volumeMounts": [
        {
          "volumeSubPath": "models/current",
          "containerMountPath": "/app/models",
          "readOnly": true
        }
      ]
    }
  },
  {
    "name": "model-server",
    "properties": {
      "image": "<registry-name>.azurecr.io/model-server:v1",
      "targetPort": "11434",
      "isMain": false,
      "authType": "UserAssigned",
      "userManagedIdentityClientId": "<identity-client-id>",
      "environmentVariables": [
        {
          "name": "MODEL_NAME",
          "value": "microsoft/Phi-3-mini-4k-instruct-onnx"
        }
      ],
      "volumeMounts": [
        {
          "volumeSubPath": "models/current",
          "containerMountPath": "/models",
          "readOnly": false
        }
      ]
    }
  }
]
```

You can apply the complete specification with one command:

```bash
az webapp sitecontainers create \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --sitecontainers-spec-file ./sitecontainers-spec.json
```

You can verify that App Service stores one main container and one sidecar:

```bash
az webapp sitecontainers list \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --output table
```

Confirm that `main-api` has the main role and that the two target ports are different. You should also compare the image tags and managed identity client ID with the values you intended to deploy.

## Configure the local chat client

The local Flask client provides the browser chat experience without adding a third container to the App Service application. The client reads the **CHAT_API_URL** value that you loaded from *.env* or *.env.ps1*, so it calls the web app created for your exercise.

1. Run the following command to **change to the client directory**.

    ```bash
    cd client
    ```

1. Run the following command to **create a Python virtual environment**.

    ```bash
    python -m venv .venv
    ```

1. Run the following command to **activate the virtual environment in Bash**.

    ```bash
    source .venv/bin/activate
    ```

    If you use PowerShell, run the following command instead:

    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

1. Run the following command to **install the client dependencies**.

    ```bash
    pip install -r requirements.txt
    ```

1. Run the following command to **start the local chat client**.

    ```bash
    python app.py
    ```

## Verify end-to-end inference

Container startup can take longer when the sidecar loads a model. You can inspect the model-server log until the process reports that it listens on port `11434`. A successful startup confirms the image pull and process launch boundaries.

You can retrieve the model-server log with the container-specific command:

```bash
az webapp sitecontainers log \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --container-name model-server
```

You can retrieve the public chat API URL for direct diagnostic requests:

```bash
APP_URL="https://${APP_NAME}.azurewebsites.net"

echo "$APP_URL"
```

Open `http://localhost:5000` in a browser, wait until the page reports **Model ready**, and send a short message. The browser keeps up to eight recent user and assistant messages in the current tab and sends the bounded history through the local Flask client to the chat API. The history is not stored by either server and is cleared when you reload the page.

The response confirms several boundaries. App Service routes external traffic to the main container, the chat API connects to `localhost:11434`, and the model server returns a completion. The model-server log should show the corresponding request.

You can also test the chat API directly:

```bash
curl --fail-with-body \
  --request POST \
  --header "Content-Type: application/json" \
  --data '{"messages":[{"role":"user","content":"Explain Azure App Service sidecars in one sentence."}]}' \
  "${APP_URL}/api/chat"
```

You can also call the API's limited readiness operation:

```bash
curl --fail-with-body "${APP_URL}/health/ready"
```

The readiness response should report that the local model dependency is available. It shouldn't expose model configuration, internal paths, or other sensitive details.

## Verify the shared volume

The model server writes a small manifest to `/models/manifest.json` after it loads the exercise model. The main API reads the same file through `/app/models/manifest.json`. The paths differ, but both mounts use the `models/current` volume subpath.

You can request the API operation that reports the non-sensitive manifest fields:

```bash
curl --fail-with-body "${APP_URL}/model-info"
```

Confirm that the response identifies the exercise model and reports a ready state. If the API can't read the file, compare both container definitions. The `volumeSubPath` values must match, and the main API mount should remain read-only.

The volume is non-persistent. The exercise application can recreate the manifest whenever the sidecar starts. Production data that must survive restarts or be shared across scaled-out instances belongs in a durable service such as Azure Storage.

## Diagnose an injected port failure

You can now create a controlled connectivity failure by changing the main API's `MODEL_ENDPOINT` to port `11435` in `sitecontainers-spec.json`. Keep the model-server target port at `11434`. Reapplying the file creates a mismatch between the client endpoint and the listening process.

You can apply the changed specification and test readiness again:

```bash
az webapp sitecontainers create \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --sitecontainers-spec-file ./sitecontainers-spec.json
```

```bash
curl --fail-with-body "${APP_URL}/health/ready"
```

The readiness operation should report that the model dependency is unavailable. You can inspect the main container log to find the connection refusal:

```bash
az webapp sitecontainers log \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --container-name main-api
```

Use the diagnostic sequence from the preceding unit. You can confirm that both images pull, both processes start, and the model server listens on `11434`. Comparing the main API environment value with the sidecar target port isolates the mismatch.

You can restore `MODEL_ENDPOINT` to `http://localhost:11434`, reapply the specification, and refresh the chat application. When the model status returns to **Model ready**, send another message. A successful response verifies that the configuration correction resolves the original failure.

## Review metrics and remove resources

You can review App Service CPU, memory, response time, and request metrics after the tests. The measurements show the combined behavior of the main API and model-serving sidecar. Production plan selection requires representative concurrency and a longer observation window.

When you finish the exercise, you can remove the resource group if it contains only exercise resources:

```bash
az group delete \
  --name "$RESOURCE_GROUP" \
  --yes \
  --no-wait
```

Resource deletion prevents continued App Service charges. The command doesn't wait for deletion to finish, so you can verify removal later in the Azure portal or with `az group show`.
