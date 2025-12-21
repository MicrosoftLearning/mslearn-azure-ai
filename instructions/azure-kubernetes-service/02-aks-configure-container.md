---
lab:
    topic: Azure Kubernetes Service
    title: 'Configure apps on Azure Kubernetes Service'
    description: 'Learn how to configure Kubernetes deployments with persistent storage, and store sensitive and non-sensitive settings. '
---

# Configure apps on Azure Kubernetes Service

In this exercise, you learn how to configure Kubernetes deployments with ConfigMaps for non-sensitive settings, Secrets for sensitive credentials, and PersistentVolumeClaims for persistent storage. You deploy a containerized API to Azure Kubernetes Service (AKS), configure it with various Kubernetes resources, and interact with it using a Python client application.

Tasks performed in this exercise:

- Download the project starter files
- Deploy resources to Azure (ACR, AKS cluster)
- Build and push a container image to Azure Container Registry
- Configure kubectl credentials for AKS cluster access
- Apply updated YAML files to AKS to create the pod and expose the API with a LoadBalancer
- Run the client app to test the API endpoints
- View API logs stored on persistent volume
- Clean up Azure resources

This exercise takes approximately **30-40** minutes to complete.

>**IMPORTANT:** The persistent storage implementation in this exercise is for demonstration purposes only. For logging, production applications should use a centralized logging solution like Azure Monitor or Application Insights instead of storing logs on persistent volumes. If persistent storage is required, implement log rotation policies to prevent storage from filling up, which can cause container failures and pod evictions.

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
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/aks-configure-python.zip
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

    When the operation is complete it will return the ACR endpoint. Copy the information, you need it later in the exercise.

1. After the ACR resource has been created, enter **2** to launch **Build and push API image to ACR**. This option uses ACR tasks to build the image and add it to the ACR repository. This operation can take 3-5 minutes to complete.

1. After the image has been built and pushed to ACR, enter **3** to launch the **Create AKS cluster** option. This creates the AKS resource configured with a managed identity, gives the service permission to pull images from the ACR resource, and assigns the needed RBAC role to write to the persistent storage. This operation can take 5-10 minutes to complete.

1. After the AKS cluster deployment has completed, enter **4** to launch the **Get AKS credentials for kubectl** option. This uses the **az aks get-credentials** command to retrieve credentials and configure **kubectl**.

1. After the credentials have been configured, enter **5** to launch the **Check deployment stats** option. This option reports if each of the resources have been successfully deployed.

    If all of the services return a **successful** message, enter **6** to exit the deployment script.

Next, you complete the YAML files necessary to deploy the API to AKS.

## Complete the YAML deployment files and deploy to AKS

In this section you complete YAML files, located in the *k8s* folder, needed to configure Kubernetes deployments with persistent storage, and store sensitive and non-sensitive settings.

### Complete the ConfigMap YAML file

ConfigMaps store non-sensitive configuration data as key-value pairs that can be consumed by pods. In this section, you create a ConfigMap to store application settings like the student name, API version, and log path.

1. Open the *k8s/configmap.yaml* file and add the following code to the file. You can update the value for **STUDENT_NAME** with your name if you want to.

    ```yml
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: api-config
      labels:
        app: aks-config-api # Label for the AKS configuration API
    data:
      # Store non-sensitive configuration values
      STUDENT_NAME: "YourNameHere"
      API_VERSION: "1.0.0"
      LOG_PATH: "/var/log/api" # Path for API logs
    ```

1. Review the comments in the code, then save your changes.

### Complete the Secrets YAML file

Secrets store sensitive information like passwords, tokens, and keys in a base64-encoded format. In this section, you create a Secret to store sensitive credentials that the API will access at runtime.

1. Open the *k8s/secrets.yaml* file and add the following code to the file.

    ```yml
    apiVersion: v1
    kind: Secret
    metadata:
      name: api-secrets
      labels:
        app: aks-config-api
    type: Opaque
    stringData:
      # Store sensitive credentials as base64-encoded values
      secret-endpoint: "SecretEndpointValue"
      secret-access-key: "SecretAccessKey123456"
    ```

1. Take a few minutes to review the comments in the code, then save your changes.

### Complete the PVC YAML file

A PersistentVolumeClaim (PVC) requests storage resources from Azure that can be mounted to pods. In this section, you create a PVC that uses Azure Disk storage to persist API log files across pod restarts.

