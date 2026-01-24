---
lab:
    topic: Azure Container Apps
    title: 'Configure autoscaling for an API using KEDA'
    description: 'Learn how to configure KEDA-based autoscaling in Azure Container Apps using HTTP concurrency triggers (no extra Azure services).'
---

# Configure autoscaling using KEDA triggers

AI applications often experience unpredictable workloads—a surge in inference requests, batch jobs, or sudden spikes from an agent-based workflow. KEDA-based autoscaling in Azure Container Apps allows your workloads to scale to zero when idle (saving costs) and rapidly scale out when demand increases.

In this exercise, you deploy a simple mock "agent API" and configure autoscaling based on **HTTP concurrent requests**. You then generate concurrent load and observe how the app scales out and creates new revisions when configuration changes are applied.

Tasks performed in this exercise:

- Create Azure Container Registry and Container Apps resources
- Deploy a mock agent API container app
- Configure an HTTP concurrency scale rule using KEDA
- Generate concurrent requests to trigger scale-out
- Monitor replica count changes in real-time
- Configure scale rules using YAML

This exercise takes approximately **25-35** minutes to complete.

>**Important:** Azure Container Registry task runs are temporarily paused from Azure free credits. This exercise requires a Pay-As-You-Go, or another paid plan.

## Before you start

To complete the exercise, you need:

- An Azure subscription with the permissions to deploy the necessary Azure services. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli?view=azure-cli-latest).
- [Python 3.12](https://www.python.org/downloads/) or greater.

## Download project starter files and deploy Azure services

In this section you download the project starter files and use a script to deploy the necessary services to your Azure subscription. The Azure Container Registry and Container Apps environment deployment takes a few minutes to complete.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/aca-scale-python.zip
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

1. Run the following command to ensure you have the **containerapp** extension for Azure CLI.

    ```azurecli
    az extension add --name containerapp
    ```

1. Run the following commands to ensure your subscription has the necessary resource providers for the exercise.

    ```azurecli
    az provider register --namespace Microsoft.App
    az provider register --namespace Microsoft.OperationalInsights
    ```

### Create resources in Azure

In this section you run the deployment script to deploy the necessary services to your Azure subscription.

1. Make sure you are in the root directory of the project and run the appropriate command in the terminal to launch the deployment script. The script deploys ACR, a Container Apps environment, and a Container App with ingress enabled. It also creates a file with environment variables you use throughout the exercise.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

1. When the script is running, enter **1** to launch **Create Azure Container Registry and build container image**.

1. When the previous operation is finished, enter **2** to launch **Create Container Apps environment**.

1. When the previous operation is finished, enter **3** to launch **Create Container App (ingress enabled)**. This option also writes the `.env` file used by the rest of the exercise.

1. When the deployment completes, enter **5** to exit the deployment script.

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

## Configure autoscaling

In this section you configure an HTTP scale rule that triggers scaling based on **concurrent requests**. This is a useful proxy for "agent requests in progress" without adding any other Azure services.

>**Note:** Applying configuration updates (including scaling changes) creates a **new revision**.

1. (Optional) Verify the app endpoint is available.

    **PowerShell**
    ```powershell
    Invoke-RestMethod "$env:CONTAINER_APP_URL/"
    ```

    **Bash**
    ```bash
    curl -sS "$CONTAINER_APP_URL/" | head
    ```

## Configure multiple scale rules using YAML

In this section you configure autoscaling by editing the Container App YAML. This is a repeatable way to manage scale rules, and it becomes essential when you have multiple rules.

1. Run the following command to export the app configuration to a YAML file.

    **Bash**
    ```bash
    az containerapp show \
        --name $CONTAINER_APP_NAME \
        --resource-group $RESOURCE_GROUP \
        --output yaml > app-config.yaml
    ```

    **PowerShell**
    ```powershell
    az containerapp show `
        --name $env:CONTAINER_APP_NAME `
        --resource-group $env:RESOURCE_GROUP `
        --output yaml > app-config.yaml
    ```

1. Open the *app-config.yaml* file in VS Code. Find the **scale** section under **properties > template**. Update it to set **minReplicas** to **0** and **maxReplicas** to **10**, then add an HTTP scale rule that triggers when concurrent requests exceed a threshold. The **scale** section should look similar to the following example.

    ```yaml
    scale:
      maxReplicas: 10
      minReplicas: 0
      rules:
      - name: http-scaling
        http:
          metadata:
            concurrentRequests: "10"
    ```

1. Save the file and run the following command to apply the updated configuration.

    **Bash**
    ```bash
    az containerapp update \
        --name $CONTAINER_APP_NAME \
        --resource-group $RESOURCE_GROUP \
        --yaml app-config.yaml
    ```

    **PowerShell**
    ```powershell
    az containerapp update `
        --name $env:CONTAINER_APP_NAME `
        --resource-group $env:RESOURCE_GROUP `
        --yaml app-config.yaml
    ```

1. Run the following command to verify the scale rule is configured.

    **Bash**
    ```bash
    az containerapp show \
        --name $CONTAINER_APP_NAME \
        --resource-group $RESOURCE_GROUP \
        --query "properties.template.scale.rules[].name"
    ```

    **PowerShell**
    ```powershell
    az containerapp show `
        --name $env:CONTAINER_APP_NAME `
        --resource-group $env:RESOURCE_GROUP `
        --query "properties.template.scale.rules[].name"
    ```

## Generate load and observe scaling

In this section you run a local Flask dashboard that can both generate concurrent requests and show Container App revisions/replicas.

1. Install the dashboard dependencies.

    ```
    python -m pip install -r finished/azure-container-apps/scale-container-aca/python/client/requirements.txt
    ```

1. Run the dashboard.

    ```
    python finished/azure-container-apps/scale-container-aca/python/client/app.py
    ```

1. Open the dashboard at `http://127.0.0.1:5000`.

1. Click **Refresh Revisions & Replicas**.

1. In the **Load Generator** section, click **Start** (for example: concurrency 50, duration 60, delayMs 500). You should see replicas scale out.

1. (Optional) View system logs for scaling events.

    **Bash**
    ```bash
    az containerapp logs show \
        --name $CONTAINER_APP_NAME \
        --resource-group $RESOURCE_GROUP \
        --type system \
        --tail 50
    ```

    **PowerShell**
    ```powershell
    az containerapp logs show `
        --name $env:CONTAINER_APP_NAME `
        --resource-group $env:RESOURCE_GROUP `
        --type system `
        --tail 50
    ```

# Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues during this exercise, try these steps:

**App not scaling out under load**
- Verify the HTTP scale rule is configured using **az containerapp show --query "properties.template.scale"**
- Ensure you're generating concurrent requests (use the dashboard with a non-zero delay)
- Increase `delayMs` (for example 500-1500ms) so requests overlap and concurrency accumulates

**Dashboard can't list revisions/replicas**
- Ensure Azure CLI is installed and you ran `az login`
- Ensure the `containerapp` extension is installed: `az extension add --name containerapp`
- Ensure `.env` is loaded and contains `RESOURCE_GROUP` and `CONTAINER_APP_NAME`

**YAML update fails**
- Ensure the YAML file syntax is valid
- Remove read-only properties like **id**, **systemData**, and **type** from the YAML before applying
- Verify the scale rules section follows the correct structure
