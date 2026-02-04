In this exercise, you design and implement an indexing strategy for a document search application. You analyze query requirements, create containers with custom indexing policies, configure composite indexes for multi-property queries, and measure the impact on RU consumption. This hands-on practice reinforces the indexing concepts covered in this module.

## Create Azure resources

Before implementing indexing strategies, you need an Azure Cosmos DB account with a database for testing different index configurations.

1. Open a terminal and sign in to Azure:

    ```azurecli
    az login
    ```

1. Create a resource group for your resources:

    ```azurecli
    az group create \
        --name rg-indexing-lab \
        --location eastus
    ```

1. Create an Azure Cosmos DB account. Replace `<unique-account-name>` with a globally unique name:

    ```azurecli
    az cosmosdb create \
        --name <unique-account-name> \
        --resource-group rg-indexing-lab \
        --default-consistency-level Session
    ```

    Account creation takes several minutes. Note the `documentEndpoint` value in the output.

1. Create a database within the account:

    ```azurecli
    az cosmosdb sql database create \
        --account-name <unique-account-name> \
        --resource-group rg-indexing-lab \
        --name documentsearch
    ```

## Set up the development environment

Prepare your local environment to work with Azure Cosmos DB using the Python SDK.

1. Create a new directory for your project and navigate to it:

    ```bash
    mkdir indexing-lab && cd indexing-lab
    ```

1. Create a Python virtual environment and activate it:

    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

1. Install the required packages:

    ```bash
    pip install azure-cosmos
    ```

1. Retrieve your Cosmos DB endpoint and key:

    ```azurecli
    az cosmosdb keys list \
        --name <unique-account-name> \
        --resource-group rg-indexing-lab \
        --type keys
    ```

    Note the `primaryMasterKey` value.

## Create a container with default indexing

First, create a container that uses the default indexing policy to establish a baseline for comparison.

1. Create a file named `setup_default_container.py`:

    ```python
    from azure.cosmos import CosmosClient, PartitionKey

    # Replace with your values
    ENDPOINT = "https://<unique-account-name>.documents.azure.com:443/"
    KEY = "<your-primary-key>"

    # Initialize the client
    client = CosmosClient(ENDPOINT, credential=KEY)
    database = client.get_database_client("documentsearch")

    # Create container with default indexing (indexes all properties)
    print("Creating container with default indexing policy...")
    container = database.create_container_if_not_exists(
        id="documents-default",
        partition_key=PartitionKey(path="/category")
    )

    # Display the default indexing policy
    container_props = container.read()
    print("\nDefault indexing policy:")
    print(f"  Indexing mode: {container_props['indexingPolicy']['indexingMode']}")
    print(f"  Included paths: {container_props['indexingPolicy']['includedPaths']}")
    print(f"  Excluded paths: {container_props['indexingPolicy']['excludedPaths']}")
    ```

1. Run the script:

    ```bash
    python setup_default_container.py
    ```

    Notice that the default policy includes `/*`, meaning all properties are indexed.

## Create a container with optimized indexing

Now create a container with a custom indexing policy that indexes only the properties used in queries.

1. Create a file named `setup_optimized_container.py`:

    ```python
    from azure.cosmos import CosmosClient, PartitionKey

    ENDPOINT = "https://<unique-account-name>.documents.azure.com:443/"
    KEY = "<your-primary-key>"

    client = CosmosClient(ENDPOINT, credential=KEY)
    database = client.get_database_client("documentsearch")

    # Custom indexing policy - index only queried properties
    indexing_policy = {
        "indexingMode": "consistent",
        "automatic": True,
        "includedPaths": [
            {"path": "/title/?"},
            {"path": "/documentType/?"},
            {"path": "/category/?"},
            {"path": "/uploadDate/?"},
            {"path": "/author/?"},
            {"path": "/tags/[]"}
        ],
        "excludedPaths": [
            {"path": "/*"}
        ],
        "compositeIndexes": [
            [
                {"path": "/documentType", "order": "ascending"},
                {"path": "/uploadDate", "order": "descending"}
            ],
            [
                {"path": "/category", "order": "ascending"},
                {"path": "/author", "order": "ascending"}
            ]
        ]
    }

    print("Creating container with optimized indexing policy...")
    container = database.create_container_if_not_exists(
        id="documents-optimized",
        partition_key=PartitionKey(path="/category"),
        indexing_policy=indexing_policy
    )

    print("\nOptimized indexing policy configured:")
    print("  - Indexed properties: title, documentType, category, uploadDate, author, tags")
    print("  - Excluded: all other properties (content, rawText, metadata)")
    print("  - Composite indexes for multi-property queries")
    ```

1. Run the script:

    ```bash
    python setup_optimized_container.py
    ```

## Populate containers with sample data

Insert sample documents into both containers to compare query performance.

