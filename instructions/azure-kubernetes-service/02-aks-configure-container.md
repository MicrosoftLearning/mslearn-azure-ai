---
lab:
    topic: Azure Kubernetes Service
    title: 'Configure Azure Kubernetes Service'
    description: 'Learn how to configure Kubernetes deployments with persistent storage, and store sensitive and non-sensitive settings. '
---

# Configure Azure Kubernetes Service

In this exercise, you deploy Azure resources including a Microsoft Foundry AI model, Azure Container Registry (ACR), and Azure Kubernetes Service (AKS) cluster. You then complete Kubernetes manifest files to define container specifications, health probes, resource limits, and load balancing. After deploying the containerized API to AKS, you use a Python client application to test the deployed API endpoints including health checks, readiness validation, and AI model inference requests.

Tasks performed in this exercise:

- Download the project starter files
- Deploy resources to Azure
- Complete the *deployment.yaml* and *service.yaml* files and deploy the container to AKS
- Run the client app to test the API

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
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/aks-deploy-python.zip
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

1. Enter **1** to launch the **1. Provision gpt-4o-mini model in Microsoft Foundry** option. This option creates the resource group if it doesn't already exist, creates the resource in MIcrosoft Foundry, and deploys the **gpt-4o-mini** model to the resource.

    > **Important:** If there are errors during the model deployment, enter **2** to launch the **2. Delete/Purge Foundry deployment** option. This will delete the deployment and purge the resource name. Exit the menu, and change the region in the deployment script to one of the other recommended regions. Then restart the deployment script and run the model provisioning option again.

1. After the model is deployed, enter **3** to launch **3. Create Azure Container Registry (ACR)**. This creates the resource where the API container will be stored, and later pulled into the AKS resource.

1. After the ACR resource has been created, enter **4** to launch **Build and push API image to ACR**. This option uses ACR tasks to build the image and add it to the ACR repository. This operation can take 3-5 minutes to complete.

1. After the image has been built and pushed to ACR, enter **5** to launch the **5. Create AKS resource** option. This creates the AKS resource configured with a managed identity and gives the service permission to pull images from the ACR resource. This operation can take 5-10 minutes to complete.

1. After the AKS resources has been deployed, enter **6** to launch the **6. Check deployment stats** option. This option reports if each of the three resources have been successfully deployed.

    If all of the services return a **successful** message, enter **8** to exit the deployment script.

Next, you complete the YAML files necessary to deploy the API to AKS.

## Complete the YAML deployment files and deploy to AKS

In this section you complete both the *deployment.yaml* and *service.yaml* files. The deployment manifest defines how the API container is deployed and managed in AKS, while the service manifest exposes the API to external traffic through a load balancer.

1. Open the *k8s/deployment.yaml* file to begin completing the file.

1. Locate the **# BEGIN: Container specification** comment and add the following YAML section to the manifest under the comment. Ensure YAML indentation is correct.

    ```yml
    containers:  # List of containers to run in the pod
    - name: api
      image: ACR_ENDPOINT/aks-api:latest  # Container image from ACR
      imagePullPolicy: Always  # Always pull the latest image from registry
      ports:  # Ports exposed by the container
      - name: http
        containerPort: 8000
        protocol: TCP
    ```

    This section defines the container specification, including which container image to use from ACR, the pull policy, and which port the container exposes for HTTP traffic.

1. Locate the **# BEGIN: Liveness Probe Configuration** comment and add the following YAML section to the manifest under the comment. Ensure YAML indentation is correct.

    ```yml
    livenessProbe:  # Detects if container is alive or needs restart
      httpGet:
        path: /healthz  # Health check endpoint path
        port: http
      initialDelaySeconds: 10  # Seconds to wait before first check
      periodSeconds: 30
      timeoutSeconds: 5
      failureThreshold: 3  # Consecutive failures before restarting container
    ```

    This section configures the liveness probe, which periodically checks if the container is healthy by making HTTP requests to the **/healthz** endpoint. If the probe fails three consecutive times, Kubernetes automatically restarts the container.

1. Locate the **# BEGIN: Resource Limits Configuration** comment and add the following YAML section to the manifest under the comment. Ensure YAML indentation is correct.

    ```yml
    resources:  # CPU and memory resource specifications
      requests:  # Minimum resources guaranteed to the container
        memory: "256Mi"
        cpu: "250m"
      limits:  # Maximum resources the container can use
        memory: "512Mi"
        cpu: "500m"
    ```

    This section defines the CPU and memory resources for the container. Requests specify the minimum resources guaranteed, while limits set the maximum resources the container can consume. This helps Kubernetes schedule pods efficiently and prevents resource starvation.

1. Save your changes and take a few minutes to review the completed *deployment.yaml* file.

Next, you update the *service.yaml* file.

1. Open the *k8s/service.yaml* to complete the file.

