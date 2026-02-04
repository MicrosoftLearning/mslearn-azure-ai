---
lab:
    topic: Azure Cosmos DB
    title: 'Build a semantic search application with vector search'
    description: 'Learn how to implement vector similarity search in Azure Cosmos DB for NoSQL to enable semantic search over document data'
---

# Build a semantic search application with vector search

In this exercise, you implement vector similarity search using Azure Cosmos DB for NoSQL. Vector search enables semantic matching by comparing high-dimensional vector representations of text, finding relevant results even when exact terms don't match. You configure a container with vector embedding and indexing policies, load documents with pre-computed embeddings, and execute similarity queries using the **VectorDistance** function. This pattern provides a foundation for building AI applications that perform semantic search over document data.

Tasks performed in this exercise:

- Download project starter files and configure the deployment script
- Deploy an Azure Cosmos DB for NoSQL account with vector search capability
- Build Python functions for vector similarity search
- Test vector search using a Flask web application
- Execute filtered vector queries using the Cosmos DB SQL API

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
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/cosmosdb-implement-vector-python.zip
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

In this section you run the deployment script to deploy the Cosmos DB account with vector search capability.

1. Make sure you are in the root directory of the project and run the appropriate command in the terminal to launch the deployment script.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

1. When the script menu appears, enter **1** to launch the **Create Cosmos DB account** option. This creates the Cosmos DB for NoSQL account with the **EnableNoSQLVectorSearch** capability and a database. **Note:** Deployment can take 5-10 minutes to complete.

    >**IMPORTANT:** Leave the terminal running the deployment open for the duration of the exercise. You can move on to the next section of the exercise while the deployment continues in the terminal.

## Complete the vector search functions

In this section you complete the *vector_functions.py* file by adding functions that perform vector similarity search. These functions use the **VectorDistance** function to calculate similarity between query vectors and document embeddings. The *test_workflow.py* script, which you run later in this exercise, imports these functions to demonstrate how an AI application would use them.

1. Open the *client/vector_functions.py* file in VS Code.

1. Search for the **BEGIN STORE VECTOR DOCUMENT FUNCTION** comment and add the following code directly after the comment. This function stores a document with its vector embedding for similarity search.

    ```python
    def store_vector_document(
        document_id: str,
        chunk_id: str,
        content: str,
        embedding: list,
        metadata: dict = None
    ) -> dict:
        """Store a document with its vector embedding for similarity search."""
        container = get_container()

        # Build the document structure with embedding for vector search
        # The 'id' field is required by Cosmos DB and must be unique within the partition
        # The 'documentId' field is our partition key - chunks from the same source document
        # are stored together for efficient retrieval
        # The 'embedding' field contains the vector that will be used for similarity search
        document = {
            "id": chunk_id,
            "documentId": document_id,
            "content": content,
            "embedding": embedding,  # 256-dimensional vector for similarity search
            "metadata": metadata or {},
            "createdAt": datetime.utcnow().isoformat(),
            "chunkIndex": metadata.get("chunkIndex", 0) if metadata else 0
        }

        # upsert_item inserts if new, updates if exists (based on id + partition key)
        # This is idempotent - safe to call multiple times with the same data
        response = container.upsert_item(body=document)

        # Request Units (RUs) measure the cost of database operations in Cosmos DB
        # Tracking RU consumption helps optimize queries and estimate costs
        ru_charge = response.get_response_headers()['x-ms-request-charge']

        return {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "ru_charge": float(ru_charge)
        }
    ```

1. Search for the **BEGIN VECTOR SIMILARITY SEARCH FUNCTION** comment and add the following code directly after the comment. This function finds documents most similar to a query using vector distance.

    ```python
    def vector_similarity_search(
        query_embedding: list,
        top_n: int = 5
    ) -> list:
        """
        Find documents most similar to the query using vector distance.

        Uses the VectorDistance function to calculate cosine similarity between
        the query embedding and document embeddings stored in Cosmos DB.
        Results are ordered by similarity (lowest distance = most similar).
        """
        container = get_container()

        # The VectorDistance function calculates the distance between two vectors
        # Using cosine distance: 0 = identical, 2 = opposite
        # We order by distance ascending so most similar results come first
        # The @queryVector parameter contains our 256-dimensional query embedding
        query = """
            SELECT TOP @topN
                c.id,
                c.documentId,
                c.content,
                c.metadata,
                VectorDistance(c.embedding, @queryVector) AS similarityScore
            FROM c
            ORDER BY VectorDistance(c.embedding, @queryVector)
        """

        items = container.query_items(
            query=query,
            parameters=[
                {"name": "@topN", "value": top_n},
                {"name": "@queryVector", "value": query_embedding}
            ],
            enable_cross_partition_query=True
        )

        return [
            {
                "chunk_id": item["id"],
                "document_id": item["documentId"],
                "content": item["content"],
                "metadata": item["metadata"],
                "similarity_score": item["similarityScore"]
            }
            for item in items
        ]
    ```

