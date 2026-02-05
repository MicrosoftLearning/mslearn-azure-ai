---
lab:
    topic: Azure Cosmos DB
    title: 'Optimize query performance with vector indexes'
    description: 'Learn how to compare and tune vector indexing strategies in Azure Cosmos DB for NoSQL to optimize query performance and reduce RU costs'
---

{% include under-construction.md %}

# Optimize query performance with vector indexes

In this exercise, you compare and tune vector indexing strategies to optimize query performance in Azure Cosmos DB for NoSQL. Vector indexes significantly impact both search quality and Request Unit (RU) consumption. You create containers with three different index types—flat, quantizedFlat, and diskANN—load identical sample data, and run comparative searches to measure performance differences. This hands-on practice helps you select the right indexing strategy for your AI application's requirements.

Tasks performed in this exercise:

- Download project starter files and configure the deployment script
- Deploy an Azure Cosmos DB for NoSQL account with vector search capability
- Build Python functions for comparing vector index performance
- Create containers with flat, quantizedFlat, and diskANN indexes
- Test and compare index performance using a Flask web application

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
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/cosmosdb-optimize-index-python.zip
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

## Complete the index comparison functions

In this section you complete the Python code for comparing vector index performance and review the container setup script. You add functions that perform similarity searches and track RU consumption and execution time. You also examine the different vector indexing configurations to understand how each index type is created.

### Complete the vector similarity search script

In this section you complete the *index_functions.py* file by adding the function that performs vector similarity search with performance tracking. This function is called for each container to compare how different index types handle the same query.

1. Open the *client/index_functions.py* file in VS Code.

1. Search for the **BEGIN VECTOR SIMILARITY SEARCH FUNCTION** comment and add the following code directly after the comment. This function finds documents similar to the query and tracks performance metrics.

    ```python
    def vector_similarity_search(
        container_name: str,
        query_embedding: list,
        top_n: int = 5
    ) -> dict:
        """
        Find documents most similar to the query using vector distance.

        This function performs a vector similarity search using the VectorDistance
        function and tracks the RU consumption and execution time. Results are
        ordered by distance (lowest = most similar).

        Args:
            container_name: Name of the container to search
            query_embedding: 256-dimensional query vector
            top_n: Number of results to return

        Returns:
            Dictionary containing results, ru_charge, and execution_time_ms
        """
        container = get_container(container_name)

        # Track execution time for performance comparison
        start_time = time.time()

        # The VectorDistance function calculates distance between vectors
        # Using cosine distance: 0 = identical, 2 = opposite
        # Results ordered by distance ascending (most similar first)
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

        items = list(container.query_items(
            query=query,
            parameters=[
                {"name": "@topN", "value": top_n},
                {"name": "@queryVector", "value": query_embedding}
            ],
            enable_cross_partition_query=True
        ))

        end_time = time.time()
        execution_time_ms = (end_time - start_time) * 1000

        # Get RU charge from the query - note: this is approximate for multi-page results
        # For accurate RU tracking in production, use Azure Monitor
        ru_charge = 0.0
        try:
            # The last_response_headers contains the RU charge
            ru_charge = float(container.client_connection.last_response_headers.get(
                'x-ms-request-charge', 0
            ))
        except Exception:
            pass  # RU tracking may not be available in all scenarios

        results = [
            {
                "chunk_id": item["id"],
                "document_id": item["documentId"],
                "content": item["content"],
                "metadata": item["metadata"],
                "similarity_score": item["similarityScore"]
            }
            for item in items
        ]

        return {
            "results": results,
            "ru_charge": ru_charge,
            "execution_time_ms": round(execution_time_ms, 2)
        }
    ```

1. Search for the **BEGIN COMPARE INDEX PERFORMANCE FUNCTION** comment and add the following code directly after the comment. This function runs the same query against all three containers and returns comparative results.

    ```python
    def compare_index_performance(
        query_embedding: list,
        top_n: int = 5
    ) -> dict:
        """
        Run the same vector search query against all three containers and compare performance.

        This function executes identical vector similarity searches against containers
        with different indexing strategies (flat, quantizedFlat, diskANN) to demonstrate
        the performance characteristics of each approach.

        Args:
            query_embedding: 256-dimensional query vector
            top_n: Number of results to return from each container

        Returns:
            Dictionary with results from each container including RU costs and timing
        """
        comparison = {}

        # Test each container with the same query
        for index_type, container_name in [
            ("flat", CONTAINER_FLAT),
            ("quantizedFlat", CONTAINER_QUANTIZED),
            ("diskANN", CONTAINER_DISKANN)
        ]:
            try:
                result = vector_similarity_search(container_name, query_embedding, top_n)
                comparison[index_type] = {
                    "container": container_name,
                    "results": result["results"],
                    "ru_charge": result["ru_charge"],
                    "execution_time_ms": result["execution_time_ms"],
                    "result_count": len(result["results"]),
                    "status": "success"
                }
            except Exception as e:
                comparison[index_type] = {
                    "container": container_name,
                    "results": [],
                    "ru_charge": 0,
                    "execution_time_ms": 0,
                    "result_count": 0,
                    "status": "error",
                    "error": str(e)
                }

        return comparison
    ```

