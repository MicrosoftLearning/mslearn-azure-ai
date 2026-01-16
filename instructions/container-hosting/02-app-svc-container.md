---
lab:
    topic: Container hosting
    title: 'Deploy a container to Azure App Service'
    description: '(In development) Learn how to ....'
---

# Deploy a container to Azure App Service

In this exercise, you ...

Tasks performed in this exercise:

- Download the project starter files
- Create resources in Azure
- ...

This exercise takes approximately **30** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- The latest version of the [Azure CLI](/cli/azure/install-azure-cli?view=azure-cli-latest).

## Download project starter files and deploy Azure services

In this section you download the project starter files and use a script to deploy the necessary services to your Azure subscription.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/appsvc-container-python.zip
    ```

1. Copy, or move, the file to a location in your system where you want to work on the project. Then unzip the file into a folder.

1. Launch Visual Studio Code (VS Code) and select **File > Open Folder...** in the menu, then choose the folder containing the project files.

1. The project contains deployment scripts for both Bash (*azdeploy.sh*) and PowerShell (*azdeploy.ps1*). Open the appropriate file for your environment and change the two values at the top of the script to meet your needs, then save your changes. **Note:** Do not change anything else in the script.

    ```
    "<your-resource-group-name>" # Resource Group name
    "<your-azure-region>" # Azure region for the resources
    ```

1. In the menu bar select **Terminal > New Terminal** to open a terminal window in VS Code.

1. Run the following command to login to your Azure account. Answer the prompts to select your Azure account and subscription for the exercise.

    ```
    az login
    ```

1. Run the following command to ensure your subscription has the necessary resource provider to install Azure Container Registry (ACR).

    ```
    az provider register --namespace Microsoft.ContainerRegistry
    ```

### Create resources in Azure

In this section you run the deployment script to deploy the necessary services to your Azure subscription.

1. Make sure you are in the root directory of the project and run the appropriate command in the terminal to launch the deployment script. The deployment script will deploy ACR and create a file with environment variables needed for exercise.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

1. When the script is running, enter **1** to launch the **1. Create Azure Container Registry and build container image** option. This option creates the ACR service and uses ACR Tasks to build and push the image to the registry.

1. When the previous operation is finished, enter **2** to launch the **Create App Service Plan** options. This option creates the App Service plan needed for web app.

    >**Note:** A file containing environment variables is created after the App Service plan is created. You use these variables throughout the exercise.

1. When the previous operation is finished, enter **4** to exit the deployment script.

1. Run the appropriate command to load the environment variables into your terminal session from the file created in a previous step.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

    >**Note:** Keep the terminal open. If you close it and create a new terminal, you might need to run the command to create the environment variable again.

## Create the web app

In this section you create the web app with CLI commands. You then configure the web app with a system-assigned managed identity to give the app access to the image in ACR.

1. Run the following command to create a Web App for Containers configured to pull from your container registry.

    ```azurecli
    az webapp create \
        --resource-group $RESOURCE_GROUP \
        --plan $APP_PLAN \
        --name $APP_NAME \
        --container-image-name $ACR_NAME.azurecr.io/docprocessor:v1
    ```

    At this point, the app might not be able to start successfully because the web app doesn't yet have permission to pull from your private registry.

1. Run the following command to enable a system-assigned managed identity on the web app.

    ```azurecli
    az webapp identity assign \
        --resource-group $RESOURCE_GROUP \
        --name $APP_NAME
    ```

Get the principal ID and grant ACR pull permissions:

```azurecli
PRINCIPAL_ID=$(az webapp identity show \
    --resource-group $RESOURCE_GROUP \
    --name $APP_NAME \
    --query principalId \
    --output tsv)

ACR_ID=$(az acr show \
    --resource-group $RESOURCE_GROUP \
    --name $ACR_NAME \
    --query id \
    --output tsv)

az role assignment create \
    --assignee $PRINCIPAL_ID \
    --scope $ACR_ID \
    --role AcrPull
```

Configure the web app to use managed identity for registry authentication:

```azurecli
az webapp config set \
    --resource-group $RESOURCE_GROUP \
    --name $APP_NAME \
    --acr-use-identity true \
    --acr-identity [system]
```

Update the container settings to use the registry with managed identity:

```azurecli
az webapp config container set \
    --resource-group $RESOURCE_GROUP \
    --name $APP_NAME \
    --container-image-name $ACR_NAME.azurecr.io/docprocessor:v1 \
    --container-registry-url https://$ACR_NAME.azurecr.io
```

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues while completing this exercise, try the following troubleshooting steps:

**Verify Azure authentication and environment variables**
- Run **az account show** to confirm you're logged in to the correct Azure subscription.
- Verify your environment variables are set by running **echo $ACR_NAME** (Bash) or **$env:ACR_NAME** (PowerShell).
- If variables are empty, re-run **source .env** (Bash) or **. .\.env.ps1** (PowerShell).

**Verify ACR deployment**
- Navigate to the [Azure portal](https://portal.azure.com) and locate your resource group.
- Confirm that the Azure Container Registry exists and shows a **Provisioning State** of **Succeeded**.
- Run **az acr list --output table** to verify your registry is accessible.

**Troubleshoot build failures**
- Check the build output for error messages - common issues include missing Dockerfile or incorrect file paths.
- Verify you're running commands from the project root directory (where the *api* folder is located).
- Run **az acr task list-runs --registry $ACR_NAME --output table** to see the status of recent builds.

