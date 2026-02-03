In this exercise, you build a semantic search application using Azure Cosmos DB for NoSQL vector search. You create a container with vector policies, generate and store embeddings, execute similarity queries, and combine vector search with metadata filters. This hands-on practice reinforces the vector search patterns covered in this module, demonstrating how AI applications perform semantic search over document data.

## Create Azure resources

Before implementing vector search, you need an Azure Cosmos DB account with the vector search feature enabled and an Azure OpenAI resource for generating embeddings.

1. Open a terminal and sign in to Azure:

    ```azurecli
    az login
    ```

1. Create a resource group for your resources:

    ```azurecli
    az group create \
        --name rg-vector-search-lab \
        --location eastus
    ```

1. Create an Azure Cosmos DB account with vector search capability. Replace `<unique-account-name>` with a globally unique name:

    ```azurecli
    az cosmosdb create \
        --name <unique-account-name> \
        --resource-group rg-vector-search-lab \
        --default-consistency-level Session \
        --capabilities EnableNoSQLVectorSearch
    ```

    Account creation takes several minutes. The `EnableNoSQLVectorSearch` capability enables the vector indexing and search feature.

1. Create a database within the account:

    ```azurecli
    az cosmosdb sql database create \
        --account-name <unique-account-name> \
        --resource-group rg-vector-search-lab \
        --name knowledgebase
    ```

1. Create an Azure OpenAI resource. Replace `<unique-openai-name>` with a unique name:

    ```azurecli
    az cognitiveservices account create \
        --name <unique-openai-name> \
        --resource-group rg-vector-search-lab \
        --location eastus \
        --kind OpenAI \
        --sku S0
    ```

1. Deploy the text-embedding-ada-002 model:

    ```azurecli
    az cognitiveservices account deployment create \
        --name <unique-openai-name> \
        --resource-group rg-vector-search-lab \
        --deployment-name text-embedding-ada-002 \
        --model-name text-embedding-ada-002 \
        --model-version "2" \
        --model-format OpenAI \
        --sku-capacity 10 \
        --sku-name Standard
    ```

## Set up the development environment

With the Azure resources created, prepare your local environment to work with both Cosmos DB and Azure OpenAI.

1. Create a new directory for your project and navigate to it:

    ```bash
    mkdir vector-search-lab && cd vector-search-lab
    ```

1. Create a Python virtual environment and activate it:

    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

1. Install the required packages:

    ```bash
    pip install azure-cosmos openai
    ```

1. Retrieve your Cosmos DB endpoint and key:

    ```azurecli
    az cosmosdb keys list \
        --name <unique-account-name> \
        --resource-group rg-vector-search-lab \
        --type keys
    ```

    Note the `primaryMasterKey` value.

1. Retrieve your Azure OpenAI endpoint and key:

    ```azurecli
    az cognitiveservices account show \
        --name <unique-openai-name> \
        --resource-group rg-vector-search-lab \
        --query "properties.endpoint" -o tsv

    az cognitiveservices account keys list \
        --name <unique-openai-name> \
        --resource-group rg-vector-search-lab
    ```

## Create a container with vector policies

Create a Python script that sets up a container with the proper vector embedding policy and indexing configuration.

1. Create a file named `setup_container.py` with the following content:

    ```python
    from azure.cosmos import CosmosClient, PartitionKey

    # Replace with your values
    COSMOS_ENDPOINT = "https://<unique-account-name>.documents.azure.com:443/"
    COSMOS_KEY = "<your-cosmos-key>"

    # Initialize the client
    client = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)
    database = client.get_database_client("knowledgebase")

    # Vector embedding policy - defines how vectors are stored
    vector_embedding_policy = {
        "vectorEmbeddings": [
            {
                "path": "/embedding",
                "dataType": "float32",
                "distanceFunction": "cosine",
                "dimensions": 1536
            }
        ]
    }

    # Indexing policy with vector index
    indexing_policy = {
        "indexingMode": "consistent",
        "automatic": True,
        "includedPaths": [
            {"path": "/*"}
        ],
        "excludedPaths": [
            {"path": "/\"_etag\"/?"},
            {"path": "/embedding/*"}
        ],
        "vectorIndexes": [
            {"path": "/embedding", "type": "diskANN"}
        ]
    }

    # Create container with vector support
    print("Creating container with vector policies...")
    container = database.create_container_if_not_exists(
        id="articles",
        partition_key=PartitionKey(path="/category"),
        indexing_policy=indexing_policy,
        vector_embedding_policy=vector_embedding_policy
    )

    print(f"Container 'articles' created successfully!")
    print(f"Vector policy: cosine distance, 1536 dimensions")
    print(f"Vector index type: diskANN")
    ```

1. Run the script:

    ```bash
    python setup_container.py
    ```

## Generate embeddings and store documents

Create a script that generates embeddings from text content and stores documents with their vectors.

