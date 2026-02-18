---
lab:
    topic: Instrument and observe apps
    title: 'Instrument an app with OpenTelemetry'
    description: 'Learn how to instrument a Python Flask application with OpenTelemetry, create custom spans and attributes, export telemetry to Application Insights, and diagnose performance issues using the Application Map.'
    level: 300
    duration: 25
---

# Instrument an app with OpenTelemetry

OpenTelemetry is an open-source observability framework that provides a standardized way to collect traces, metrics, and logs from applications. The Azure Monitor OpenTelemetry Distro packages the OpenTelemetry SDK with the Azure Monitor exporter so Python applications can send telemetry to Application Insights with minimal configuration. Custom spans let you trace application-specific operations and add attributes that enrich trace data with business context.

In this exercise, you deploy an Application Insights resource and build a Python Flask web application that demonstrates OpenTelemetry instrumentation for a document processing pipeline. You configure the Azure Monitor OpenTelemetry Distro, create custom parent and child spans for each pipeline stage, add span attributes to capture document metadata, and use the Application Map and end-to-end transaction view in the Azure portal to diagnose a simulated latency bottleneck.

Tasks performed in this exercise:

- Download the project starter files
- Create an Application Insights resource
- Add code to the starter files to complete the app
- Run the app and diagnose a performance issue in Application Insights

This exercise takes approximately **25** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).

## Download project starter files and deploy Application Insights

In this section you download the starter files for the app and use a script to deploy an Application Insights resource to your subscription.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/instrument-app-python.zip
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

1. Run the following command to ensure your subscription has the necessary resource provider for the exercise.

    ```
    az provider register --namespace Microsoft.Insights
    ```

1. Run the appropriate command in the terminal to launch the script.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

1. When the script is running, enter **1** to launch the **1. Create Application Insights** option.

    This option creates the resource group if it doesn't already exist, deploys a Log Analytics workspace, and creates an Application Insights resource connected to that workspace.

1. Enter **2** to run the **2. Assign role** option. This assigns the Monitoring Metrics Publisher role to your account so the app can publish telemetry to Application Insights using Microsoft Entra authentication.

1. Enter **3** to run the **3. Check deployment status** option. Verify the Application Insights resource shows **Succeeded** and the role is assigned before continuing. If the resource is still provisioning, wait a moment and try again.

1. Enter **4** to run the **4. Retrieve connection info** option. This creates the environment variable file with the Application Insights connection string needed by the app.

1. Enter **5** to exit the deployment script.

1. Run the appropriate command to load the environment variables into your terminal session from the file created in a previous step.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

    >**Note:** Keep the terminal open. If you close it and create a new terminal, you need to run this command again to reload the environment variables.

## Complete the app

In this section you add code to the *telemetry_functions.py* file to complete the OpenTelemetry instrumentation functions. The Flask app in *app.py* calls these functions and displays the results in the browser. You run the app later in the exercise.

1. Open the *client/telemetry_functions.py* file to begin adding code.

>**Note:** The code blocks you add to the application should align with the comment for that section of the code.

### Add code to configure telemetry

In this section you add code to configure the Azure Monitor OpenTelemetry Distro so the application exports traces to Application Insights. The function reads the connection string from an environment variable, creates a **DefaultAzureCredential** for Microsoft Entra authentication, and sets a resource attribute that identifies the application in the Application Map.

The function calls **configure_azure_monitor()** from the Azure Monitor OpenTelemetry Distro package. This single call configures the OpenTelemetry SDK with the Azure Monitor trace exporter and sets up automatic instrumentation for Flask requests. The **credential** parameter enables Entra-based authentication so the app publishes telemetry using the Monitoring Metrics Publisher role instead of the instrumentation key. The **cloud.role.name** resource attribute controls how the application node appears in the Application Map.