1. Create a file named `populate_data.py`:

    ```python
    from azure.cosmos import CosmosClient
    import random
    from datetime import datetime, timedelta

    ENDPOINT = "https://<unique-account-name>.documents.azure.com:443/"
    KEY = "<your-primary-key>"

    client = CosmosClient(ENDPOINT, credential=KEY)
    database = client.get_database_client("documentsearch")

    container_default = database.get_container_client("documents-default")
    container_optimized = database.get_container_client("documents-optimized")

    # Sample data
    categories = ["engineering", "marketing", "finance", "legal", "hr"]
    document_types = ["report", "presentation", "spreadsheet", "policy", "memo"]
    authors = ["Alice Smith", "Bob Johnson", "Carol Williams", "David Brown", "Eve Davis"]

    documents = []
    base_date = datetime(2024, 1, 1)

    for i in range(50):
        category = random.choice(categories)
        doc = {
            "id": f"doc-{i:04d}",
            "category": category,
            "title": f"Document {i} - {category.title()} {random.choice(['Guide', 'Report', 'Summary', 'Analysis'])}",
            "documentType": random.choice(document_types),
            "author": random.choice(authors),
            "uploadDate": (base_date + timedelta(days=random.randint(0, 365))).isoformat(),
            "tags": random.sample(["important", "draft", "final", "review", "archive", "confidential"], k=random.randint(1, 3)),
            "content": "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 50,
            "rawText": "This is the raw extracted text from the document. " * 30,
            "metadata": {
                "pages": random.randint(1, 50),
                "fileSize": random.randint(10000, 5000000),
                "format": random.choice(["pdf", "docx", "xlsx", "pptx"])
            }
        }
        documents.append(doc)

    # Insert into both containers
    print("Inserting documents into default container...")
    for doc in documents:
        container_default.upsert_item(doc)
    print(f"  Inserted {len(documents)} documents")

    print("\nInserting documents into optimized container...")
    for doc in documents:
        container_optimized.upsert_item(doc)
    print(f"  Inserted {len(documents)} documents")

    print("\nData population complete!")
    ```

1. Run the script:

    ```bash
    python populate_data.py
    ```

## Compare query performance

Create a script that runs identical queries against both containers and compares RU consumption.

1. Create a file named `compare_queries.py`:

    ```python
    from azure.cosmos import CosmosClient

    ENDPOINT = "https://<unique-account-name>.documents.azure.com:443/"
    KEY = "<your-primary-key>"

    client = CosmosClient(ENDPOINT, credential=KEY)
    database = client.get_database_client("documentsearch")

    container_default = database.get_container_client("documents-default")
    container_optimized = database.get_container_client("documents-optimized")

    def run_query(container, query, parameters, description):
        """Run query and return RU consumption."""
        results = list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))

        # Get RU charge from the last response
        # Note: For accurate RU tracking, use Azure Monitor
        return len(results)

    print("=" * 60)
    print("Query Performance Comparison")
    print("=" * 60)

    # Query 1: Simple filter on indexed property
    print("\nQuery 1: Filter by documentType")
    print("-" * 40)
    query = "SELECT c.id, c.title FROM c WHERE c.documentType = @type"
    params = [{"name": "@type", "value": "report"}]

    count_default = run_query(container_default, query, params, "default")
    count_optimized = run_query(container_optimized, query, params, "optimized")
    print(f"  Default container: {count_default} results")
    print(f"  Optimized container: {count_optimized} results")

    # Query 2: Filter + ORDER BY (benefits from composite index)
    print("\nQuery 2: Filter by documentType + ORDER BY uploadDate")
    print("-" * 40)
    query = """
        SELECT c.id, c.title, c.uploadDate
        FROM c
        WHERE c.documentType = @type
        ORDER BY c.uploadDate DESC
    """
    params = [{"name": "@type", "value": "report"}]

    count_default = run_query(container_default, query, params, "default")
    count_optimized = run_query(container_optimized, query, params, "optimized")
    print(f"  Default container: {count_default} results")
    print(f"  Optimized container: {count_optimized} results")
    print("  Note: Optimized container uses composite index for this query")

    # Query 3: Multi-property filter
    print("\nQuery 3: Filter by category AND author")
    print("-" * 40)
    query = """
        SELECT c.id, c.title
        FROM c
        WHERE c.category = @category AND c.author = @author
    """
    params = [
        {"name": "@category", "value": "engineering"},
        {"name": "@author", "value": "Alice Smith"}
    ]

    count_default = run_query(container_default, query, params, "default")
    count_optimized = run_query(container_optimized, query, params, "optimized")
    print(f"  Default container: {count_default} results")
    print(f"  Optimized container: {count_optimized} results")

    # Query 4: Array contains
    print("\nQuery 4: Filter by tag (array contains)")
    print("-" * 40)
    query = "SELECT c.id, c.title, c.tags FROM c WHERE ARRAY_CONTAINS(c.tags, @tag)"
    params = [{"name": "@tag", "value": "important"}]

    count_default = run_query(container_default, query, params, "default")
    count_optimized = run_query(container_optimized, query, params, "optimized")
    print(f"  Default container: {count_default} results")
    print(f"  Optimized container: {count_optimized} results")

    print("\n" + "=" * 60)
    print("Check Azure Monitor for detailed RU consumption metrics")
    print("=" * 60)
    ```

1. Run the script:

    ```bash
    python compare_queries.py
    ```

## Test session consistency behavior

Create a script that demonstrates session consistency using session tokens.

