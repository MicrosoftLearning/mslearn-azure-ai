---
lab:
    topic: Azure Kubernetes Service
    title: 'Troubleshoot apps on Azure Kubernetes Service'
    description: 'Learn how to troubleshoot Azure Kubernetes Service deployments... '
---

# Troubleshoot apps on Azure Kubernetes Service

In this exercise, you learn how to troubleshoot Azure Kubernetes Service (AKS) deployments...

Tasks performed in this exercise:

- Download the project starter files
- Deploy resources to Azure (ACR, AKS cluster)
- ...
- Clean up Azure resources

This exercise takes approximately **30-40** minutes to complete.

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
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/aks-troubleshoot-python.zip
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

1. Run the following command to ensure your subscription has the necessary resource provider to install AKS.

    ```
    az provider register --namespace Microsoft.ContainerService
    ```

1. Make sure you are in the root directory of the project and run the appropriate command in the terminal to launch the deployment script.

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

1. After the model is deployed, enter **1** to launch **Create Azure Container Registry (ACR)**. This creates the resource where the API container will be stored, and later pulled into the AKS resource.

1. After the ACR resource has been created, enter **2** to launch **Build and push API image to ACR**. This option uses ACR tasks to build the image and add it to the ACR repository. This operation can take 3-5 minutes to complete.

1. After the image has been built and pushed to ACR, enter **3** to launch the **Create AKS cluster** option. This creates the AKS resource configured with a managed identity, gives the service permission to pull images from the ACR resource, and assigns the needed RBAC role to write to the persistent storage. This operation can take 5-10 minutes to complete.

1. After the AKS cluster deployment has completed, enter **4** to launch the **Get AKS credentials for kubectl** option. This uses the **az aks get-credentials** command to retrieve credentials and configure **kubectl**.

1. After the credentials have been set, enter **5** to launch the **Deploy applications to AKS** option. This deploys an API to the AKS cluster.

1. After the app has been deployed, enter **6** to launch the **Check deployment stats** option. This option reports if each of the resources have been successfully deployed.

    If all of the services return a **successful** message, enter **6** to exit the deployment script.

>**Note:** Leave the terminal open, all of the steps in the exercise are performed in the terminal.

## Troubleshoot the deployment

The deployment script created all Kubernetes resources in a **namespace** called **aks-troubleshoot**. Namespaces are a way to organize and isolate resources within a Kubernetes cluster. They allow you to group related resources together, apply resource quotas, and manage access control. When you don't specify a namespace, resources are created in the **default** namespace. For this exercise, all **kubectl** commands include **-n aks-troubleshoot** to target the correct namespace.

### Verify the deployment

In this section you...

1. Run the following command to verify the pod is running in the namespace. The command should return one pod with **Running** status and **1/1** in the READY column.

    ```
    kubectl get pods -n aks-troubleshoot
    ```

1. Run the following command to verify the Service has endpoints. The command should return one endpoint slice listed with an IP address.

    ```
    kubectl get endpointslices -l kubernetes.io/service-name=api-service -n aks-troubleshoot
    ```

1. Run the following command to test connectivity using port-forward. This command creates a tunnel from your local machine to the Service running in the cluster, allowing you to access it at **http://localhost:8080**.

    ```
    kubectl port-forward service/api-service 8080:80 -n aks-troubleshoot
    ```

1. In the menu bar select **Terminal > New Terminal** to open a second terminal window in VS Code. Run the following command to test the connection. You should receive a JSON response with **"status": "healthy"**.

    ```bash
    # Bash
    curl http://localhost:8080/healthz
    ```

    ```powershell
    # PowerShell
    Invoke-RestMethod http://localhost:8080/healthz
    ```
1. Switch back to the terminal where **port-forward** is running and enter **ctrl+c** to exit the command.

### Diagnose a label mismatch

A Service routes traffic to pods based on label selectors. When labels don't match, the Service has no endpoints and requests fail. The API was deployed with pods labeled **app: api** and a Service selector matching **app: api**. In this section you apply a Service configuration that changes the selector to **app: api-v2**, breaking the connection.

1. Run the following command to apply the Service configuration that creates a label mismatch error.

    ```
    kubectl apply -f k8s/label-mismatch-service.yaml -n aks-troubleshoot
    ```

1. Run the following command to verify the pod is still running. The pod shows **Running** status with **1/1** ready and labels showing **app=api**.

    ```
    kubectl get pods --show-labels -n aks-troubleshoot
    ```

1. Run the following command to check the Service endpoint slices. The command should return an endpoint slice with **\<unset>** in the ENDPOINTS column, indicating no pods match the Service selector.

    ```
    kubectl get endpointslices -l kubernetes.io/service-name=api-service -n aks-troubleshoot
    ```

1. Run the following command to view the Service details. Look for the **Selector** field in the output, which now shows **app=api-v2**.

    ```
    kubectl describe service api-service -n aks-troubleshoot
    ```

    This confirms the label mismatch. The Service selector is **app=api-v2** but the pod label is **app=api**.

1. Run the following command to open the Service configuration in an editor.

    ```
    kubectl edit service api-service -n aks-troubleshoot
    ```

1. In the editor, find the **selector** section and change **app: api-v2** to `app: api`. Save the changes and exit the editor by selecting **Esc**, typing **:wq**, and then selecting **Enter**.

    >**Note:** The editor uses vi commands. Quick reference:</br>
    >- Use arrow keys (**↑ ↓ ← →**) to navigate through the file
    >- Enter **i** for insert mode to type text
    >- Enter **Esc** to exit insert mode
    >- Enter **x** or **del** to delete character under cursor
    >- Enter **:wq** + **Enter** to save and exit
    >- Enter **:q!** + **Enter** to exit without saving

1. Run the following command to verify the endpoint slice addresses are restored. The command should return an endpoint slice with an IP address listed.

    ```
    kubectl get endpointslices -l kubernetes.io/service-name=api-service -n aks-troubleshoot
    ```

Next you...


## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues while completing this exercise, try the following troubleshooting steps:

**Check deployment status with the deployment script**
- Run the deployment script and select option **5. Check deployment status** to verify the state of all deployed resources.
- This command checks:
  - ACR provisioning state and readiness
  - AKS cluster provisioning state
  - Kubernetes resources (ConfigMap, Secrets, PVC, Deployment availability, Service LoadBalancer IP)
- Use this output to identify which component may be causing issues.

**Verify YAML file completeness**
- Ensure all YAML content was added correctly to *configmap.yaml*, *secrets.yaml*, and *pvc.yaml* and that indentation is correct.
- Confirm the ACR endpoint was properly updated in *deployment.yaml* (replace **\<YOUR_ACR_ENDPOINT>** with your actual ACR endpoint).
- If you make changes to any YAML file after initial deployment, reapply the file with **kubectl apply -f k8s/\<filename>.yaml**.
- After updating ConfigMap or Secret files, perform a rolling restart to reload the configuration: **kubectl rollout restart deployment aks-config-api**.

**Verify client configuration**
- Ensure you've created a *.env* file in the *client* folder with **API_ENDPOINT** set to the LoadBalancer's external IP (for example, **http://20.xxx.xxx.xxx**).
- Verify you can reach the API endpoint by running **curl http://\<external-ip>/healthz** from the terminal.

**Check Python environment and dependencies**
- Confirm the virtual environment is activated before running the client app.
- Verify that all packages from *requirements.txt* were installed successfully by running **pip list**.
- Ensure you're running the client from the *client* directory.