1. Add the following YAML to the manifest. Ensure YAML indentation is correct.

    ```yml
    apiVersion: v1
    kind: Service  # Service: exposes pods on a network and provides load balancing
    metadata:
      name: aks-api-service  # Unique name for the service
      labels:
        app: aks-api # Matches deployment and pod labels
      annotations:
        service.beta.kubernetes.io/azure-load-balancer-internal: "false"  # Use public load balancer
    spec:  # Service specification
      type: LoadBalancer  # Exposes service externally
      selector:  # Selects which pods to route traffic to based on labels
        app: aks-api
        version: v1
      ports:  # Port mappings between service and pods
      - name: http
        port: 80  # Service port exposed externally
        targetPort: http  # Pod container port to forward traffic to
        protocol: TCP
      sessionAffinity: None  # Client requests not pinned to specific pods
    ```

    This manifest creates a LoadBalancer Service that exposes your API pods externally through an Azure Load Balancer. It routes incoming traffic on port 80 to the container's port 8000, using label selectors to identify which pods should receive traffic.

1. Save your changes and take a few minutes to review the file.

### Apply the manifests to AKS

In this section you use the deployment script to apply the manifests to AKS.

1. Make sure you are in the root directory of the project and run the appropriate command in the terminal to launch the deployment script.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

1. Enter **7** to launch the **7. Deploy to AKS** option. This option performs several operations: it retrieves your AKS credentials and configures kubectl, creates a Kubernetes secret with your Foundry credentials, updates the deployment manifest with your ACR endpoint, and then uses **kubectl apply** to deploy both manifests to your AKS cluster. When the operation is complete, enter **8** to exit the deployment script.

1. Run the following commands in the terminal to verify the deployment. Expect **kubectl get deploy,svc** to show the Deployment **READY** as **1/1** (or your replica count) and the Service **EXTERNAL-IP** to have a public IP (not **\<pending>**). The rollout command should print **deployment "aks-api" successfully rolled out** when the update is complete.

    ```
    kubectl get deploy,svc
    kubectl rollout status deploy/aks-api
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

### Perform operations with the app

Now it's time to run the client application to perform various operations on the API. The app provides a menu-driven interface.

1. Run the following command in the terminal to start the console app. Refer to the commands from earlier in the exercise to activate the environment, if needed, before running the command.

    ```
    python main.py
    ```

1. Enter **1** to start the **1. Check API Health (Liveness)** option. This verifies that the API container is running and responds to health checks, which is the same endpoint used by the Kubernetes liveness probe.

1. Enter **2** to start the **2. Check API Readiness (Foundry Connectivity)** option. This confirms the API can successfully connect to the Foundry model endpoint and is ready to process inference requests.

1. Enter **3** to start the **3. Send Inference Request** option. This sends a single prompt to the API and receives a complete response from the deployed model. Single inference requests are useful for batch processing, automated tasks, or when you need the entire response at once for further processing.

1. Enter **4** to start the **4. Start Chat Session (Streaming)** option. This starts an interactive chat session where responses from the model are streamed in real-time as they're generated.

When you're finished enter **5** to exit the app.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues while completing this exercise, try the following troubleshooting steps:

**Verify Azure resource deployment**
- Navigate to the [Azure portal](https://portal.azure.com) and locate your resource group.
- Confirm that the Microsoft Foundry resource shows a **Provisioning State** of **Succeeded** and the **gpt-4o-mini** model is deployed.
- Verify the Azure Container Registry (ACR) exists and contains the **aks-api** image.
- Check that the AKS cluster is in a **Succeeded** state and the nodes are running.

**Verify AKS deployment status**
- Run **kubectl get pods** to check if the API pods are running. Look for **Running** status.
- Run **kubectl get svc** to verify the LoadBalancer service has an external IP assigned (not **\<pending>**).
- Run **kubectl describe pod \<pod-name>** to see detailed pod status and events if issues occur.
- Check pod logs with **kubectl logs \<pod-name>** to see container startup errors or runtime issues.

**Verify YAML file completeness**
- Ensure all YAML sections were added correctly to *deployment.yaml* and *service.yaml* between the appropriate comment markers.
- Verify YAML indentation is correct (use spaces, not tabs) as incorrect indentation will cause deployment failures.
- Confirm the ACR endpoint was properly substituted in the deployment manifest by the deployment script.

**Verify client configuration**
- Check that the *.env* file exists in the *client* folder and contains a valid **API_ENDPOINT** value.
- Ensure the API endpoint uses the correct external IP from the LoadBalancer service.
- Verify you can reach the API endpoint by running **curl http://\<external-ip>/healthz** from the terminal.

**Check Python environment and dependencies**
- Confirm the virtual environment is activated before running the client app.
- Verify that all packages from *requirements.txt* were installed successfully by running **pip list**.
- Ensure you're running the client from the *client* directory.