1. Create a file named `test_consistency.py`:

    ```python
    from azure.cosmos import CosmosClient
    from datetime import datetime

    ENDPOINT = "https://<unique-account-name>.documents.azure.com:443/"
    KEY = "<your-primary-key>"

    client = CosmosClient(ENDPOINT, credential=KEY)
    database = client.get_database_client("documentsearch")
    container = database.get_container_client("documents-optimized")

    print("=" * 60)
    print("Session Consistency Demo")
    print("=" * 60)

    # Create a new document
    new_doc = {
        "id": f"doc-session-test-{datetime.now().strftime('%H%M%S')}",
        "category": "engineering",
        "title": "Newly Uploaded Document",
        "documentType": "report",
        "author": "Test User",
        "uploadDate": datetime.now().isoformat(),
        "tags": ["new", "test"],
        "content": "This document was just created to test session consistency."
    }

    print(f"\n1. Creating document: {new_doc['id']}")
    response = container.create_item(new_doc)

    # Get session token from the write operation
    # Note: In practice, extract from response headers
    print("   Document created successfully")

    # Immediately query for the document
    print("\n2. Querying for the document immediately after creation...")
    query = "SELECT * FROM c WHERE c.id = @id"
    params = [{"name": "@id", "value": new_doc["id"]}]

    results = list(container.query_items(
        query=query,
        parameters=params,
        partition_key="engineering"
    ))

    if results:
        print(f"   Found document: {results[0]['title']}")
        print("   Session consistency ensures read-your-writes!")
    else:
        print("   Document not found (unexpected with session consistency)")

    # Clean up
    print("\n3. Cleaning up test document...")
    container.delete_item(item=new_doc["id"], partition_key="engineering")
    print("   Test document deleted")

    print("\n" + "=" * 60)
    print("Session consistency guarantees that within a session,")
    print("you always see your own writes immediately.")
    print("=" * 60)
    ```

1. Run the script:

    ```bash
    python test_consistency.py
    ```

## Analyze index utilization

Create a script that retrieves query metrics to analyze index utilization.

1. Create a file named `analyze_indexes.py`:

    ```python
    from azure.cosmos import CosmosClient

    ENDPOINT = "https://<unique-account-name>.documents.azure.com:443/"
    KEY = "<your-primary-key>"

    client = CosmosClient(ENDPOINT, credential=KEY)
    database = client.get_database_client("documentsearch")
    container = database.get_container_client("documents-optimized")

    print("=" * 60)
    print("Index Utilization Analysis")
    print("=" * 60)

    # Query that uses composite index
    print("\nQuery 1: Uses composite index (documentType + uploadDate)")
    print("-" * 40)
    query = """
        SELECT c.id, c.title
        FROM c
        WHERE c.documentType = @type
        ORDER BY c.uploadDate DESC
    """

    results = container.query_items(
        query=query,
        parameters=[{"name": "@type", "value": "report"}],
        enable_cross_partition_query=True,
        populate_query_metrics=True
    )

    # Consume results to get metrics
    items = list(results)
    print(f"  Results: {len(items)} documents")

    # Query that scans (no index on content)
    print("\nQuery 2: Full scan (content not indexed)")
    print("-" * 40)
    query = "SELECT c.id, c.title FROM c WHERE CONTAINS(c.content, @text)"

    results = container.query_items(
        query=query,
        parameters=[{"name": "@text", "value": "Lorem"}],
        enable_cross_partition_query=True,
        populate_query_metrics=True
    )

    items = list(results)
    print(f"  Results: {len(items)} documents")
    print("  Note: This query performs a full scan because 'content' is excluded from indexes")

    # Query optimized by partition key
    print("\nQuery 3: Single partition query (uses partition key)")
    print("-" * 40)
    query = "SELECT c.id, c.title FROM c WHERE c.category = @category"

    results = container.query_items(
        query=query,
        parameters=[{"name": "@category", "value": "engineering"}],
        partition_key="engineering"  # Routes to single partition
    )

    items = list(results)
    print(f"  Results: {len(items)} documents")
    print("  Note: Query routes to single partition for optimal performance")

    print("\n" + "=" * 60)
    print("Tips for index optimization:")
    print("  - Index properties used in WHERE and ORDER BY clauses")
    print("  - Exclude large properties not used in queries")
    print("  - Create composite indexes for multi-property queries")
    print("  - Use partition keys to enable single-partition queries")
    print("=" * 60)
    ```

1. Run the script:

    ```bash
    python analyze_indexes.py
    ```

## Clean up resources

When finished with the exercise, delete the resource group to avoid ongoing charges:

```azurecli
az group delete --name rg-indexing-lab --yes --no-wait
```

## Summary

In this exercise, you created Azure Cosmos DB containers with both default and custom indexing policies. You compared the default "index everything" approach with a targeted policy that indexes only queried properties. You configured composite indexes to optimize multi-property filter and sort queries. You tested session consistency behavior to understand read-your-writes guarantees, and analyzed index utilization patterns to identify optimization opportunities. These hands-on skills enable you to design indexing strategies that balance query performance with cost efficiency for AI applications.
