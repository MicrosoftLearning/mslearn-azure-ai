---
lab:
    topic: Integrate backend services
    title: 'Build an MCP server with Azure Functions'
    description: 'Learn how to create and test an MCP server using Azure Functions that exposes tool trigger functions for AI agents and language models to discover and invoke.'
    level: 200
    duration: 25
---

# Build an MCP server with Azure Functions

The Model Context Protocol (MCP) is an open standard that defines how AI agents and language models discover and invoke external tools. Azure Functions includes an MCP extension that lets you expose function apps as MCP servers, where each function becomes a tool that MCP clients can call.

In this exercise, you create an Azure Functions project with the MCP extension, define tool trigger functions for document processing, configure the MCP server settings, and test the server locally by connecting to it from GitHub Copilot in agent mode.

>**Note:** This exercise uses the Azure Functions MCP extension, which is actively evolving. Visit the [Azure Functions MCP extension documentation](/azure/azure-functions/functions-bindings-mcp-trigger) for the most up-to-date setup instructions, API surface, and configuration options.

Tasks performed in this exercise:

- Create a new Azure Functions project with the MCP extension
- Configure the MCP server settings in *host.json*
- Define MCP tool trigger functions in *function_app.py*
- Verify the Python environment
- Test the MCP server locally using GitHub Copilot in agent mode

This exercise takes approximately **25** minutes to complete.

## Before you start

To complete the exercise, you need:

- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- The [Azure Functions extension](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-azurefunctions) for Visual Studio Code.
- [Azure Functions Core Tools](https://learn.microsoft.com/azure/azure-functions/functions-run-local) v4 or later.
- [Python 3.9](https://www.python.org/downloads/) or later.
- The [GitHub Copilot](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) extension for Visual Studio Code.

## Create a new Functions project with the MCP extension

In this section you create a new Azure Functions project in Visual Studio Code using the Azure Functions extension and configure the MCP server settings in *host.json*. The extension scaffolds the project structure, generates the *.vscode* configuration files for integrated debugging, and sets up the Python v2 programming model.

1. Create a folder for the project (for example, *mcp-server-functions*) and open it in Visual Studio Code by selecting **File > Open Folder...** in the menu.

1. Press **Ctrl+Shift+P** to open the Command Palette. Run the **Azure Functions: Create Function...** command and choose the following options when prompted:

    | Option | Action |
    |--|--|
    | Select the folder... | Select the folder you opened in the previous step |
    | Select a project type | Select **Python** |
    | Select a Python interpreter... | Select **python 3.12** |
    | Select a template... | Select **HTTP trigger** |
    | Function name | Accept the default **http_trigger** |
    | Authorization level | Select **ANONYMOUS** |

    The extension creates the project structure including *function_app.py*, *host.json*, *local.settings.json*, *requirements.txt*, and the *.vscode* folder with *launch.json*, *tasks.json*, and *extensions.json*. The scaffolded HTTP trigger function in *function_app.py* is replaced in the next section.

1. Open *host.json* and replace its contents with the following code, then save your changes. The **extensionBundle** must use the **Preview** bundle because the **mcpToolTrigger** binding type is a preview feature not included in the stable extension bundle. The **mcpToolTrigger** section defines the MCP server name, version, and instructions that MCP clients display when connecting.

    ```json
    {
        "version": "2.0",
        "extensionBundle": {
            "id": "Microsoft.Azure.Functions.ExtensionBundle.Preview",
            "version": "[4.*, 5.0.0)"
        },
        "extensions": {
            "mcpToolTrigger": {
                "serverName": "document-tools",
                "serverVersion": "1.0.0",
                "serverInstructions": "Tools for document processing and classification"
            }
        }
    }
    ```

1. Open *local.settings.json* and replace its contents with the following code.

    ```json
    {
      "IsEncrypted": false,
      "Values": {
        "AzureWebJobsStorage": "",
        "FUNCTIONS_WORKER_RUNTIME": "python",
        "AzureWebJobsSecretStorageType": "Files"
      }
    }
    ```

1. Create a *.vscode/mcp.json* file in the project to register the local MCP endpoint with Visual Studio Code. This file tells Visual Studio Code where to find MCP servers and how to connect to them. Add the following code to the file, then save your changes.

    ```json
    {
        "servers": {
            "document-tools-local": {
                "type": "sse",
                "url": "http://localhost:7071/runtime/webhooks/mcp/sse"
            }
        }
    }
    ```

## Define MCP tool trigger functions

In this section you define two MCP tool trigger functions that become discoverable tools for MCP clients. Each function uses the **@app.generic_trigger()** decorator with the **mcpToolTrigger** type. You define the tool name, description, and input properties through the trigger configuration, and the function receives tool invocation requests from connected MCP clients.

1. Open *function_app.py* in the Visual Studio Code Explorer sidebar and replace its contents with the following code that defines two MCP tool trigger functions:

    ```python
    import azure.functions as func
    import json
    import logging

    # Initialize the FunctionApp instance that registers all trigger functions
    app = func.FunctionApp()

    # Define an MCP tool trigger that exposes "summarize_text" to MCP clients.
    # toolProperties defines the input schema: a single "text" string parameter.
    @app.generic_trigger(
        arg_name="context",
        type="mcpToolTrigger",
        toolName="summarize_text",
        description="Summarize a block of text into key points",
        toolProperties='[{"propertyName": "text", "propertyType": "string", "description": "The text to summarize"}]'
    )
    def summarize_text(context: str) -> str:
        # Log the raw payload for debugging
        logging.info(f"summarize_text raw context: {context}")
        # Parse the outer request envelope sent by the MCP client
        request = json.loads(context)
        logging.info(f"summarize_text parsed request: {request}")
        # Extract the tool arguments from the request
        arguments = request.get("arguments", {})
        # Retrieve the "text" property defined in toolProperties
        text = arguments.get("text", "")

        # In a real implementation, call an Azure AI service here
        summary = f"Summary of {len(text.split())} words: {text[:100]}..."

        # Return a JSON response; the "content" field is displayed to the MCP client
        return json.dumps({"content": summary})

    # Define a second MCP tool trigger that exposes "classify_document" to MCP clients.
    # toolProperties defines two input parameters: "text" and "categories".
    @app.generic_trigger(
        arg_name="context",
        type="mcpToolTrigger",
        toolName="classify_document",
        description="Classify a document into a category",
        toolProperties='[{"propertyName": "text", "propertyType": "string", "description": "The document text to classify"}, {"propertyName": "categories", "propertyType": "string", "description": "Comma-separated list of possible categories"}]'
    )
    def classify_document(context: str) -> str:
        # Log the raw payload for debugging
        logging.info(f"classify_document raw context: {context}")
        # Parse the outer request envelope sent by the MCP client
        request = json.loads(context)
        logging.info(f"classify_document parsed request: {request}")
        # Extract the tool arguments from the request
        arguments = request.get("arguments", {})
        # Retrieve the "text" and "categories" properties defined in toolProperties
        text = arguments.get("text", "")
        categories = arguments.get("categories", "general")

        # In a real implementation, call an Azure AI service here
        # Split the comma-separated categories string into a list
        category_list = [c.strip() for c in categories.split(",")]
        # Select the first category as the classification result
        selected_category = category_list[0] if category_list else "unknown"

        # Return a JSON response with the classification result
        return json.dumps({
            "content": f"Classification: {selected_category}",
            "category": selected_category
        })
    ```

1. Save the file and take a few minutes to review the code. Each function uses the **@app.generic_trigger()** decorator with the **mcpToolTrigger** type. The **toolName** appears in the MCP client's tool list, and **description** helps language models understand when to use each tool. The **toolProperties** parameter defines the input schema as a JSON array of property definitions.

## Verify the Python environment

In this section you verify that Visual Studio Code is using the Python interpreter from the virtual environment that the Azure Functions extension created during project setup.

1. Press **Ctrl+Shift+P** to open the Command Palette and run the **Python: Select Interpreter** command. Select the interpreter from the *.venv* folder in the project directory (for example, *./.venv/bin/python*). This ensures the debugger and terminal use the correct environment when you start the Functions runtime with **F5**.

## Test the MCP server locally

In this section you start the local Functions runtime and connect to the MCP server from GitHub Copilot in agent mode to verify that the tools are discoverable and return the expected results.

1. Press **F5** to start the Functions runtime with the debugger attached. If you receive a warning about a required storage account, select **Skip for now** . Visual Studio Code launches Core Tools, attaches the debugger, and opens the terminal panel showing the function endpoints.

    >**Note:** You can also start the runtime without the debugger by running `func start` in the integrated terminal.

    The terminal output shows the registered MCP tool trigger functions. Verify you see output similar to:

    ```
    Functions:
        classify_document: mcpToolTrigger
        summarize_text: mcpToolTrigger
    ```

    If both functions appear, the MCP server is running and ready for connections.

1. Visual Studio Code detects the *.vscode/mcp.json* file you created earlier and connects to the MCP server. Open GitHub Copilot chat and switch to **Agent** mode. Select the tools icon (wrench) and look for the **document-tools-local** group — this matches the server key name from *.vscode/mcp.json*. Verify that both **summarize_text** and **classify_document** appear under that group with their descriptions.

### Test with explicit prompts

Explicit prompts that name a tool directly are the most reliable way to trigger an MCP tool. The model will usually invoke the tool, but it may still rephrase or summarize the tool's raw output in its response. If a tool is not invoked, check the terminal output to confirm, then try submitting the prompt again.

1. Test the **classify_document** tool by entering the following prompt in the Copilot chat. **Note:** When Copilot invokes an MCP tool for the first time, you may see a permission prompt. Select **Allow** to let Copilot call the tool.

    ```
    Use the classify_document tool to classify this text: 'This agreement is entered into by Party A and Party B'  with categories: contract, invoice, memo
    ```

    Copilot invokes the tool and returns a response. Verify the result contains a classification of **contract**. The stub implementation selects the first category from the comma-separated list, so the result matches the first category you provided in the prompt. Check the terminal output for the function invocation log entry.

1. Test the **summarize_text** tool by entering the following prompt in the Copilot chat.

    ```
    Use the summarize_text tool to summarize this text: 'Azure Functions is a serverless compute service that lets you run event-triggered code without having to explicitly provision or manage infrastructure.'
    ```

    Verify the result contains a summary string starting with **Summary of** followed by the word count and a truncated preview of the input text.

### Test with natural language prompts

Natural language prompts are more likely to answer a prompt directly without invoking a tool, since the model must decide on its own whether a tool is relevant. Check the terminal output for logging entries to confirm whether a tool was actually invoked. If it was not, try rephrasing the prompt or explicitly naming the tool.

1. Enter the following prompt in the Copilot chat:

    ```
    Is the following text an invoice, contract, or memo?
    'Invoice B1234 for services rendered in January 2026. Total amount due: $5,000.'
    ```

    Copilot should recognize that the **classify_document** tool matches this request and invoke it automatically. Verify the result returns a classification. Check the terminal output to confirm the function was invoked.

1. Enter the following prompt to test natural tool discovery for the **summarize_text** tool:

    ```
    Give me a brief summary of this text: 'Machine learning models require large datasets for training. The quality of the training data directly impacts model accuracy. Data preprocessing steps include cleaning, normalization, and feature extraction.'
    ```

    Copilot should invoke the **summarize_text** tool and return a summary. Verify the terminal output shows the function invocation.

1. Press **Shift+F5** to stop the debugger and shut down the Functions runtime.

## Next steps

In a production scenario, you would deploy the function app to Azure using the Flex Consumption plan, authenticate MCP client connections with the **mcp_extension** system key, and replace the placeholder logic in each tool function with calls to Azure AI services using **DefaultAzureCredential** and the function app's managed identity. For more details, see the [Azure Functions MCP extension documentation](/azure/azure-functions/functions-bindings-mcp-trigger).

## Troubleshooting

If you encounter issues while completing this exercise, try the following troubleshooting steps:

**Azure Functions Core Tools not starting**
- Confirm that Azure Functions Core Tools v4 or later is installed by running **func --version** in the terminal.
- Verify that port 7071 is not in use by another process.
- Ensure *local.settings.json* exists in the project root. The Azure Functions extension generates this file during project creation.

**MCP tools not appearing in Copilot**
- Verify that *.vscode/mcp.json* is saved and the URL matches the local endpoint (`http://localhost:7071/runtime/webhooks/mcp/sse`).
- Confirm the Functions runtime is running and shows both tool trigger functions in the terminal output.
- Try restarting Visual Studio Code if the MCP server configuration is not detected after saving the file.

**Function invocation returns errors**
- Check the terminal output for Python exceptions or stack traces.
- Verify *function_app.py* has correct indentation and that all code was entered as shown.
- Confirm the virtual environment is activated and all dependencies from *requirements.txt* are installed.

**Check Python environment and dependencies**
- Confirm that Visual Studio Code is using the Python interpreter from the *.venv* folder by running the **Python: Select Interpreter** command.
- Verify that all packages from *requirements.txt* were installed successfully by running **pip list** in the integrated terminal.