1. Search for the **BEGIN FILTERED VECTOR SEARCH FUNCTION** comment and add the following code directly after the comment. This function combines vector similarity search with metadata filtering for hybrid queries.

    ```python
    def filtered_vector_search(
        query_embedding: list,
        category: str = None,
        top_n: int = 5
    ) -> list:
        """
        Combine vector similarity search with metadata filtering.

        This hybrid approach first filters documents by category (or other metadata),
        then ranks the filtered results by vector similarity. This is useful for
        narrowing results to a specific domain before applying semantic search.
        """
        container = get_container()

        # Build WHERE clause for metadata filtering
        # The filter is applied BEFORE vector ranking, reducing the search space
        where_clause = ""
        parameters = [
            {"name": "@topN", "value": top_n},
            {"name": "@queryVector", "value": query_embedding}
        ]

        if category:
            where_clause = "WHERE c.metadata.category = @category"
            parameters.append({"name": "@category", "value": category})

        # Filtered vector search: apply metadata filter, then rank by similarity
        query = f"""
            SELECT TOP @topN
                c.id,
                c.documentId,
                c.content,
                c.metadata,
                VectorDistance(c.embedding, @queryVector) AS similarityScore
            FROM c
            {where_clause}
            ORDER BY VectorDistance(c.embedding, @queryVector)
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
                "similarity_score": item["similarityScore"]
            }
            for item in items
        ]
    ```

1. Save your changes to the *vector_functions.py* file.

1. Take a few minutes to review all of the code in the file.

Next, you finalize the Azure resource deployment.

## Complete the Azure resource deployment

In this section you return to the deployment script to configure Entra ID access, create the vector container, and retrieve the connection information.

1. When the **Create Cosmos DB account** operation has completed, enter **2** to launch the **Configure Entra ID access** option. This assigns your user account the necessary role to access the Cosmos DB data plane.

1. Enter **3** to launch the **Create vector container** option. This creates a container with the vector embedding policy (256 dimensions, cosine distance) and a DiskANN vector index.

1. Enter **4** to launch the **Check deployment status** option. This verifies all resources are ready, including the vector search capability.

1. Enter **5** to launch the **Retrieve connection info** option. This creates a file with the necessary environment variables.

1. Enter **6** to exit the deployment script.

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

Next, you explore the vector container configuration.

## Understand the vector container configuration

In this section you learn about the vector embedding and indexing policies configured for the container. The deployment script created the container with specific settings that enable vector similarity search.

The vector embedding policy defines how embeddings are stored:

| Setting | Value | Description |
|---------|-------|-------------|
| **path** | /embedding | JSON path where vectors are stored |
| **dataType** | float32 | Data type for vector components |
| **distanceFunction** | cosine | Similarity metric (0=identical, 2=opposite) |
| **dimensions** | 256 | Number of dimensions in each vector |

The indexing policy includes a vector index:

| Setting | Value | Description |
|---------|-------|-------------|
| **path** | /embedding | Path to index for vector search |
| **type** | diskANN | Approximate nearest neighbor algorithm |

The DiskANN index type provides efficient approximate nearest neighbor search, enabling fast similarity queries even with large datasets. The embedding path is excluded from standard indexing since vectors use their own specialized index.

## Test the vector search functions with the Flask app

In this section you start the Flask web application and use its interface to test the vector search functions you created. The app provides a visual way to load data, run tests, and execute vector similarity searches.

1. Run the following command to navigate to the *client* directory.

    ```
    cd client
    ```

1. Run the following command to create a virtual environment for the Flask app. Depending on your environment the command might be **python** or **python3**.

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

1. Run the following command to install the Python dependencies for the app. This installs the **flask**, **azure-cosmos**, and **azure-identity** libraries.

    ```bash
    pip install -r requirements.txt
    ```

1. Run the following command to start the Flask application.

    ```bash
    flask run
    ```

1. Open a browser and navigate to `http://127.0.0.1:5000` to view the application.

### Load sample data

In this section you use the app to load sample documents with pre-computed embeddings into the Cosmos DB container. The sample data includes 12 documents about Azure services, each with a 256-dimensional embedding vector.

1. In the **Load Sample Data** section, select **Load Vector Data**. This inserts documents with their pre-computed embeddings from the *sample_vectors.json* file.

1. Verify that the success message appears showing the number of documents loaded and the total RU (Request Unit) charge.

### Run test workflow

In this section you run automated tests that verify the vector search functions you created in *vector_functions.py* work correctly.