1. Save your changes to the *index_functions.py* file.

### Review the container setup code

In this section you review the *setup_containers.py* script that creates containers with different vector indexing strategies. The vector index type is configured at container creation time and cannot be changed afterward—you must delete and recreate the container to use a different index. This makes upfront testing important: a common approach is to create test containers with each index type, load representative sample data, and run benchmark queries to measure RU costs and latency before committing to a production configuration.

1. Open the *client/setup_containers.py* file in VS Code.

1. Search for the **BEGIN CREATE FLAT CONTAINER FUNCTION** comment and review the code. Notice how the flat index is configured:

    ```python
    # Flat index: exact search, compares query against all vectors
    # Higher RU cost for large datasets but guaranteed best results
    indexing_policy = {
        "indexingMode": "consistent",
        "automatic": True,
        "includedPaths": [
            {"path": "/*"}
        ],
        "excludedPaths": [
            {"path": "/embedding/*"}
        ],
        "vectorIndexes": [
            {
                "path": "/embedding",
                "type": "flat"
            }
        ]
    }
    ```

1. Search for the **BEGIN CREATE QUANTIZED CONTAINER FUNCTION** comment and review the quantizedFlat configuration:

    ```python
    # QuantizedFlat index: compressed vectors for memory efficiency
    # Lower memory footprint with slight accuracy trade-off
    indexing_policy = {
        ...
        "vectorIndexes": [
            {
                "path": "/embedding",
                "type": "quantizedFlat"
            }
        ]
    }
    ```

1. Search for the **BEGIN CREATE DISKANN CONTAINER FUNCTION** comment and review the diskANN configuration:

    ```python
    # DiskANN index: approximate nearest neighbor with graph-based search
    # Best performance for large datasets, slight accuracy trade-off
    indexing_policy = {
        ...
        "vectorIndexes": [
            {
                "path": "/embedding",
                "type": "diskANN"
            }
        ]
    }
    ```

1. Take a moment to understand the key differences between index types:

    | Index Type | Search Method | Best For | Trade-offs |
    |------------|---------------|----------|------------|
    | **flat** | Exact nearest neighbor | Small datasets, highest accuracy | Higher RU for large datasets |
    | **quantizedFlat** | Compressed exact search | Medium datasets, memory efficiency | Slight accuracy loss |
    | **diskANN** | Approximate graph search | Large datasets, production | ~95% recall, best performance |

Next, you finalize the Azure resource deployment.

## Complete the Azure resource deployment

In this section you return to the deployment script to configure Entra ID access and retrieve the connection information.

1. When the **Create Cosmos DB account** operation has completed, enter **2** to launch the **Configure Entra ID access** option. This assigns your user account the necessary role to access the Cosmos DB data plane.

1. Enter **3** to launch the **Check deployment status** option. Verify the Cosmos DB account shows as ready with the vector search capability enabled.

1. Enter **4** to launch the **Retrieve connection info** option. This creates a file with the necessary environment variables.

1. Enter **5** to exit the deployment script.

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

Next, you set up the Python environment and create the vector containers.

## Set up the Python environment

In this section you create a Python virtual environment and install the dependencies needed for both the container setup script and the Flask application.

1. Run the following command to navigate to the *client* directory.

    ```
    cd client
    ```

1. Run the following command to create a virtual environment for the Python scripts. Depending on your environment the command might be **python** or **python3**.

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

1. Run the following command to install the Python dependencies. This installs the **flask**, **azure-cosmos**, and **azure-identity** libraries.

    ```bash
    pip install -r requirements.txt
    ```

Next, you create the containers with different vector indexing strategies.

## Create containers with different index strategies

In this section you run the setup script to create three Cosmos DB containers, each with a different vector indexing configuration. This enables side-by-side performance comparison.

1. Run the following command to execute the setup script and create the containers. Ensure you are still in the *client* directory with the virtual environment activated.

    ```bash
    python setup_containers.py
    ```

1. Verify the output shows all three containers were created successfully:
    - **vectors-flat** with flat index
    - **vectors-quantized** with quantizedFlat index
    - **vectors-diskann** with diskANN index

Next, you test the vector index performance using the Flask application.

## Test vector index performance with the Flask app

In this section you start the Flask web application and use its interface to compare vector search performance across the three indexing strategies. The app runs identical queries against all containers and displays the results side-by-side.

1. Ensure you are still in the *client* directory with the virtual environment activated. You should see **(.venv)** in your terminal prompt.

