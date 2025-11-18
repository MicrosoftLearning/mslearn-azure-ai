---
lab:
    topic: Azure Managed Redis
    title: 'Perform data operations in Azure Managed Redis'
    description: 'Learn how to perform data operations in Azure Managed Redis using the redis-py Python library.'
---

# Perform data operations in Azure Managed Redis

In this exercise, you...

Tasks performed in this exercise:

* Download the project starter files
* Create an Azure Managed Redis resource
* Add code to the starter files to complete the console app
* Run the console app to perform data operations

This exercise takes approximately **30** minutes to complete.

## Download the project starter files

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/amr-data-operations-python.zip
    ```

1. Copy, or move, the file to a location in your system where you want to work on the project. Then unzip the file into a folder.

1. Launch Visual Studio Code and select **File > Open Folder...** in the menu, then choose the folder containing the project files.

## Create an Azure Managed Redis resource

1. In your browser navigate to the Azure portal [https://portal.azure.com](https://portal.azure.com); signing in with your Azure credentials if prompted.

1. Use the **[\>_]** button to the right of the search bar at the top of the page to create a new cloud shell in the Azure portal, selecting a ***Bash*** environment. The cloud shell provides a command line interface in a pane at the bottom of the Azure portal. If you are prompted to select a storage account to persist your files, select **No storage account required**, your subscription, and then select **Apply**.

    > **Note**: If you have previously created a cloud shell that uses a *PowerShell* environment, switch it to ***Bash***.

1. Create a resource group for the resources needed for this exercise. Replace **myResourceGroup** with a name you want to use for the resource group. You can replace **eastus** with a region near you if needed. If you already have a resource group you want to use, proceed to the next step.

    ```
    az group create --location eastus --name myResourceGroup
    ```

1. Run the following command to create a basic container registry. The registry name must be unique within Azure, and contain 5-50 alphanumeric characters. Replace **myResourceGroup** with the name you used earlier, and **myContainerRegistry** with a unique value.

    ```bash
    az acr create --resource-group myResourceGroup \
        --name myContainerRegistry --sku Basic
    ```

    > **Note:** The command creates a *Basic* registry, a cost-optimized option for developers learning about Azure Container Registry.



## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. In your browser navigate to the Azure portal [https://portal.azure.com](https://portal.azure.com); signing in with your Azure credentials if prompted.
1. Navigate to the resource group you created and view the contents of the resources used in this exercise.
1. On the toolbar, select **Delete resource group**.
1. Enter the resource group name and confirm that you want to delete it.

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.
