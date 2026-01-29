---
lab:
    topic: Azure Database for PostgreSQL
    title: 'Optimize vector search performance'
    description: 'Learn how to optimize vector search performance in Azure Database for PostgreSQL using indexes, parameter tuning, and connection pooling'
---

# Optimize vector search performance

In this exercise, you deploy an Azure Database for PostgreSQL instance and optimize it for vector search workloads. You create test data with vector embeddings, analyze baseline performance, build and compare IVFFlat and HNSW indexes, tune search parameters, and configure PgBouncer connection pooling. These techniques are essential for production AI applications that require fast similarity search across large datasets.

Tasks performed in this exercise:

- Download project starter files and configure the deployment script
- Deploy an Azure Database for PostgreSQL Flexible Server with Microsoft Entra authentication
- Create a test dataset with vector embeddings
- Analyze baseline vector search performance without indexes
- Create and compare IVFFlat and HNSW vector indexes
- Tune index parameters to balance speed and recall
- Configure PgBouncer connection pooling
- Monitor performance using Azure Monitor

This exercise takes approximately **XX** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription with the permissions to deploy the necessary Azure services. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).
- [PostgreSQL command-line tools](https://www.postgresql.org/download/) (**psql**)

## Download project starter files and deploy Azure services

In this section you download the project starter files and use a script to deploy the necessary services to your Azure subscription. The PostgreSQL server deployment takes a few minutes to complete.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/postgresql-optimize-vector-search-python.zip
    ```

1. Copy, or move, the file to a location in your system where you want to work on the project. Then unzip the file into a folder.

1. Launch Visual Studio Code (VS Code) and select **File > Open Folder...** in the menu, then choose the folder containing the project files.

1. The project contains deployment scripts for both Bash (*azdeploy.sh*) and PowerShell (*azdeploy.ps1*). Open the appropriate file for your environment and change the two values at the top of the script to meet your needs, then save your changes. **Note:** Do not change anything else in the script.

    ```
    "<your-resource-group-name>" # Resource Group name
    "<your-azure-region>" # Azure region for the resources
    ```

1. In the menu bar select **Terminal > New Terminal** to open a terminal window in VS Code.

    >**Tip:** This entire exercise is performed in the terminal. Maximize the panel size to make it easier to view the results of the commands.

1. Run the following command to log in to your Azure account. Answer the prompts to select your Azure account and subscription for the exercise.

    ```
    az login
    ```

1. Run the following command to ensure your subscription has the necessary resource provider for the exercise.

    ```azurecli
    az provider register --namespace Microsoft.DBforPostgreSQL
    ```

### Create resources in Azure

In this section you run the deployment script to deploy the PostgreSQL server and configure authentication.

1. Make sure you are in the root directory of the project and run the appropriate command in the terminal to launch the deployment script.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

1. When the script menu appears, enter **1** to launch the **Create PostgreSQL server with Entra authentication** option. This creates the server with Entra-only authentication enabled. **Note:** Deployment can take 5-10 minutes to complete.

    >**IMPORTANT:** Leave the terminal running the deployment open for the duration of the exercise. You can move on to the next section of the exercise while the deployment continues in the terminal.

## Review vector index concepts

In this section you review the key concepts for vector indexing that you apply later in the exercise. Understanding these trade-offs helps you make informed decisions when optimizing vector search.

### IVFFlat indexes

IVFFlat (Inverted File with Flat compression) divides vectors into clusters called **lists**. When searching, it only scans vectors in nearby clusters rather than the entire dataset.

Key parameters:

- **lists**: Number of clusters to create. A good starting point is `rows / 1000` for up to 1 million rows. More lists means faster searches but slower index builds.
- **probes**: Number of clusters to search at query time. Higher values improve recall (finding the true nearest neighbors) but increase latency.

### HNSW indexes

HNSW (Hierarchical Navigable Small World) builds a multi-layer graph structure. Upper layers contain fewer nodes for fast navigation; lower layers contain more nodes for precise searching.

Key parameters:

- **m**: Maximum connections per node. Higher values improve recall but increase memory usage and build time. Default is 16.
- **ef_construction**: Size of the dynamic candidate list during index building. Higher values create better quality graphs but take longer to build. Default is 64.
- **ef_search**: Size of the dynamic candidate list during search. Higher values improve recall but increase latency. Default is 40.

### When to use each

| Consideration | IVFFlat | HNSW |
|---------------|---------|------|
| Build time | Faster | Slower |
| Query speed | Fast | Faster |
| Memory usage | Lower | Higher |
| Recall accuracy | Good with tuning | Better out of box |
| Update performance | Requires rebuilding | Supports incremental |

For this exercise, you test both index types and measure the trade-offs firsthand.

## Complete the Azure resource deployment

In this section you return to the deployment script to configure the Microsoft Entra administrator and retrieve the connection information for the PostgreSQL server.

1. When the **Create PostgreSQL server with Entra authentication** operation has completed, enter **2** to launch the **Configure Microsoft Entra administrator** option. This sets your Azure account as the database administrator.

1. When the previous operation completes, enter **3** to launch the **Check deployment status** option. This verifies the server is ready.

1. Enter **4** to launch the **Retrieve connection info and access token** option. This creates a file with the necessary environment variables.

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

    >**Note:** Keep the terminal open. If you close it and create a new terminal, you might need to run the command to load the environment variables again.

    >**Note:** The access token expires after approximately one hour. If you need to reconnect later, run the script again and select option **4** to generate a new token, then export the variables again.

## Create the database schema and test data

In this section you connect to the PostgreSQL server and create a table with product data and vector embeddings for testing.

1. Run the following command to connect to the server using the environment variables. The **PGPASSWORD** environment variable is automatically used for authentication.

    **Bash**
    ```bash
    psql "host=$DB_HOST port=5432 dbname=$DB_NAME user=$DB_USER sslmode=require"
    ```

    **PowerShell**
    ```powershell
    psql "host=$env:DB_HOST port=5432 dbname=$env:DB_NAME user=$env:DB_USER sslmode=require"
    ```

1. Run the following command to enable the pgvector extension.

    ```sql
    CREATE EXTENSION IF NOT EXISTS vector;
    ```

1. Run the following command to create the products table with a vector column. The `vector(384)` data type stores 384-dimensional embeddings, a common size for sentence embedding models.

    ```sql
    CREATE TABLE products (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        category_id INTEGER NOT NULL,
        price NUMERIC(10,2) NOT NULL,
        in_stock BOOLEAN DEFAULT true,
        embedding vector(384)
    );
    ```

1. Run the following command to generate test data with random embeddings. This creates 100,000 products with random 384-dimensional vectors.

    ```sql
    INSERT INTO products (name, category_id, price, in_stock, embedding)
    SELECT
        'Product ' || i,
        (random() * 20)::int + 1,
        (random() * 1000)::numeric(10,2),
        random() > 0.1,
        ('[' || array_to_string(ARRAY(
            SELECT (random() * 2 - 1)::float4
            FROM generate_series(1, 384)
        ), ',') || ']')::vector
    FROM generate_series(1, 100000) AS i;
    ```

1. Run the following command to verify the data was created. You should see 100,000 rows.

    ```sql
    SELECT COUNT(*) FROM products;
    ```

1. Run the following command to create a query vector for consistent testing. This temporary table stores a random embedding you use throughout the exercise.

    ```sql
    CREATE TEMP TABLE query_vectors AS
    SELECT ('[' || array_to_string(ARRAY(
        SELECT (random() * 2 - 1)::float4
        FROM generate_series(1, 384)
    ), ',') || ']')::vector AS embedding;
    ```

## Analyze baseline performance

In this section you measure vector search performance without any indexes to establish a baseline.

1. Run the following command to execute a vector similarity query and capture the execution plan.

    ```sql
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;
    ```

1. Examine the output. You should see a **Seq Scan** in the plan, indicating PostgreSQL is scanning all 100,000 rows. Note the **Execution Time** value at the bottom.

1. Run the query two more times to get consistent measurements. The first run may be slower due to cold caches. Record the average execution time as your baseline.

## Create and compare IVFFlat and HNSW indexes

In this section you create both index types and compare their performance.

### Create an IVFFlat index

1. Run the following command to create an IVFFlat index. For 100,000 rows, 100 lists is a reasonable starting point (using the `rows / 1000` guideline). Note the time taken to build the index.

    ```sql
    CREATE INDEX idx_products_embedding_ivfflat
    ON products USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
    ```

1. Run the following command to execute the same query with the IVFFlat index.

    ```sql
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;
    ```

1. Verify the plan shows **Index Scan using idx_products_embedding_ivfflat**. Record the execution time.

1. Run the following commands to test different probe values. Higher probes search more clusters, improving recall at the cost of speed.

    ```sql
    -- Low probes (fast, lower recall)
    SET ivfflat.probes = 1;
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;

    -- Medium probes (balanced)
    SET ivfflat.probes = 10;
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;

    -- High probes (slower, higher recall)
    SET ivfflat.probes = 50;
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;
    ```

1. Record the execution times for each probe setting.

### Create an HNSW index

1. Run the following command to drop the IVFFlat index so you can test HNSW independently.

    ```sql
    DROP INDEX idx_products_embedding_ivfflat;
    ```

1. Run the following command to create an HNSW index. Note the build time, which is typically longer than IVFFlat.

    ```sql
    CREATE INDEX idx_products_embedding_hnsw
    ON products USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
    ```

1. Run the following command to execute the query with the HNSW index.

    ```sql
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;
    ```

1. Run the following commands to test different ef_search values. Higher values improve recall but increase latency.

    ```sql
    -- Low ef_search (faster)
    SET hnsw.ef_search = 20;
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;

    -- Default ef_search
    SET hnsw.ef_search = 40;
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;

    -- High ef_search (higher recall)
    SET hnsw.ef_search = 100;
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;
    ```

1. Record the execution times for each setting.

### Compare your results

Fill in the following table with your measurements:

| Configuration | Execution time | Notes |
|---------------|----------------|-------|
| Sequential scan (no index) | | Baseline |
| IVFFlat, probes=1 | | Fastest indexed |
| IVFFlat, probes=10 | | Balanced |
| IVFFlat, probes=50 | | Higher recall |
| HNSW, ef_search=20 | | Fast |
| HNSW, ef_search=40 | | Default |
| HNSW, ef_search=100 | | Higher recall |

## Implement metadata filtering with indexes

In this section you test queries that combine vector similarity with metadata filters.

1. Run the following command to create a B-tree index on the category column.

    ```sql
    CREATE INDEX idx_products_category ON products (category_id);
    ```

1. Run the following command to execute a filtered vector search.

    ```sql
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    WHERE category_id = 5
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;
    ```

1. Examine the plan to see how PostgreSQL combines the filters. You may see a **Bitmap And** operation or the planner may filter first and then sort.

1. Run the following command to test with a more selective filter.

    ```sql
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    WHERE category_id = 5 AND price BETWEEN 100 AND 200
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;
    ```

1. Run the following command to create a composite index for the filter combination.

    ```sql
    CREATE INDEX idx_products_category_price ON products (category_id, price);
    ```

1. Re-run the previous query and compare the execution plan.

## Configure PgBouncer connection pooling

In this section you enable and configure PgBouncer for connection pooling. PgBouncer reduces connection overhead for applications that frequently open and close database connections.

1. Open a new terminal in VS Code. Keep the psql session open in the original terminal.

1. Run the following command to load the environment variables in the new terminal.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

1. Run the following command to enable PgBouncer. Replace **\<rg-name>** with your resource group name and **\<server-name>** with the server name from your deployment (shown in the deployment script menu).

    ```azurecli
    az postgres flexible-server parameter set \
        --resource-group <rg-name> \
        --server-name <server-name> \
        --name pgbouncer.enabled \
        --value true
    ```

1. Run the following command to configure transaction pooling mode, which is recommended for most workloads.

    ```azurecli
    az postgres flexible-server parameter set \
        --resource-group <rg-name> \
        --server-name <server-name> \
        --name pgbouncer.default_pool_mode \
        --value transaction
    ```

1. Run the following command to set the pool size.

    ```azurecli
    az postgres flexible-server parameter set \
        --resource-group <rg-name> \
        --server-name <server-name> \
        --name pgbouncer.default_pool_size \
        --value 50
    ```

1. Run the following command to connect through PgBouncer on port 6432.

    **Bash**
    ```bash
    psql "host=$DB_HOST port=6432 dbname=$DB_NAME user=$DB_USER sslmode=require"
    ```

    **PowerShell**
    ```powershell
    psql "host=$env:DB_HOST port=6432 dbname=$env:DB_NAME user=$env:DB_USER sslmode=require"
    ```

1. Run a test query to verify PgBouncer is working.

    ```sql
    SELECT COUNT(*) FROM products;
    ```

1. Enter `exit` to close the PgBouncer psql session.

## Monitor performance with Azure Monitor

In this section you review the metrics generated during your testing using the Azure portal.

1. Open a browser and navigate to the [Azure portal](https://portal.azure.com).

1. Navigate to your Azure Database for PostgreSQL resource.

1. Select **Monitoring** > **Metrics** from the left menu.

1. Add the following metrics to your view:
    - CPU percent
    - Memory percent
    - Active connections
    - Storage IO percent

1. Set the time range to cover your testing period.

1. Observe how different operations affected resource utilization:
    - Index creation shows CPU spikes
    - Query execution shows brief CPU activity
    - Memory utilization increases when indexes are loaded

## Summary

In this exercise, you:

- Deployed an Azure Database for PostgreSQL Flexible Server with Microsoft Entra authentication
- Created a test dataset with 100,000 vector embeddings
- Established baseline performance for vector queries without indexes
- Created and compared IVFFlat and HNSW indexes
- Tuned index parameters (**probes** and **ef_search**) to balance accuracy and speed
- Implemented metadata filtering with B-tree indexes
- Configured PgBouncer for connection pooling
- Monitored performance metrics in Azure Monitor

These techniques enable you to optimize Azure Database for PostgreSQL for production vector search workloads.

# Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues during this exercise, try these steps:

**psql connection fails**
- Ensure the *.env* file was created by running the deployment script option **4**
- Ensure you ran **source .env** (Bash) or **. .\.env.ps1** (PowerShell) to load environment variables
- The access token expires after approximately one hour; run the deployment script option **4** again to generate a new token
- Verify the server is ready by running the deployment script option **3**

**Access denied or authentication errors**
- Ensure the Microsoft Entra administrator was configured by running the deployment script option **2**
- Verify **PGPASSWORD** is set correctly in your terminal session
- Ensure you're using the correct **DB_USER** value (your Azure account email)

**Index build takes too long or fails**
- HNSW indexes take longer to build than IVFFlat; allow 1-2 minutes for 100,000 vectors
- If the build times out, check CPU and memory metrics in Azure Monitor
- Consider reducing the dataset size for testing

**PgBouncer connection fails**
- Ensure PgBouncer is enabled by checking deployment script option **3**
- Use port **6432** instead of **5432** for PgBouncer connections
- PgBouncer requires General Purpose or Memory Optimized tier (not Burstable)