1. Locate the **# BEGIN CONFIGURE TELEMETRY FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def configure_telemetry(app):
        """Configure the Azure Monitor OpenTelemetry Distro."""
        connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")

        if not connection_string:
            raise ValueError(
                "APPLICATIONINSIGHTS_CONNECTION_STRING environment variable must be set"
            )

        from azure.monitor.opentelemetry import configure_azure_monitor

        credential = DefaultAzureCredential()

        configure_azure_monitor(
            connection_string=connection_string,
            credential=credential,
            resource_attributes={"cloud.role.name": "document-pipeline-app"}
        )
    ```

1. Take a few minutes to review the code.

### Add code to process documents

In this section you add code that creates a parent span for a batch document processing operation. The function loops through a configurable number of documents and calls three child span functions for each one: validate, enrich, and store.

The function uses **start_as_current_span()** to create a parent span named "process-documents" that wraps the entire batch. Each child function creates its own span that automatically becomes a child of the current span, building a hierarchical trace tree. The span attributes record the batch size and the number of successfully processed documents.

1. Locate the **# BEGIN PROCESS DOCUMENTS FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def process_documents(doc_count):
        """Process a batch of documents through the pipeline with tracing."""
        tracer = get_tracer()
        results = []

        with tracer.start_as_current_span("process-documents") as parent_span:
            parent_span.set_attribute("document.count", doc_count)
            parent_span.set_attribute("pipeline.name", "document-processing")

            for i in range(1, doc_count + 1):
                doc_id = f"DOC-{i:04d}"

                validate_result = validate_document(doc_id)
                enrich_result = enrich_document(doc_id)
                store_result = store_document(doc_id)

                results.append({
                    "doc_id": doc_id,
                    "validate": validate_result,
                    "enrich": enrich_result,
                    "store": store_result
                })

            parent_span.set_attribute("document.processed", len(results))

        return results
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to validate documents

In this section you add code that creates a child span for the document validation stage. The span records the document identifier and processing stage as attributes, enabling you to filter and search for specific documents in Application Insights.

The function calls **start_as_current_span()** to create a span named "validate-document" that automatically becomes a child of the active parent span. The **set_attribute()** calls add searchable metadata to the span. The **set_status()** call marks the span as successful, which is reflected in the success rate metrics in Application Insights.

1. Locate the **# BEGIN VALIDATE DOCUMENT FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def validate_document(doc_id):
        """Validate a document and record a traced span."""
        tracer = get_tracer()

        with tracer.start_as_current_span("validate-document") as span:
            span.set_attribute("document.id", doc_id)
            span.set_attribute("document.stage", "validate")

            # Simulate validation work
            time.sleep(random.uniform(0.05, 0.15))
            is_valid = True

            span.set_attribute("document.valid", is_valid)
            span.set_status(StatusCode.OK)

        return {"status": "valid", "duration_ms": round(random.uniform(50, 150))}
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to enrich documents

In this section you add code that creates a child span for the document enrichment stage. This function contains a simulated latency issue that causes certain documents to take significantly longer to process, creating a visible performance bottleneck that you diagnose later using the Application Map.

The function introduces a deliberate delay for documents **DOC-0003** and **DOC-0005**, simulating an external service call that intermittently takes 1.5 to 3 seconds. The **enrichment.slow** attribute flags affected spans so you can filter for them in Application Insights. When you examine the end-to-end transaction view later, these spans will stand out as the source of pipeline latency.

1. Locate the **# BEGIN ENRICH DOCUMENT FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def enrich_document(doc_id):
        """Enrich a document with metadata and record a traced span."""
        tracer = get_tracer()

        with tracer.start_as_current_span("enrich-document") as span:
            span.set_attribute("document.id", doc_id)
            span.set_attribute("document.stage", "enrich")

            # Simulated latency issue: documents DOC-0003 and DOC-0005
            # experience high latency during enrichment, representing
            # a bottleneck for the student to diagnose in Application Insights
            if doc_id in ("DOC-0003", "DOC-0005"):
                delay = random.uniform(1.5, 3.0)
                span.set_attribute("enrichment.slow", True)
            else:
                delay = random.uniform(0.05, 0.2)
                span.set_attribute("enrichment.slow", False)

            time.sleep(delay)
            span.set_attribute("enrichment.duration_s", round(delay, 3))
            span.set_status(StatusCode.OK)

        return {
            "status": "enriched",
            "duration_ms": round(delay * 1000),
            "slow": doc_id in ("DOC-0003", "DOC-0005")
        }
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to store documents

In this section you add code that creates a child span for the document storage stage. The span records the document identifier, processing stage, and storage type as attributes.

The function creates a span named "store-document" and adds a **storage.type** attribute to indicate the destination. Like the other pipeline stages, this span becomes a child of the "process-documents" parent span, completing the three-stage trace tree for each document.

1. Locate the **# BEGIN STORE DOCUMENT FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def store_document(doc_id):
        """Store a document and record a traced span."""
        tracer = get_tracer()

        with tracer.start_as_current_span("store-document") as span:
            span.set_attribute("document.id", doc_id)
            span.set_attribute("document.stage", "store")
            span.set_attribute("storage.type", "blob")

            # Simulate storage write
            time.sleep(random.uniform(0.05, 0.2))

            span.set_status(StatusCode.OK)

        return {"status": "stored", "duration_ms": round(random.uniform(50, 200))}
    ```

1. Save your changes and take a few minutes to review the code.

## Configure the Python environment

In this section you navigate to the client app directory, create the Python environment, and install the dependencies.

1. Run the following command in the VS Code terminal to navigate to the *client* directory.

    ```
    cd client
    ```

