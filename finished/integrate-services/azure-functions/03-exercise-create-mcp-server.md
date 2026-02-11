The Model Context Protocol (MCP) is an open standard that defines how AI agents and language models discover and invoke external tools. Azure Functions includes an MCP extension that lets you expose function apps as remote MCP servers, where each function becomes a tool that MCP clients can call. In this exercise, you create and deploy an MCP server using Azure Functions that exposes tool trigger functions for an AI agent to use.

> [!NOTE]
> This exercise uses the Azure Functions MCP extension, which is actively evolving. Visit the [Azure Functions MCP extension documentation](/azure/azure-functions/functions-bindings-mcp-trigger) for the most up-to-date setup instructions, API surface, and configuration options.

## Create a new Functions project with the MCP extension

You can start by creating a new Azure Functions project in Visual Studio Code using the Azure Functions extension. The extension scaffolds the project structure, generates the `.vscode` configuration files for integrated debugging, and sets up the Python v2 programming model.

1. Create a folder for the project (for example, `mcp-server-functions`) and open it in Visual Studio Code.

1. Press **Ctrl+Shift+P** (or **Cmd+Shift+P** on macOS) to open the Command Palette. Run the **Azure Functions: Create Function...** command and choose the following options when prompted:

    - **Language:** Python
    - **Python programming model:** Model V2
    - **Python interpreter:** Select your Python 3.9+ interpreter
    - **Template:** Skip for now (you'll define functions in the next section)

    The extension creates the project structure including `function_app.py`, `host.json`, `local.settings.json`, `requirements.txt`, and the `.vscode` folder with `launch.json`, `tasks.json`, and `extensions.json`.

1. Open the integrated terminal in Visual Studio Code (**Ctrl+`**) and install the project dependencies:

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

1. Open `host.json` in the Explorer sidebar and add the MCP server configuration. The extension already generated this file with the `extensionBundle` section. You can add the `mcpToolTrigger` section, which defines the server name, version, and instructions that MCP clients display when connecting:

    ```json
    {
        "version": "2.0",
        "extensionBundle": {
            "id": "Microsoft.Azure.Functions.ExtensionBundle",
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

## Define MCP tool trigger functions

MCP tool trigger functions are regular Azure Functions that use the `@app.generic_trigger()` decorator with the MCP trigger type. Each function becomes a discoverable tool that MCP clients can invoke. You define the tool name, description, and input properties through the trigger configuration, and the function receives tool invocation requests from connected MCP clients.

1. Open `function_app.py` in the Visual Studio Code Explorer sidebar and replace its contents with the following code that defines two MCP tool trigger functions:

    ```python
    import azure.functions as func
    import json
    import logging

    app = func.FunctionApp()

    @app.generic_trigger(
        arg_name="context",
        type="mcpToolTrigger",
        toolName="summarize_text",
        description="Summarize a block of text into key points",
        toolProperties='[{"propertyName": "text", "propertyValue": "string", "description": "The text to summarize"}]'
    )
    def summarize_text(context: str) -> str:
        request = json.loads(context)
        content = json.loads(request.get("content", "{}"))
        text = content.get("text", "")

        # In a real implementation, call an Azure AI service here
        summary = f"Summary of {len(text.split())} words: {text[:200]}..."

        return json.dumps({"content": summary})

    @app.generic_trigger(
        arg_name="context",
        type="mcpToolTrigger",
        toolName="classify_document",
        description="Classify a document into a category",
        toolProperties='[{"propertyName": "text", "propertyValue": "string", "description": "The document text to classify"}, {"propertyName": "categories", "propertyValue": "string", "description": "Comma-separated list of possible categories"}]'
    )
    def classify_document(context: str) -> str:
        request = json.loads(context)
        content = json.loads(request.get("content", "{}"))
        text = content.get("text", "")
        categories = content.get("categories", "general")

        # In a real implementation, call an Azure AI service here
        category_list = [c.strip() for c in categories.split(",")]
        selected_category = category_list[0] if category_list else "unknown"

        return json.dumps({
            "content": f"Classification: {selected_category}",
            "category": selected_category
        })
    ```

    Each function uses the `@app.generic_trigger()` decorator with the `mcpToolTrigger` type. The `toolName` appears in the MCP client's tool list, and `description` helps language models understand when to use each tool. The `toolProperties` parameter defines the input schema as a JSON array of property definitions.

## Test the MCP server locally

You can test the MCP server locally by starting the Functions runtime with the Visual Studio Code debugger and connecting to the MCP endpoint from the built-in MCP client. The local runtime starts an SSE (Server-Sent Events) endpoint that MCP clients connect to for tool discovery and invocation.

1. Press **F5** to start the Functions runtime with the debugger attached. Visual Studio Code launches Core Tools, attaches the debugger, and opens the terminal panel showing the function endpoints.

    > [!NOTE]
    > You can also start the runtime without the debugger by running `func start` in the integrated terminal.

    The terminal output shows the registered MCP tool trigger functions. Look for output similar to:

    ```
    Functions:
        classify_document: mcpToolTrigger
        summarize_text: mcpToolTrigger
    ```

1. The MCP SSE endpoint is available at `http://localhost:7071/runtime/webhooks/mcp/sse`. You can create a `.vscode/mcp.json` file in your project to register this endpoint as an MCP server in Visual Studio Code. This file tells Visual Studio Code where to find MCP servers and how to connect to them. Create the file with the following content:

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

1. After saving `.vscode/mcp.json`, Visual Studio Code detects the MCP server configuration. You can open GitHub Copilot chat in agent mode and verify that the `summarize_text` and `classify_document` tools appear in the available tools list. You can test a tool by asking Copilot to use it, such as: "Use the classify_document tool to classify this text: 'This agreement is entered into by Party A and Party B' with categories: contract, invoice, memo."

## Deploy the MCP server to Azure

After testing locally, you can deploy the function app to Azure and configure it for production access. The deployed MCP server uses the `mcp_extension` system key to authenticate client connections.

1. Create a function app in Azure using the Flex Consumption plan:

    ```azurecli
    az functionapp create \
        --resource-group myResourceGroup \
        --name mcp-server-app \
        --consumption-plan-location eastus2 \
        --runtime python \
        --runtime-version 3.11 \
        --functions-version 4 \
        --storage-account mystorageaccount
    ```

1. Deploy your function app:

    ```bash
    func azure functionapp publish mcp-server-app
    ```

1. Retrieve the `mcp_extension` system key for the deployed function app. MCP clients use this key to authenticate when connecting to the remote server:

    ```azurecli
    az functionapp keys list \
        --resource-group myResourceGroup \
        --name mcp-server-app \
        --query "systemKeys.mcp_extension" \
        --output tsv
    ```

1. Update `.vscode/mcp.json` to add the remote server alongside the local server entry. You can replace `<mcp_extension_system_key>` with the key value from the previous step:

    ```json
    {
        "servers": {
            "document-tools-local": {
                "type": "sse",
                "url": "http://localhost:7071/runtime/webhooks/mcp/sse"
            },
            "document-tools-remote": {
                "type": "sse",
                "url": "https://mcp-server-app.azurewebsites.net/runtime/webhooks/mcp/sse",
                "headers": {
                    "x-functions-key": "<mcp_extension_system_key>"
                }
            }
        }
    }
    ```

    The `mcp_extension` system key provides access specifically to the MCP SSE endpoint. It's a system key, not a function key, because the MCP endpoint is managed by the extension rather than by individual functions.

## Verify the deployment

You can verify your deployed MCP server by connecting to it from Visual Studio Code and invoking a tool through GitHub Copilot.

1. After saving the updated `.vscode/mcp.json`, Visual Studio Code detects the `document-tools-remote` server. You can open GitHub Copilot chat in agent mode and confirm that the tools from the remote server appear in the available tools list.

1. Verify that both `summarize_text` and `classify_document` appear with their descriptions and input schemas.

1. Test the remote server by asking Copilot to invoke the `classify_document` tool with sample input, such as: "Use the classify_document tool to classify this text: 'Invoice #1234 for services rendered in January' with categories: contract, invoice, memo." Verify that the function processes the request and returns a classification result.

In a production implementation, you would replace the placeholder logic in each tool function with calls to Azure AI services using `DefaultAzureCredential` and the function app's managed identity, following the patterns from earlier units in this module.
