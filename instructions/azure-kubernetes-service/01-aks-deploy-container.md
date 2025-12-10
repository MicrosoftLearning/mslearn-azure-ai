---
lab:
    topic: Azure Kubernetes Service
    title: 'Deploy a containerized API to Azure Kubernetes Service'
    description: 'Learn how to create deployment and service manifests to deploy containers to Azure Kubernetes Service.'
---

# Deploy a containerized API to Azure Kubernetes Service

In this exercise, you create a

Tasks performed in this exercise:

- Download the project starter files
- Deploy resources to Azure
- Complete the *deployment.yaml* and *service.yaml* files and deploy the container to AKS
- Run the client app to test the API

This exercise takes approximately **30** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription with the permissions to deploy the necessary Azure services. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- The latest version of the [Azure CLI](/cli/azure/install-azure-cli?view=azure-cli-latest).
- The Kubernetes command-line tool, [kubectl](https://kubernetes.io/docs/tasks/tools/).

## Download project starter files and deploy Azure services

In this section you download the starter files for the console app and use a script to deploy the necessary services to your Azure subscription. The Azure Managed Redis deployment takes 5-10 minutes to complete.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/amr-data-operations-python.zip
    ```

1. Copy, or move, the file to a location in your system where you want to work on the project. Then unzip the file into a folder.

1. Launch Visual Studio Code (VS Code) and select **File > Open Folder...** in the menu, then choose the folder containing the project files.

1. The project contains deployment scripts for both Bash (*azdeploy.sh*) and PowerShell (*azdeploy.ps1*). Open the appropriate file for your environment and change the two values at the top of the script to meet your needs, then save your changes. **Note:** Do not change anything else in the script.

    ```
    "<your-resource-group-name>" # Resource Group name
    "<your-azure-region>" # Azure region for the resources
    ```

    > **Note:** It is recommended to use one of the following three Azure regions for deployment: **eastus2**, **swedencentral**, or **australiaeast**. These regions support the deployment of the AI inference model used in the exercise.

1. In the menu bar select **Terminal > New Terminal** to open a terminal window in VS Code.

1. Run the following command to login to your Azure account. Answer the prompts to select your Azure account and subscription for the exercise.

    ```
    az login
    ```

1. Run the follwoing command to ensure your subscription has the necessary resource provider to install AKS.

    ```
    az provider register --namespace Microsoft.ContainerService
    ```

1. Make sure you are in the root directory of the project and run the appropriate command in the terminal to launch the script.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

### Deploy resources to Azure

With the deployment script running, follow these steps to create the needed resources in Azure.

1. Enter **1** to launch the **1. Provision gpt-4o-mini model in Microsoft Foundry** option. This option creates the resource group if it doesn't already exist, creates the resource in MIcrosoft Foundry, and deploys the **gpt-4o-mini** model to the resource.

    > **Important:** If there are errors during the model deployment, enter **2** to launch the **2. Delete/Purge Foundry deployment** option. This will delete the deployment and purge the resource name. Exit the menu, and change the region in the deployment script to one of the other recommended regions. Then restart the deployment script and run the model provisioning option again.

1. After the model is deployed, enter **3** to launch **3. Create Azure Container Registry (ACR)**. This creates the resource where the API container will be stored, and later pulled into the AKS resource.

1. After the ACR resource has been created, enter **4** to launch **Build and push API image to ACR**. This option uses ACR tasks to build the image and add it to the ACR repository. This operation can take 3-5 minutes to complete.

1. After the image has been built and pushed to ACR, enter **5** to launch the **5. Create AKS resource** option. This creates the AKS resource configured with a managed identity and gives the service permission to pull images from the ACR resource. This operation can take 5-10 minutes to complete.

1. After the AKS resources has been deployed, enter **6** to launch the **6. Check deployment stats** option. This option reports if each of the three resources have been successfully deployed.

    If all of the services return a **successful** message, enter **8** to exit the deployment script.

Next, you complete the YAML files necessary to deploy the API to AKS.

## Complete the YAML deployment files




## Configure the Python environment

In this section, you create the Python environment and install the dependencies.

1. Ensure you are in the *client* folder of the project in the terminal.

1. Run the following command in the VS Code terminal to create the Python environment.

    ```
    python -m venv .venv
    ```

1. Run the following command in the VS Code terminal to activate the Python environment.

    **Bash**
    ```bash
    source .venv/Scripts/activate
    ```

    **PowerShell**
    ```powershell
    .venv\Scripts\Activate.ps1
    ```

    >**Note:** You may need to modify the commands for your environment. The *Scripts* folder may be *bin* depending on your operating system.

1. Run the following command in the VS Code terminal to install the dependencies.

    ```
    pip install -r requirements.txt
    ```

## Run the client app

In this section, you run the client application to perform various operations on the API. The app provides a menu-driven interface.

1. Run the following command in the terminal to start the console app. Refer to the commands from earlier in the exercise to activate the environment, if needed, before running the command.

    ```
    python main.py
    ```

1. The app has the following options. Select the **1. Store hash data** to get started.

    ```
    1. Store hash data
    2. Retrieve hash data
    3. Set expiration
    4. Retrieve expiration (TTL)
    5. Delete key
    6. Exit
    ```

1. Select the remaining options in order to run the different operations.

>**Note:** You can run the options in any order you choose. For example, after storing the hash data you can retrieve the expiration information to learn there is no expiration set on the key.

The mock hash data used in the app is defined in the beginning of the **main()** function. You can update the code to use a different key, or add more values to the hash data.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues while completing this exercise, try the following troubleshooting steps:

**Verify Azure Managed Redis resource deployment**
- Navigate to the [Azure portal](https://portal.azure.com) and locate your resource group.
- Confirm that the Azure Managed Redis resource shows a **Provisioning State** of **Succeeded**.
- Check that the resource has **Public network access** enabled and **Access keys authentication** set to **Enabled**.

**Check code completeness and indentation**
- Ensure all code blocks were added to the correct sections in *main.py* between the appropriate BEGIN/END comment markers.
- Verify that Python indentation is consistent (use spaces, not tabs) and that all code aligns properly within functions.
- Confirm that no code was accidentally removed or modified outside the designated sections.

**Verify environment variables**
- Check that the *.env* file exists in the project folder and contains valid **REDIS_HOST** and **REDIS_KEY** values.
- Ensure the *.env* file is in the same directory as *main.py*.

**Check Python environment and dependencies**
- Confirm the virtual environment is activated before running the app.
- Verify that all packages from *requirements.txt* were installed successfully by running **pip list**.