1. Run the following command to create the Python environment.

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

1. Run the following command in the VS Code terminal to install the dependencies.

    ```
    pip install -r requirements.txt
    ```

## Run the app

In this section you run the completed Flask application to generate telemetry and diagnose a simulated performance bottleneck using the Application Map and end-to-end transaction view in Application Insights.

1. Run the following command in the terminal to start the app. Refer to the commands from earlier in the exercise to activate the environment, if needed, before running the command. If you navigated away from the *client* directory, run **cd client** first.

    ```
    python app.py
    ```

1. Open a browser and navigate to `http://localhost:5000` to access the app.

1. Select **Check Telemetry Status** in the left panel. Verify that the telemetry status shows **active** and the resource attributes include **cloud.role.name** with the value **document-pipeline-app**. This confirms the Azure Monitor OpenTelemetry Distro is configured and exporting telemetry.

1. Select **Process Documents** in the left panel. This processes five documents through the pipeline and displays the results in a table. Notice that documents **DOC-0003** and **DOC-0005** show significantly higher enrichment durations and a **SLOW** tag, while the other documents complete quickly.

1. Select **Process Documents** two more times to generate additional telemetry data. Each run creates new traces with parent and child spans.

1. Wait two to three minutes for the telemetry to arrive in Application Insights. Telemetry is batched and sent periodically, so there is a short delay before data appears in the portal.

1. Navigate to the [Azure portal](https://portal.azure.com) and locate your Application Insights resource in the resource group you created earlier.

1. In the Application Insights resource, select **Application map** in the left navigation under **Investigate**. The map should display a node labeled **document-pipeline-app** (the **cloud.role.name** you configured). The node shows the request count and average response time, providing an at-a-glance view of application health.

1. Select the **document-pipeline-app** node to open the details panel. Select a request to view the end-to-end transaction details. The transaction view displays the full span hierarchy: the root HTTP request span, the "process-documents" parent span, and the child spans for each pipeline stage (validate, enrich, store).

1. In the transaction timeline, identify the "enrich-document" spans with durations of 1.5 seconds or more. These are the spans for documents **DOC-0003** and **DOC-0005** that exhibit the simulated latency. Expand one of these spans to view its attributes, including **document.id**, **document.stage**, and **enrichment.slow = True**.

1. Compare the enrich spans for slow documents to those for fast documents. The fast documents complete enrichment in under 200 milliseconds, while the slow documents take 1.5 to 3 seconds. This clearly identifies the enrichment stage as the bottleneck and the specific document IDs affected.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues while completing this exercise, try the following troubleshooting steps:

**Verify Application Insights deployment**
- Navigate to the [Azure portal](https://portal.azure.com) and locate your resource group.
- Confirm that the Application Insights resource shows a **Provisioning State** of **Succeeded**.
- Verify the resource is connected to a Log Analytics workspace.

**Check the connection string**
- Run the deployment script's **Check deployment status** option to verify the resource was created successfully.
- Confirm the *.env* file contains the **APPLICATIONINSIGHTS_CONNECTION_STRING** value.
- If the connection string is missing, run the **Retrieve connection info** option again.

**Check code completeness and indentation**
- Ensure all code blocks were added to the correct sections in *telemetry_functions.py* between the appropriate BEGIN/END comment markers.
- Verify that Python indentation is consistent (use spaces, not tabs) and that all code aligns properly within functions.
- Confirm that no code was accidentally removed or modified outside the designated sections.

**Verify environment variables**
- Check that the *.env* file exists in the project root and contains the **APPLICATIONINSIGHTS_CONNECTION_STRING** value.
- Ensure you ran **source .env** (Bash) or **. .\.env.ps1** (PowerShell) to load environment variables into your terminal session.
- If variables are empty, re-run **source .env** (Bash) or **. .\.env.ps1** (PowerShell).

**Check authentication**
- Confirm you are logged in to Azure CLI by running **az account show**.
- Verify the Monitoring Metrics Publisher role is assigned to your account by checking the role assignments in the Azure portal or running the deployment script's option to assign the role again.

**Check Python environment and dependencies**
- Confirm the virtual environment is activated before running the app.
- Verify that all packages from *requirements.txt* were installed successfully by running **pip list**.
- If **azure-monitor-opentelemetry** is not installed, run **pip install -r requirements.txt** again.

**Telemetry not appearing in Application Insights**
- Telemetry can take two to five minutes to appear in the portal after the app sends it. Wait and refresh the Application Map.
- Verify the connection string is correct by comparing it to the value shown in the Azure portal under the Application Insights resource's **Overview** page.
- Check the VS Code terminal output for any errors related to telemetry export.
- Ensure you selected **Process Documents** at least twice to generate enough data for the Application Map to display.
