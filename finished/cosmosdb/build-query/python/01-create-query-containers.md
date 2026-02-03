---
lab:
    topic: Azure Cosmos DB
    title: 'Build a RAG document store on Azure Cosmos DB for NoSQL'
    description: 'Learn how to build a document storage backend for retrieval-augmented generation (RAG) using Azure Cosmos DB for NoSQL'
---

# Build a RAG document store on Azure Cosmos DB for NoSQL

In this exercise, you create an Azure Cosmos DB for NoSQL database that serves as a document store for retrieval-augmented generation (RAG) applications. The database stores chunked documents with metadata that an AI application can retrieve to provide context to language models. You design a schema optimized for document retrieval, build Python functions that store and query document chunks, and test the complete workflow. This pattern provides a foundation for building AI applications that ground language model responses in your organization's documents.

Tasks performed in this exercise:

- Download project starter files and configure the deployment script
- Deploy an Azure Cosmos DB for NoSQL account with a database and container
- Build Python functions for storing and retrieving document chunks
- Create a document schema optimized for RAG retrieval patterns
- Test the RAG document workflow using a provided test script
- Query document context using the Cosmos DB SQL API

This exercise takes approximately **30** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription with the permissions to deploy the necessary Azure services. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).
- [Python 3.12](https://www.python.org/downloads/) or greater.

## Download project starter files and deploy Azure services

In this section you download the project starter files and use a script to deploy the necessary services to your Azure subscription. The Cosmos DB account deployment takes a few minutes to complete.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/cosmosdb-build-query-python.zip
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

    ```azurecli
    az provider register --namespace Microsoft.DocumentDB
    ```

### Create resources in Azure

In this section you run the deployment script to deploy the Cosmos DB account.

1. Make sure you are in the root directory of the project and run the appropriate command in the terminal to launch the deployment script.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

1. When the script menu appears, enter **1** to launch the **Create Cosmos DB account** option. This creates the Cosmos DB for NoSQL account with a database and container. **Note:** Deployment can take 5-10 minutes to complete.

    >**IMPORTANT:** Leave the terminal running the deployment open for the duration of the exercise. You can move on to the next section of the exercise while the deployment continues in the terminal.

## Complete the RAG document functions

In this section you complete the *rag_functions.py* file by adding functions that an AI application can call to store and retrieve document chunks. These functions serve as the application's interface to the document store. The *test_workflow.py* script, which you run later in this exercise, imports these functions to demonstrate how an AI application would use them.

1. Open the *rag-backend/rag_functions.py* file in VS Code.

1. Search for the **BEGIN STORE DOCUMENT CHUNK FUNCTION** comment and add the following code directly after the comment. This function stores a document chunk with its metadata, using upsert to handle both inserts and updates.

    ```python
    def store_document_chunk(
        document_id: str,
        chunk_id: str,
        content: str,
        metadata: dict = None,
        embedding: list = None
    ) -> dict:
        """Store a document chunk with metadata and optional embedding placeholder."""
        container = get_container()

        chunk = {
            "id": chunk_id,
            "documentId": document_id,
            "content": content,
            "metadata": metadata or {},
            "embedding": embedding or [],
            "createdAt": datetime.utcnow().isoformat(),
            "chunkIndex": metadata.get("chunkIndex", 0) if metadata else 0
        }

        response = container.upsert_item(body=chunk)
        ru_charge = response.get_response_headers()['x-ms-request-charge']

        return {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "ru_charge": float(ru_charge)
        }
    ```

1. Search for the **BEGIN GET CHUNKS BY DOCUMENT FUNCTION** comment and add the following code directly after the comment. This function retrieves all chunks for a specific document, ordered by chunk index for sequential reading.

    ```python
    def get_chunks_by_document(document_id: str, limit: int = 100) -> list:
        """Retrieve all chunks for a specific document, ordered by chunk index."""
        container = get_container()

        query = """
            SELECT c.id, c.content, c.metadata, c.chunkIndex, c.createdAt
            FROM chunks c
            WHERE c.documentId = @documentId
            ORDER BY c.chunkIndex
            OFFSET 0 LIMIT @limit
        """

        items = container.query_items(
            query=query,
            parameters=[
                {"name": "@documentId", "value": document_id},
                {"name": "@limit", "value": limit}
            ],
            partition_key=document_id
        )

        return [
            {
                "chunk_id": item["id"],
                "content": item["content"],
                "metadata": item["metadata"],
                "chunk_index": item["chunkIndex"],
                "created_at": item["createdAt"]
            }
            for item in items
        ]
    ```

1. Search for the **BEGIN SEARCH CHUNKS BY METADATA FUNCTION** comment and add the following code directly after the comment. This function searches for chunks across documents using metadata filters, which is useful for finding relevant context based on tags, categories, or other attributes.

    ```python
    def search_chunks_by_metadata(
        filters: dict,
        limit: int = 10
    ) -> list:
        """Search for chunks across documents using metadata filters."""
        container = get_container()

        # Build dynamic WHERE clauses based on filters
        where_clauses = []
        parameters = []

        if "source" in filters:
            where_clauses.append("c.metadata.source = @source")
            parameters.append({"name": "@source", "value": filters["source"]})

        if "category" in filters:
            where_clauses.append("c.metadata.category = @category")
            parameters.append({"name": "@category", "value": filters["category"]})

        if "tags" in filters and filters["tags"]:
            # Check if any of the specified tags exist in the chunk's tags array
            where_clauses.append("ARRAY_CONTAINS(c.metadata.tags, @tag)")
            parameters.append({"name": "@tag", "value": filters["tags"][0]})

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
        parameters.append({"name": "@limit", "value": limit})

        query = f"""
            SELECT c.id, c.documentId, c.content, c.metadata, c.chunkIndex
            FROM chunks c
            WHERE {where_clause}
            OFFSET 0 LIMIT @limit
        """

        items = container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        )

        return [
            {
                "chunk_id": item["id"],
                "document_id": item["documentId"],
                "content": item["content"],
                "metadata": item["metadata"],
                "chunk_index": item["chunkIndex"]
            }
            for item in items
        ]
    ```

1. Search for the **BEGIN GET CHUNK BY ID FUNCTION** comment and add the following code directly after the comment. This function performs an efficient point read to retrieve a specific chunk by its ID and document ID.

    ```python
    def get_chunk_by_id(document_id: str, chunk_id: str) -> dict:
        """Retrieve a specific chunk using a point read (most efficient)."""
        container = get_container()

        try:
            item = container.read_item(
                item=chunk_id,
                partition_key=document_id
            )
            return {
                "chunk_id": item["id"],
                "document_id": item["documentId"],
                "content": item["content"],
                "metadata": item["metadata"],
                "chunk_index": item["chunkIndex"],
                "created_at": item["createdAt"],
                "embedding": item.get("embedding", [])
            }
        except exceptions.CosmosResourceNotFoundError:
            return None
    ```

1. Save your changes to the *rag_functions.py* file.

1. Take a few minutes to review all of the code in the app.

Next, you finalize the Azure resource deployment.

## Complete the Azure resource deployment

In this section you return to the deployment script to retrieve the connection information for the Cosmos DB account.

1. When the **Create Cosmos DB account** operation has completed, enter **2** to launch the **Retrieve connection info** option. This creates a file with the necessary environment variables.

1. Enter **3** to launch the **Check deployment status** option. This verifies all resources are ready.

1. Enter **4** to exit the deployment script.

1. Run the following command to load the environment variables into your terminal session from the file created in a previous step.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

    >**Note:** Keep the terminal open. If you close it and create a new terminal, you might need to run the command to create the environment variable again.

Next, you explore the document schema used for the RAG document store.

## Understand the RAG document schema

In this section you learn about the document schema designed for RAG applications. Unlike relational databases, Cosmos DB for NoSQL uses a flexible JSON document model. The container was created with **documentId** as the partition key, which groups all chunks from the same source document together for efficient retrieval.

The document schema for each chunk includes:

| Field | Description |
|-------|-------------|
| **id** | Unique identifier for the chunk (required by Cosmos DB) |
| **documentId** | Source document identifier (partition key) |
| **content** | The actual text content of the chunk |
| **metadata** | Flexible object for source, category, tags, and custom attributes |
| **embedding** | Array placeholder for vector embeddings (used in vector search scenarios) |
| **chunkIndex** | Position of the chunk within the source document |
| **createdAt** | Timestamp for when the chunk was stored |

This schema supports common RAG patterns:

- **Point reads**: Retrieve a specific chunk by ID and document ID (lowest latency)
- **Single-partition queries**: Get all chunks for a document efficiently
- **Cross-partition queries**: Search across documents by metadata
- **Vector search**: When combined with vector indexing (covered in a later exercise)

## Test the RAG document workflow

In this section you run a test script to verify the RAG functions work correctly. The *test_workflow.py* script is included in the project files and demonstrates storing document chunks, retrieving them by document, and searching by metadata.

1. Run the following command to navigate to the *rag-backend* directory.

    ```
    cd rag-backend
    ```

1. Run the following command to create a virtual environment for the *test_workflow.py* app. Depending on your environment the command might be **python** or **python3**.

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

1. Run the following command to install the Python dependencies for the app. This installs the **azure-cosmos** library for Cosmos DB connectivity.

    ```bash
    pip install -r requirements.txt
    ```

1. Run the following command to execute the test script. This script exercises all the RAG functions you created.

    ```bash
    python test_workflow.py
    ```

1. You should see output showing each step completing successfully, demonstrating that the application can store document chunks, retrieve them by document ID, search by metadata, and perform point reads.

1. Optional: Open the *test_workflow.py* file and review the code.

## Query document context

In this section you practice querying document chunks using patterns that RAG applications commonly use.

1. Run the following command to start an interactive Python session.

    ```bash
    python
    ```

1. Run the following commands to set up the Cosmos DB client. This connects using the environment variables loaded earlier.

    ```python
    import os
    from azure.cosmos import CosmosClient

    client = CosmosClient(os.environ["COSMOS_ENDPOINT"], credential=os.environ["COSMOS_KEY"])
    database = client.get_database_client(os.environ["COSMOS_DATABASE"])
    container = database.get_container_client(os.environ["COSMOS_CONTAINER"])
    ```

1. Run the following query to find all chunks for a specific document. The test script created chunks with **documentId** set to **doc-azure-overview**.

    ```python
    query = """
        SELECT c.id, c.chunkIndex, c.content, c.metadata
        FROM chunks c
        WHERE c.documentId = @docId
        ORDER BY c.chunkIndex
    """
    items = container.query_items(
        query=query,
        parameters=[{"name": "@docId", "value": "doc-azure-overview"}],
        partition_key="doc-azure-overview"
    )
    for item in items:
        print(f"Chunk {item['chunkIndex']}: {item['content'][:50]}...")
    ```

1. Run the following query to search for chunks with a specific category across all documents. This demonstrates a cross-partition query that searches metadata.

    ```python
    query = """
        SELECT c.documentId, c.id, c.content, c.metadata.category
        FROM chunks c
        WHERE c.metadata.category = @category
    """
    items = container.query_items(
        query=query,
        parameters=[{"name": "@category", "value": "cloud-services"}],
        enable_cross_partition_query=True
    )
    for item in items:
        print(f"[{item['documentId']}] {item['content'][:60]}...")
    ```

1. Run the following query to count chunks by document. This helps understand the distribution of content across source documents.

    ```python
    query = """
        SELECT c.documentId, COUNT(1) as chunkCount
        FROM chunks c
        GROUP BY c.documentId
    """
    items = container.query_items(
        query=query,
        enable_cross_partition_query=True
    )
    for item in items:
        print(f"{item['documentId']}: {item['chunkCount']} chunks")
    ```

1. Run the following query to find chunks that contain a specific tag in their metadata. This demonstrates searching within arrays using **ARRAY_CONTAINS**.

    ```python
    query = """
        SELECT c.documentId, c.id, c.content, c.metadata.tags
        FROM chunks c
        WHERE ARRAY_CONTAINS(c.metadata.tags, @tag)
    """
    items = container.query_items(
        query=query,
        parameters=[{"name": "@tag", "value": "compute"}],
        enable_cross_partition_query=True
    )
    for item in items:
        print(f"[{item['documentId']}] Tags: {item['tags']}")
    ```

1. Enter **exit()** to close the Python session.

## Summary

In this exercise, you built a Cosmos DB-based document store for RAG applications. You deployed an Azure Cosmos DB for NoSQL account with a database and container optimized for document retrieval patterns. You created Python functions that store document chunks with metadata, retrieve chunks by document ID, search across documents using metadata filters, and perform efficient point reads. You tested the workflow by running a script that simulated storing and retrieving document chunks, then queried the stored data using the Cosmos DB SQL API. This pattern enables AI applications to store chunked documents and retrieve relevant context to ground language model responses.
