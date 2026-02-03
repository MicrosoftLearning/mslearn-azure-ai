In this exercise, you create an Azure Cosmos DB for NoSQL account, database, and container. You then use the Python SDK to perform data operations and execute queries. This hands-on practice reinforces the SDK patterns and query techniques covered in this module, demonstrating how AI applications interact with Cosmos DB for document storage and retrieval.

## Create Azure Cosmos DB resources

Before connecting with the SDK, you need an Azure Cosmos DB account with a database and container. You can create these resources using the Azure portal, Azure CLI, or infrastructure-as-code tools like Bicep. The following steps use the Azure CLI for a streamlined setup.

1. Open a terminal and sign in to Azure:

    ```azurecli
    az login
    ```

1. Create a resource group for your Cosmos DB resources:

    ```azurecli
    az group create \
        --name rg-cosmos-lab \
        --location eastus
    ```

1. Create an Azure Cosmos DB account. Replace `<unique-account-name>` with a globally unique name:

    ```azurecli
    az cosmosdb create \
        --name <unique-account-name> \
        --resource-group rg-cosmos-lab \
        --default-consistency-level Session
    ```

    Account creation takes several minutes. Note the `documentEndpoint` value in the output—you need this for SDK connections.

1. Create a database within the account:

    ```azurecli
    az cosmosdb sql database create \
        --account-name <unique-account-name> \
        --resource-group rg-cosmos-lab \
        --name productcatalog
    ```

1. Create a container with a partition key:

    ```azurecli
    az cosmosdb sql container create \
        --account-name <unique-account-name> \
        --resource-group rg-cosmos-lab \
        --database-name productcatalog \
        --name products \
        --partition-key-path "/categoryId" \
        --throughput 400
    ```

## Set up the development environment

With the Azure resources created, prepare your local environment to connect using the Python SDK.

1. Create a new directory for your project and navigate to it:

    ```bash
    mkdir cosmos-sdk-lab && cd cosmos-sdk-lab
    ```

1. Create a Python virtual environment and activate it:

    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

1. Install the required packages:

    ```bash
    pip install azure-cosmos azure-identity
    ```

1. Retrieve your account endpoint and key. For this exercise, you use the account key for authentication. In production, prefer Microsoft Entra ID authentication:

    ```azurecli
    az cosmosdb keys list \
        --name <unique-account-name> \
        --resource-group rg-cosmos-lab \
        --type keys
    ```

    Note the `primaryMasterKey` value.

## Connect and insert sample data

Create a Python script that initializes the SDK client and populates the container with sample product data.

1. Create a file named `populate_data.py` with the following content:

    ```python
    from azure.cosmos import CosmosClient, PartitionKey

    # Replace with your values
    ENDPOINT = "https://<unique-account-name>.documents.azure.com:443/"
    KEY = "<your-primary-key>"

    # Initialize the client
    client = CosmosClient(ENDPOINT, credential=KEY)
    database = client.get_database_client("productcatalog")
    container = database.get_container_client("products")

    # Sample product data
    products = [
        {
            "id": "product-001",
            "categoryId": "electronics",
            "name": "Smart Speaker",
            "price": 99.99,
            "quantity": 150,
            "features": ["voice-control", "wifi", "bluetooth"]
        },
        {
            "id": "product-002",
            "categoryId": "electronics",
            "name": "Wireless Headphones",
            "price": 199.99,
            "quantity": 75,
            "features": ["noise-canceling", "bluetooth", "30hr-battery"]
        },
        {
            "id": "product-003",
            "categoryId": "electronics",
            "name": "4K Monitor",
            "price": 449.99,
            "quantity": 30,
            "features": ["4k-resolution", "hdr", "usb-c"]
        },
        {
            "id": "product-004",
            "categoryId": "appliances",
            "name": "Coffee Maker",
            "price": 79.99,
            "quantity": 200,
            "features": ["programmable", "12-cup", "auto-shutoff"]
        },
        {
            "id": "product-005",
            "categoryId": "appliances",
            "name": "Air Purifier",
            "price": 249.99,
            "quantity": 45,
            "features": ["hepa-filter", "quiet-mode", "smart-sensor"]
        }
    ]

    # Insert products using upsert
    print("Inserting products...")
    for product in products:
        response = container.upsert_item(body=product)
        ru_charge = response.get_response_headers()['x-ms-request-charge']
        print(f"  Inserted {product['name']} - {ru_charge} RUs")

    print("\nData population complete!")
    ```

1. Run the script:

    ```bash
    python populate_data.py
    ```

    Observe the RU charge for each insert operation.

## Perform point reads

Create a script to demonstrate efficient point reads for retrieving specific items.

1. Create a file named `point_reads.py`:

    ```python
    from azure.cosmos import CosmosClient
    from azure.cosmos import exceptions

    ENDPOINT = "https://<unique-account-name>.documents.azure.com:443/"
    KEY = "<your-primary-key>"

    client = CosmosClient(ENDPOINT, credential=KEY)
    database = client.get_database_client("productcatalog")
    container = database.get_container_client("products")

    # Point read - requires id and partition key
    print("Performing point read...")
    try:
        item = container.read_item(
            item="product-002",
            partition_key="electronics"
        )
        print(f"Product: {item['name']}")
        print(f"Price: ${item['price']}")
        print(f"Features: {', '.join(item['features'])}")
    except exceptions.CosmosResourceNotFoundError:
        print("Item not found")

    # Attempting to read non-existent item
    print("\nAttempting to read non-existent item...")
    try:
        item = container.read_item(
            item="product-999",
            partition_key="electronics"
        )
    except exceptions.CosmosResourceNotFoundError:
        print("Item not found - expected behavior")
    ```