1. Create a file named `populate_data.py`:

    ```python
    from azure.cosmos import CosmosClient
    from openai import AzureOpenAI

    # Cosmos DB configuration
    COSMOS_ENDPOINT = "https://<unique-account-name>.documents.azure.com:443/"
    COSMOS_KEY = "<your-cosmos-key>"

    # Azure OpenAI configuration
    OPENAI_ENDPOINT = "https://<unique-openai-name>.openai.azure.com/"
    OPENAI_KEY = "<your-openai-key>"

    # Initialize clients
    cosmos_client = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)
    container = cosmos_client.get_database_client("knowledgebase").get_container_client("articles")

    openai_client = AzureOpenAI(
        api_key=OPENAI_KEY,
        api_version="2024-02-01",
        azure_endpoint=OPENAI_ENDPOINT
    )

    # Sample knowledge base articles
    articles = [
        {
            "id": "art-001",
            "category": "networking",
            "title": "Troubleshooting wireless network connections",
            "content": "This guide covers common WiFi connectivity issues including connection drops, slow speeds, and authentication failures. Start by checking your router's power and internet connection. Verify that WiFi is enabled on your device and you're connecting to the correct network name."
        },
        {
            "id": "art-002",
            "category": "networking",
            "title": "Configuring router security settings",
            "content": "Secure your home network by changing default passwords, enabling WPA3 encryption, and hiding your network SSID. Regular firmware updates protect against vulnerabilities. Consider setting up a guest network for visitors."
        },
        {
            "id": "art-003",
            "category": "software",
            "title": "Resolving application crash errors",
            "content": "When applications crash unexpectedly, check for available updates first. Clear the application cache and temporary files. If crashes persist, try reinstalling the application or running it in compatibility mode."
        },
        {
            "id": "art-004",
            "category": "software",
            "title": "Managing system memory and performance",
            "content": "Improve system performance by closing unnecessary background applications. Use Task Manager to identify memory-intensive processes. Consider adding more RAM if your system consistently runs at high memory usage."
        },
        {
            "id": "art-005",
            "category": "hardware",
            "title": "Diagnosing printer connectivity problems",
            "content": "If your printer isn't responding, verify it's powered on and connected to the same network as your computer. Check for paper jams and low ink levels. Reinstall printer drivers if connection issues persist."
        }
    ]

    def generate_embedding(text):
        """Generate embedding using Azure OpenAI."""
        response = openai_client.embeddings.create(
            input=text,
            model="text-embedding-ada-002"
        )
        return response.data[0].embedding

    # Insert articles with embeddings
    print("Generating embeddings and inserting articles...\n")
    for article in articles:
        # Combine title and content for embedding
        text_for_embedding = f"{article['title']} {article['content']}"

        # Generate embedding
        embedding = generate_embedding(text_for_embedding)
        article["embedding"] = embedding

        # Insert document
        container.upsert_item(article)
        print(f"Inserted: {article['title']}")
        print(f"  Category: {article['category']}")
        print(f"  Embedding dimensions: {len(embedding)}\n")

    print("Data population complete!")
    ```

1. Run the script:

    ```bash
    python populate_data.py
    ```

    Observe that each article is processed through the embedding model and stored with its vector.

## Execute vector similarity searches

Create a script that performs semantic searches using the `VectorDistance` function.

1. Create a file named `vector_search.py`:

    ```python
    from azure.cosmos import CosmosClient
    from openai import AzureOpenAI

    # Configuration (replace with your values)
    COSMOS_ENDPOINT = "https://<unique-account-name>.documents.azure.com:443/"
    COSMOS_KEY = "<your-cosmos-key>"
    OPENAI_ENDPOINT = "https://<unique-openai-name>.openai.azure.com/"
    OPENAI_KEY = "<your-openai-key>"

    # Initialize clients
    cosmos_client = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)
    container = cosmos_client.get_database_client("knowledgebase").get_container_client("articles")

    openai_client = AzureOpenAI(
        api_key=OPENAI_KEY,
        api_version="2024-02-01",
        azure_endpoint=OPENAI_ENDPOINT
    )

    def search(query_text, top_n=3):
        """Perform semantic search for the given query."""
        # Generate query embedding
        response = openai_client.embeddings.create(
            input=query_text,
            model="text-embedding-ada-002"
        )
        query_embedding = response.data[0].embedding

        # Execute vector search
        query = """
            SELECT TOP @topN
                c.id,
                c.title,
                c.category,
                c.content,
                VectorDistance(c.embedding, @queryVector) AS SimilarityScore
            FROM c
            ORDER BY VectorDistance(c.embedding, @queryVector)
        """

        results = container.query_items(
            query=query,
            parameters=[
                {"name": "@topN", "value": top_n},
                {"name": "@queryVector", "value": query_embedding}
            ],
            enable_cross_partition_query=True
        )

        return list(results)

    # Test searches
    print("=== Vector Similarity Search Demo ===\n")

    # Search 1: WiFi problems (matches networking articles)
    print("Query: 'My internet connection keeps dropping'")
    print("-" * 50)
    results = search("My internet connection keeps dropping")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['title']}")
        print(f"   Category: {result['category']}")
        print(f"   Similarity Score: {result['SimilarityScore']:.4f}")
        print()

    # Search 2: Memory issues (matches software article)
    print("Query: 'Computer running slowly and freezing'")
    print("-" * 50)
    results = search("Computer running slowly and freezing")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['title']}")
        print(f"   Category: {result['category']}")
        print(f"   Similarity Score: {result['SimilarityScore']:.4f}")
        print()

    # Search 3: Printer issues
    print("Query: 'Cannot print documents'")
    print("-" * 50)
    results = search("Cannot print documents")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['title']}")
        print(f"   Category: {result['category']}")
        print(f"   Similarity Score: {result['SimilarityScore']:.4f}")
        print()
    ```