1. In the **Run Test Workflow** section, select **Run Tests**. This executes tests that exercise each vector search function.

1. Review the test results in the **Results** panel. Each test should show a **passed** status:
    - Store vector documents
    - Vector similarity search
    - Filtered vector search

### Vector similarity search

In this section you perform semantic searches using pre-computed query vectors. The app calls the **vector_similarity_search()** function you created in *vector_functions.py*.

1. In the **Vector Similarity Search** section, select **What is a NoSQL database?** from the **Select Query** dropdown.

1. Keep the default **Top 5** results and select **Search**.

1. Review the results showing documents ranked by similarity score. Notice that documents about Cosmos DB and databases appear first, even though the query doesn't contain the exact words from those documents.

1. Try selecting different queries such as **How does vector similarity search work?** or **What is RAG and how is it used with AI?** to see how the semantic search finds relevant content.

### Filtered vector search

In this section you combine metadata filtering with vector similarity ranking. The app calls the **filtered_vector_search()** function you created in *vector_functions.py*. You observe how filtering narrows results to a specific category.

1. In the **Filtered Vector Search** section, select **What is a NoSQL database?** from the **Select Query** dropdown.

1. Select **databases** from the **Filter by Category** dropdown.

1. Select **Search with Filter** to execute the filtered search.

1. Review the results. Notice that only documents with the **databases** category are returned, ranked by similarity to the query.

1. Try the same query with **ai-applications** category to see different results that are still semantically relevant but limited to AI-related content.

## Query vector data

In this section you practice writing SQL queries that use the **VectorDistance** function. These queries demonstrate patterns that AI applications commonly use for semantic search.

1. In the **Query Explorer** section, enter the following query to retrieve all documents with their metadata. This helps you understand the data structure.

    ```sql
    SELECT c.id, c.documentId, c.content, c.metadata
    FROM c
    OFFSET 0 LIMIT 5
    ```

1. Select **Execute Query** and review the results.

1. Now enter a vector similarity query. Copy one of the query embeddings from *sample_vectors.json* (the embedding array for "query-database-nosql") and use it in this query pattern:

    ```sql
    SELECT TOP 3
        c.id,
        c.content,
        c.metadata.category,
        VectorDistance(c.embedding, [0.085, -0.026, ...]) AS score
    FROM c
    ORDER BY VectorDistance(c.embedding, [0.085, -0.026, ...])
    ```

    >**Note:** The query above uses a truncated embedding array for readability. In practice, you would include all 256 values.

1. Return to the terminal and press **Ctrl+C** to stop the Flask application.

## Summary

In this exercise, you implemented vector similarity search using Azure Cosmos DB for NoSQL. You deployed an Azure Cosmos DB account with the **EnableNoSQLVectorSearch** capability and created a container with vector embedding and indexing policies. You built Python functions that store documents with embeddings, perform vector similarity search using the **VectorDistance** function, and combine vector search with metadata filters. You tested the workflow using a Flask web application and explored vector queries using the SQL API. This pattern enables AI applications to perform semantic search over document data, finding relevant results based on meaning rather than exact keyword matches.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you chose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues during this exercise, try these steps:

**Flask app fails to start**
- Ensure Python virtual environment is activated (you should see **(.venv)** in your terminal prompt)
- Ensure dependencies are installed: **pip install -r requirements.txt**
- Ensure environment variables are loaded by running **source .env** (Bash) or **. .\.env.ps1** (PowerShell)
- Ensure you are in the *client* directory when running **flask run**

**Authentication or access denied errors**
- Ensure Entra ID access was configured by running the deployment script option **2**
- Verify your user has both the **Contributor** role and the **Cosmos DB Built-in Data Contributor** role
- Ensure **COSMOS_ENDPOINT** is set correctly in your terminal session

**Vector search returns no results or errors**
- Verify the vector container was created by running the deployment script option **3**
- Ensure the container has the vector embedding policy configured (check status with option **4**)
- Verify sample data was loaded before running searches

**Cosmos DB operations fail**
- Verify the Cosmos DB account is ready by running the deployment script option **4**
- Ensure the database and container were created during deployment
- Check that the account has the **EnableNoSQLVectorSearch** capability

**Environment variable issues**
- Ensure the *.env* file was created by running the deployment script option **5**
- Run **source .env** (Bash) or **. .\.env.ps1** (PowerShell) after creating a new terminal
- Verify variables are set by running **echo $COSMOS_ENDPOINT** (Bash) or **$env:COSMOS_ENDPOINT** (PowerShell)

**Python venv activation issues**
- On Linux/macOS, use: **source .venv/bin/activate**
- On Windows PowerShell, use: **.\.venv\Scripts\Activate.ps1**
- If **activate** script is missing, reinstall **python3-venv** package and recreate the venv