1. Run the script:

    ```bash
    python point_reads.py
    ```

## Execute queries

Create a script that demonstrates various query patterns including filtering, projection, and aggregation.

1. Create a file named `run_queries.py`:

    ```python
    from azure.cosmos import CosmosClient

    ENDPOINT = "https://<unique-account-name>.documents.azure.com:443/"
    KEY = "<your-primary-key>"

    client = CosmosClient(ENDPOINT, credential=KEY)
    database = client.get_database_client("productcatalog")
    container = database.get_container_client("products")

    # Query 1: Single-partition query with projection
    print("=== Electronics under $200 ===")
    query = """
        SELECT p.name, p.price
        FROM products p
        WHERE p.categoryId = @category AND p.price < @maxPrice
        ORDER BY p.price
    """

    items = container.query_items(
        query=query,
        parameters=[
            {"name": "@category", "value": "electronics"},
            {"name": "@maxPrice", "value": 200.00}
        ],
        partition_key="electronics"
    )

    for item in items:
        print(f"  {item['name']}: ${item['price']}")

    # Query 2: Cross-partition query
    print("\n=== All products with quantity < 50 ===")
    query = """
        SELECT p.name, p.categoryId, p.quantity
        FROM products p
        WHERE p.quantity < @threshold
    """

    items = container.query_items(
        query=query,
        parameters=[{"name": "@threshold", "value": 50}],
        enable_cross_partition_query=True
    )

    for item in items:
        print(f"  {item['name']} ({item['categoryId']}): {item['quantity']} units")

    # Query 3: Aggregate query
    print("\n=== Electronics category statistics ===")
    query = """
        SELECT
            COUNT(1) as productCount,
            AVG(p.price) as avgPrice,
            MIN(p.price) as minPrice,
            MAX(p.price) as maxPrice
        FROM products p
        WHERE p.categoryId = @category
    """

    items = list(container.query_items(
        query=query,
        parameters=[{"name": "@category", "value": "electronics"}],
        partition_key="electronics"
    ))

    stats = items[0]
    print(f"  Product count: {stats['productCount']}")
    print(f"  Average price: ${stats['avgPrice']:.2f}")
    print(f"  Price range: ${stats['minPrice']} - ${stats['maxPrice']}")

    # Query 4: Array query
    print("\n=== Products with bluetooth feature ===")
    query = """
        SELECT p.name, p.features
        FROM products p
        WHERE ARRAY_CONTAINS(p.features, @feature)
    """

    items = container.query_items(
        query=query,
        parameters=[{"name": "@feature", "value": "bluetooth"}],
        enable_cross_partition_query=True
    )

    for item in items:
        print(f"  {item['name']}: {item['features']}")
    ```

1. Run the script:

    ```bash
    python run_queries.py
    ```

## Monitor RU consumption

Create a script that tracks RU consumption across different operations to understand cost patterns.

1. Create a file named `monitor_rus.py`:

    ```python
    from azure.cosmos import CosmosClient

    ENDPOINT = "https://<unique-account-name>.documents.azure.com:443/"
    KEY = "<your-primary-key>"

    client = CosmosClient(ENDPOINT, credential=KEY)
    database = client.get_database_client("productcatalog")
    container = database.get_container_client("products")

    print("=== RU Consumption Comparison ===\n")

    # Point read
    item = container.read_item(item="product-001", partition_key="electronics")
    # Note: Point reads don't return RU in the same way; use Azure Monitor for accurate tracking
    print(f"Point read completed for: {item['name']}")

    # Single-partition query
    query = "SELECT * FROM products p WHERE p.categoryId = @category"
    items = container.query_items(
        query=query,
        parameters=[{"name": "@category", "value": "electronics"}],
        partition_key="electronics"
    )

    count = 0
    for item in items:
        count += 1
    print(f"Single-partition query returned {count} items")

    # Cross-partition query
    query = "SELECT * FROM products p"
    items = container.query_items(
        query=query,
        enable_cross_partition_query=True
    )

    count = 0
    for item in items:
        count += 1
    print(f"Cross-partition query returned {count} items")

    print("\nCheck Azure Monitor metrics for detailed RU consumption.")
    ```

1. Run the script:

    ```bash
    python monitor_rus.py
    ```

## Clean up resources

When finished with the exercise, delete the resource group to avoid ongoing charges:

```azurecli
az group delete --name rg-cosmos-lab --yes --no-wait
```

## Summary

In this exercise, you created an Azure Cosmos DB for NoSQL account, database, and container using the Azure CLI. You used the Python SDK to insert sample data with upsert operations, perform efficient point reads for specific items, and execute various queries including filtered queries, cross-partition queries, aggregations, and array queries. These hands-on skills enable you to build AI applications that efficiently store and retrieve document data from Azure Cosmos DB.