1. Run the following command to start the Flask application.

    ```bash
    python app.py
    ```

1. Open a browser and navigate to `http://127.0.0.1:5000` to view the application.

### Load sample data

In this section you use the app to load sample support tickets with pre-computed embeddings into all three containers. Loading identical data enables fair comparison of index performance.

1. Review the **Container Status** section at the top of the page. All three containers should show 0 documents initially.

1. In the **Load Sample Data** section, select **Load Data to All Containers**. This inserts 500 support tickets with their pre-computed embeddings from the *sample_vectors.json* file into each container. The upload uses parallel processing to load data efficiently and typically completes in 30-45 seconds.

1. Verify the success message appears showing the number of documents loaded and the RU costs for each container. Notice how write RU costs may vary slightly between index types.

### Compare vector search performance

In this section you perform vector similarity searches and compare how each index type handles the same query. The app displays RU costs and execution times side-by-side.

1. In the **Vector Search Comparison** section, select **I can't login to my account** from the **Select Query** dropdown.

1. Keep the default **Top 5** results and select **Compare Index Performance**.

1. Review the **Index Performance Comparison** table showing:
    - **Results** count for each container
    - **RU Cost** for each query
    - **Time (ms)** execution duration

1. Scroll down to see the side-by-side results of the data returned from each container. Notice:
    - All three indexes should return similar results for this small dataset
    - RU costs may vary based on index type
    - The diskANN index typically shows lower RU consumption at scale

1. Try different queries like **My payment was charged twice** or **Package hasn't arrived yet** to see consistent patterns across searches.

### Compare filtered search performance

In this section you combine metadata filtering with vector similarity search. Filtering narrows the search space before applying vector ranking, which can affect performance differently for each index type.

1. In the **Filtered Vector Search Comparison** section, select **Protect my account from hackers** from the **Select Query** dropdown.

1. Select **account** from the **Filter by Category** dropdown.

1. Select **Compare Filtered Search** to execute the filtered search across all containers.

1. Review the results. Notice:
    - Only documents with the **account** category are returned
    - The combination of filtering and vector search may show different RU patterns
    - All index types apply the filter before vector ranking

1. Try the same query with **technical** category to see different filtered results.

### Analyze the results

Based on your testing, consider these guidelines for selecting an index type:

| Scenario | Recommended Index | Reason |
|----------|-------------------|--------|
| Small dataset (< 10K vectors) | flat | Exact results, acceptable RU cost |
| Medium dataset, memory constrained | quantizedFlat | Reduced memory with good accuracy |
| Large dataset, production workload | diskANN | Best RU efficiency, ~95% recall |

1. Return to the terminal and press **Ctrl+C** to stop the Flask application.

## Summary

In this exercise, you compared vector indexing strategies in Azure Cosmos DB for NoSQL. You deployed an Azure Cosmos DB account with the **EnableNoSQLVectorSearch** capability and configured Entra ID authentication. You created three containers using the Python SDK with different vector index types: flat for exact search, quantizedFlat for memory efficiency, and diskANN for production-scale approximate search. You built Python functions that perform vector similarity searches while tracking RU consumption and execution time. You used a Flask web application to run comparative searches and analyze performance differences. This pattern helps you select the optimal indexing strategy for your AI application based on dataset size, accuracy requirements, and cost constraints.

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
- Ensure you are in the *client* directory when running **python app.py**

**Authentication or access denied errors**
- Ensure Entra ID access was configured by running the deployment script option **2**
- Verify your user has both the **Contributor** role and the **Cosmos DB Built-in Data Contributor** role
- Ensure **COSMOS_ENDPOINT** is set correctly in your terminal session

**setup_containers.py fails**
- Ensure Python virtual environment is activated
- Ensure environment variables are set (**COSMOS_ENDPOINT**, **COSMOS_DATABASE**)
- If containers already exist, the script will use the existing containers

**Vector search returns errors**
- Verify the containers were created by running **python setup_containers.py**
- Ensure sample data was loaded before running searches
- Check that the containers have the vector embedding policy configured

**Cosmos DB operations fail**
- Verify the Cosmos DB account is ready by running the deployment script option **3**
- Ensure the database was created during deployment
- Check that the account has the **EnableNoSQLVectorSearch** capability

**Environment variable issues**
- Ensure the *.env* file was created by running the deployment script option **4**
- Run **source .env** (Bash) or **. .\.env.ps1** (PowerShell) after creating a new terminal
- Verify variables are set by running **echo $COSMOS_ENDPOINT** (Bash) or **$env:COSMOS_ENDPOINT** (PowerShell)

**Python venv activation issues**
- On Linux/macOS, use: **source .venv/bin/activate**
- On Windows PowerShell, use: **.\.venv\Scripts\Activate.ps1**
- If **activate** script is missing, reinstall **python3-venv** package and recreate the venv
