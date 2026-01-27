In this exercise, you apply the optimization techniques covered in this module to improve vector search performance on Azure Database for PostgreSQL. You analyze baseline performance, create and compare vector indexes, tune parameters, and configure connection pooling.

## Prerequisites

To complete this exercise, you need:

- An Azure subscription with permissions to create resources
- Azure Database for PostgreSQL with the pgvector extension enabled
- A client tool for connecting to PostgreSQL (psql, Azure Data Studio, or similar)
- Sample data with vector embeddings (instructions provided to generate test data)

## Set up the test environment

Start by creating a table with product data and vector embeddings for testing.

1. Connect to your Azure Database for PostgreSQL instance:

    ```bash
    psql "host=yourserver.postgres.database.azure.com port=5432 dbname=postgres user=youradmin password=yourpassword sslmode=require"
    ```

1. Enable the pgvector extension if not already enabled:

    ```sql
    CREATE EXTENSION IF NOT EXISTS vector;
    ```

1. Create the products table with a vector column:

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

1. Generate test data with random embeddings. This script creates 500,000 products with random 384-dimensional embeddings:

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
    FROM generate_series(1, 500000) AS i;
    ```

    This operation takes several minutes. Monitor progress by checking the row count:

    ```sql
    SELECT COUNT(*) FROM products;
    ```

## Analyze baseline performance

Before creating indexes, measure the performance of sequential scan queries to establish a baseline.

1. Generate a random query vector:

    ```sql
    -- Store a query vector for consistent testing
    CREATE TEMP TABLE query_vectors AS
    SELECT ('[' || array_to_string(ARRAY(
        SELECT (random() * 2 - 1)::float4
        FROM generate_series(1, 384)
    ), ',') || ']')::vector AS embedding;
    ```

1. Run a baseline vector similarity query and capture the execution plan:

    ```sql
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;
    ```

1. Record the execution time from the output. You should see a **Seq Scan** in the plan, indicating PostgreSQL is scanning all rows. Note the total execution time, which is likely several seconds.

1. Run the query multiple times to get consistent measurements. The first run may be slower due to cold caches.

## Create and compare IVFFlat and HNSW indexes

Create both index types and compare their performance characteristics.

### Create an IVFFlat index

1. Create an IVFFlat index with an appropriate number of lists for 500,000 rows:

    ```sql
    CREATE INDEX idx_products_embedding_ivfflat
    ON products USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 500);
    ```

1. Note the time taken to build the index. For 500,000 vectors, this typically takes one to three minutes.

1. Run the same query and examine the new execution plan:

    ```sql
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;
    ```

1. Verify the plan shows **Index Scan using idx_products_embedding_ivfflat**. Record the execution time.

1. Test different probe values to see the accuracy-speed trade-off:

    ```sql
    -- Low probes (fast, lower recall)
    SET ivfflat.probes = 1;
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;

    -- Medium probes
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

### Create an HNSW index

1. Drop the IVFFlat index to test HNSW independently:

    ```sql
    DROP INDEX idx_products_embedding_ivfflat;
    ```

1. Create an HNSW index:

    ```sql
    CREATE INDEX idx_products_embedding_hnsw
    ON products USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
    ```

1. Note the build time. HNSW indexes take longer to build than IVFFlat, typically three to ten minutes for this dataset.

1. Run the query with the HNSW index:

    ```sql
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;
    ```

1. Test different ef_search values:

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

### Compare results

Create a comparison of your measurements:

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

Test the performance of queries that combine vector similarity with metadata filters.

1. Create a B-tree index on the category column:

    ```sql
    CREATE INDEX idx_products_category ON products (category_id);
    ```

1. Run a filtered vector search:

    ```sql
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    WHERE category_id = 5
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;
    ```

1. Examine the plan to see how PostgreSQL combines the category filter with the vector index. You may see a **Bitmap And** operation combining both indexes, or the planner may choose to filter first and then sort.

1. Test with a more selective filter:

    ```sql
    EXPLAIN ANALYZE
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    WHERE category_id = 5 AND price BETWEEN 100 AND 200
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;
    ```

1. Create a composite index for the filter combination:

    ```sql
    CREATE INDEX idx_products_category_price ON products (category_id, price);
    ```

1. Re-run the query and compare execution plans.

## Configure connection pooling with PgBouncer

Enable and configure PgBouncer for your Azure Database for PostgreSQL instance.

1. Enable PgBouncer using Azure CLI:

    ```azurecli
    az postgres flexible-server parameter set \
        --resource-group yourResourceGroup \
        --server-name yourserver \
        --name pgbouncer.enabled \
        --value true
    ```

1. Configure transaction pooling mode:

    ```azurecli
    az postgres flexible-server parameter set \
        --resource-group yourResourceGroup \
        --server-name yourserver \
        --name pgbouncer.default_pool_mode \
        --value transaction
    ```

1. Set an appropriate pool size:

    ```azurecli
    az postgres flexible-server parameter set \
        --resource-group yourResourceGroup \
        --server-name yourserver \
        --name pgbouncer.default_pool_size \
        --value 50
    ```

1. Connect through PgBouncer (port 6432) and verify connectivity:

    ```bash
    psql "host=yourserver.postgres.database.azure.com port=6432 dbname=postgres user=youradmin password=yourpassword sslmode=require"
    ```

1. Run a test query to confirm PgBouncer is working:

    ```sql
    SELECT id, name, embedding <=> (SELECT embedding FROM query_vectors) AS distance
    FROM products
    ORDER BY embedding <=> (SELECT embedding FROM query_vectors)
    LIMIT 10;
    ```

## Monitor performance using Azure Monitor

Review the metrics generated during your testing.

1. In the Azure portal, navigate to your Azure Database for PostgreSQL.

1. Select **Monitoring** > **Metrics** from the left menu.

1. Add the following metrics to your view:
    - CPU percent
    - Memory percent
    - Active connections
    - Storage IO percent

1. Set the time range to cover your testing period.

1. Observe how different operations affected resource utilization:
    - Index creation should show CPU spikes
    - Query execution shows brief CPU activity
    - Memory utilization should increase when indexes are loaded

1. Consider setting up alerts for:
    - CPU percent > 80% for 5 minutes
    - Memory percent > 90% for 5 minutes
    - Active connections approaching server limits

## Clean up resources

If you created resources specifically for this exercise and no longer need them:

1. Drop the test table:

    ```sql
    DROP TABLE IF EXISTS products;
    DROP TABLE IF EXISTS query_vectors;
    ```

1. If you created a new database server for testing, delete it through the Azure portal or CLI to avoid ongoing charges.

## Summary

In this exercise, you:

- Established baseline performance for vector queries without indexes
- Created and compared IVFFlat and HNSW indexes
- Tuned index parameters (`probes` and `ef_search`) to balance accuracy and speed
- Implemented metadata filtering with appropriate B-tree indexes
- Configured PgBouncer for connection pooling
- Monitored performance metrics in Azure Monitor

These techniques enable you to optimize Azure Database for PostgreSQL for production vector search workloads.