1. Run the script:

    ```bash
    python vector_search.py
    ```

    Notice how the semantic search finds relevant articles even when the query uses different words than the article titles.

## Combine vector search with metadata filters

Create a script that demonstrates filtering vector search results by category.

1. Create a file named `filtered_search.py`:

    ```python
    from azure.cosmos import CosmosClient
    from openai import AzureOpenAI

    # Configuration (replace with your values)
    COSMOS_ENDPOINT = "https://<unique-account-name>.documents.azure.com:443/"
    COSMOS_KEY = "<your-cosmos-key>"
    OPENAI_ENDPOINT = "https://<unique-openai-name>.openai.azure.com/"
    OPENAI_KEY = "<your-openai-key>"

    # Initialize clients
    cosmos_client = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)
    container = cosmos_client.get_database_client("knowledgebase").get_container_client("articles")

    openai_client = AzureOpenAI(
        api_key=OPENAI_KEY,
        api_version="2024-02-01",
        azure_endpoint=OPENAI_ENDPOINT
    )

    def search_with_filter(query_text, category=None, top_n=3):
        """Perform semantic search with optional category filter."""
        # Generate query embedding
        response = openai_client.embeddings.create(
            input=query_text,
            model="text-embedding-ada-002"
        )
        query_embedding = response.data[0].embedding

        # Build query with optional filter
        if category:
            query = """
                SELECT TOP @topN
                    c.id,
                    c.title,
                    c.category,
                    VectorDistance(c.embedding, @queryVector) AS SimilarityScore
                FROM c
                WHERE c.category = @category
                ORDER BY VectorDistance(c.embedding, @queryVector)
            """
            parameters = [
                {"name": "@topN", "value": top_n},
                {"name": "@queryVector", "value": query_embedding},
                {"name": "@category", "value": category}
            ]
            # Use partition key for single-partition query
            results = container.query_items(
                query=query,
                parameters=parameters,
                partition_key=category
            )
        else:
            query = """
                SELECT TOP @topN
                    c.id,
                    c.title,
                    c.category,
                    VectorDistance(c.embedding, @queryVector) AS SimilarityScore
                FROM c
                ORDER BY VectorDistance(c.embedding, @queryVector)
            """
            parameters = [
                {"name": "@topN", "value": top_n},
                {"name": "@queryVector", "value": query_embedding}
            ]
            results = container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            )

        return list(results)

    # Compare filtered vs unfiltered search
    query = "connection problems"

    print("=== Filtered Search Demo ===\n")
    print(f"Query: '{query}'\n")

    # Unfiltered search
    print("Without filter (all categories):")
    print("-" * 40)
    results = search_with_filter(query)
    for result in results:
        print(f"  {result['title']} [{result['category']}] - {result['SimilarityScore']:.4f}")

    print()

    # Filtered to networking only
    print("With filter (networking only):")
    print("-" * 40)
    results = search_with_filter(query, category="networking")
    for result in results:
        print(f"  {result['title']} [{result['category']}] - {result['SimilarityScore']:.4f}")

    print()

    # Filtered to software only
    print("With filter (software only):")
    print("-" * 40)
    results = search_with_filter(query, category="software")
    for result in results:
        print(f"  {result['title']} [{result['category']}] - {result['SimilarityScore']:.4f}")
    ```

1. Run the script:

    ```bash
    python filtered_search.py
    ```

    Observe how the category filter narrows results to specific document types while maintaining semantic relevance within that category.

## Clean up resources

When finished with the exercise, delete the resource group to avoid ongoing charges:

```azurecli
az group delete --name rg-vector-search-lab --yes --no-wait
```

## Summary

In this exercise, you created an Azure Cosmos DB for NoSQL account with vector search enabled and an Azure OpenAI resource for embedding generation. You configured a container with vector embedding policies and a DiskANN index. You populated the container with documents and their embeddings, then executed vector similarity searches using the `VectorDistance` function. You also combined vector search with metadata filters to narrow results by category. These hands-on skills enable you to build AI applications that perform semantic search over document data in Azure Cosmos DB.