1. Open the *k8s/pvc.yaml* file and add the following code to the file.

    ```yml
    apiVersion: v1
    kind: PersistentVolumeClaim
    metadata:
      name: api-logs-pvc
      labels:
        app: aks-config-api # Label for the AKS configuration API
    spec:
      accessModes:
        - ReadWriteOnce  # Allow single pod to mount volume for read/write
      resources:
        requests:
          storage: 1Gi  # Request minimum Azure Disk size
      storageClassName: managed-csi  # Use Azure Disk CSI driver (default)
      volumeMode: Filesystem  # Default mode
    ```

1. Take a few minutes to review the comments in the code, then save your changes.

### Update the Deployment YAML file

The deployment manifest is already partially configured with environment variables, volume mounts, and probes. You just need to update the container image reference with your specific ACR endpoint.

1. Open the *k8s/deployment.yaml* file and locate the **image: \<YOUR_ACR_ENDPOINT>/aks-config-api:latest** line.

1. Replace **\<YOUR_ACR_ENDPOINT>** with the value you recorded earlier in the exercise.

1. Take a few minutes to review the comments in the code, then save your changes.


## Apply the manifests to AKS

In this section you apply the manifests to AKS. The following steps are performed in the VS Code terminal. Ensure you are in the root of the project before running the commands.

1. Run the following command to apply the ConfigMap.

    ```
    kubectl apply -f k8s/configmap.yaml
    ```

1. Run the following command to apply the Secrets.

    ```
    kubectl apply -f k8s/secrets.yaml
    ```

1. Run the following command to apply the PersistentVolumeClaim.

    ```
    kubectl apply -f k8s/pvc.yaml
    ```

1. Run the following command to apply the Deployment.

    ```
    kubectl apply -f k8s/deployment.yaml
    ```

1. Run the following command to create the Service.

    ```
    kubectl apply -f k8s/service.yaml
    ```

1. After you create the Service it can take a few minutes for the deployment to complete. The following command will monitor the service and update the external IP address of the pod when it's available. Note the external IP address, you need it later in the exercise. Enter **ctrl + c** to exit the command after the IP address appears.

    ```
    kubectl get svc aks-config-api-service -w
    ```

## Run the client app

In this section, you configure the Python environment and then perform operations on the API using the client app

### Configure the Python environment

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

1. Create a *.env* file in the client directory and add the following code. Replace **\<API_IP_address>** with the value you copied earlier in the exercise.

    ```
    # API endpoint - update this with the external IP from the LoadBalancer service
    # Get the IP with: kubectl get services
    API_ENDPOINT=http://<API_IP_address>
    ```
### Perform operations with the app

With the Python environment configured and dependencies installed, you can now run the client application to test the deployed API. The API logs all operations to the persistent volume, and the client provides a menu-driven interface to interact with various endpoints.

1. Run the following command in the terminal to start the console app. Refer to the commands from earlier in the exercise to activate the environment, if needed, before running the command.

    ```
    python main.py
    ```

1. Enter **1** to start the **Check API Health (Liveness)** option. This verifies that the API container is running and responds to health checks, which is the same endpoint used by the Kubernetes liveness probe. Note the information it returns contains the non-sensitive student name set in ConfigMap.

    ```
    [*] Checking API health...
    ✓ API is healthy
      Service: aks-config-api
      Version: 1.0.0
      Student: YourNameHere
    ```
1. Enter **2** to start the **Check API Readiness (Foundry Connectivity)** option. This confirms the API can successfully connect to the Foundry model endpoint and is ready to process inference requests.

1. Enter **3** to start the **View Secrets Information** option. This functionality exists only so you can confirm your secrets were set in the pod and is for demonstration purposes only. In the output you can view information about the secrets, the output is masked.

    ```
    Secret Details:

      secret_endpoint:
        Loaded: True
        Value: SecretEndp...
        Length: 19 characters

      secret_access_key:
        Loaded: True
        Value: ***3456
        Length: 21 characters
    ```

1. Enter **5** to start the **List All Products** option. This displays the mock data included in the API.

1. Now that the API has logged operations for several different endpoints, it's time to view the logs. Enter **6** to start the **View Log Summary** option and see a summary of the different operations. Note the total number of requests, and the requests to the **/readyz** and **/healthz** endpoints. Those two operations are executing automatically based on the schedule set in the *deployment.yaml* file.

    ```
    ✓ Log summary retrieved

    Log file: /var/log/api/api-requests-2025-12-21.log
    Total requests: 220
    Student: YourNameHere

    First request: 2025-12-21T02:19:48.953308
    Last request: 2025-12-21T02:46:08.952772

    Requests by endpoint:
      /readyz: 160
      /healthz: 56
      /secrets: 1
      /products: 1
    ```

1. You can continue to generate log information and when you're finished enter **7** to exit the app.

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
