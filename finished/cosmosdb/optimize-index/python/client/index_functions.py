"""
Index comparison functions for vector search performance testing in Cosmos DB.
These functions demonstrate how different vector indexing strategies affect
query performance and RU consumption.
"""
import os
import time
from datetime import datetime
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential


# Container names for the three indexing strategies
CONTAINER_FLAT = "vectors-flat"
CONTAINER_QUANTIZED = "vectors-quantized"
CONTAINER_DISKANN = "vectors-diskann"


def get_database():
    """Get a reference to the Cosmos DB database using Entra ID authentication."""
    endpoint = os.environ.get("COSMOS_ENDPOINT")
    database_name = os.environ.get("COSMOS_DATABASE")

    if not endpoint or not database_name:
        raise ValueError(
            "COSMOS_ENDPOINT and COSMOS_DATABASE environment variables must be set"
        )

    credential = DefaultAzureCredential()
    client = CosmosClient(endpoint, credential=credential)
    database = client.get_database_client(database_name)

    return database


def get_container(container_name: str):
    """Get a reference to a specific Cosmos DB container."""
    database = get_database()
    return database.get_container_client(container_name)


def get_all_containers():
    """Get references to all three index strategy containers."""
    return {
        "flat": get_container(CONTAINER_FLAT),
        "quantizedFlat": get_container(CONTAINER_QUANTIZED),
        "diskANN": get_container(CONTAINER_DISKANN)
    }


# BEGIN STORE VECTOR DOCUMENT FUNCTION
def store_vector_document(
    container_name: str,
    document_id: str,
    chunk_id: str,
    content: str,
    embedding: list,
    metadata: dict = None
) -> dict:
    """
    Store a document with its vector embedding in a specific container.

    Args:
        container_name: Name of the container (vectors-flat, vectors-quantized, vectors-diskann)
        document_id: Unique identifier for the source document (partition key)
        chunk_id: Unique identifier for this chunk within the document
        content: Text content of the document
        embedding: 256-dimensional vector embedding
        metadata: Optional metadata dictionary

    Returns:
        Dictionary with chunk_id, document_id, and ru_charge
    """
    container = get_container(container_name)

    # Build the document structure with embedding for vector search
    # The 'id' field is required by Cosmos DB and must be unique within the partition
    # The 'documentId' field is our partition key for efficient retrieval
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
    response = container.upsert_item(body=document)

    # Request Units (RUs) measure the cost of database operations
    ru_charge = response.get_response_headers()['x-ms-request-charge']

    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "ru_charge": float(ru_charge)
    }
# END STORE VECTOR DOCUMENT FUNCTION


def store_to_all_containers(
    document_id: str,
    chunk_id: str,
    content: str,
    embedding: list,
    metadata: dict = None
) -> dict:
    """Store a document to all three containers for comparison testing."""
    results = {}
    for container_name in [CONTAINER_FLAT, CONTAINER_QUANTIZED, CONTAINER_DISKANN]:
        result = store_vector_document(
            container_name, document_id, chunk_id, content, embedding, metadata
        )
        results[container_name] = result
    return results


# BEGIN VECTOR SIMILARITY SEARCH FUNCTION
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
# END VECTOR SIMILARITY SEARCH FUNCTION


# BEGIN COMPARE INDEX PERFORMANCE FUNCTION
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
# END COMPARE INDEX PERFORMANCE FUNCTION


# BEGIN FILTERED VECTOR SEARCH FUNCTION
def filtered_vector_search(
    container_name: str,
    query_embedding: list,
    category: str = None,
    top_n: int = 5
) -> dict:
    """
    Combine vector similarity search with metadata filtering.

    This hybrid approach applies a metadata filter before ranking results
    by vector similarity. Filtering reduces the search space and can
    improve performance for targeted queries.

    Args:
        container_name: Name of the container to search
        query_embedding: 256-dimensional query vector
        category: Optional category filter
        top_n: Number of results to return

    Returns:
        Dictionary containing results, ru_charge, and execution_time_ms
    """
    container = get_container(container_name)

    start_time = time.time()

    # Build WHERE clause for metadata filtering
    where_clause = ""
    parameters = [
        {"name": "@topN", "value": top_n},
        {"name": "@queryVector", "value": query_embedding}
    ]

    if category:
        where_clause = "WHERE c.metadata.category = @category"
        parameters.append({"name": "@category", "value": category})

    # Filtered vector search: apply filter, then rank by similarity
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

    items = list(container.query_items(
        query=query,
        parameters=parameters,
        enable_cross_partition_query=True
    ))

    end_time = time.time()
    execution_time_ms = (end_time - start_time) * 1000

    ru_charge = 0.0
    try:
        ru_charge = float(container.client_connection.last_response_headers.get(
            'x-ms-request-charge', 0
        ))
    except Exception:
        pass

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
# END FILTERED VECTOR SEARCH FUNCTION


def compare_filtered_performance(
    query_embedding: list,
    category: str = None,
    top_n: int = 5
) -> dict:
    """Run filtered vector search against all containers and compare."""
    comparison = {}

    for index_type, container_name in [
        ("flat", CONTAINER_FLAT),
        ("quantizedFlat", CONTAINER_QUANTIZED),
        ("diskANN", CONTAINER_DISKANN)
    ]:
        try:
            result = filtered_vector_search(
                container_name, query_embedding, category, top_n
            )
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


def get_all_categories() -> list:
    """Get unique categories from the diskANN container (reference container)."""
    try:
        container = get_container(CONTAINER_DISKANN)
        query = "SELECT DISTINCT c.metadata.category FROM c WHERE IS_DEFINED(c.metadata.category)"
        items = container.query_items(
            query=query,
            enable_cross_partition_query=True
        )
        return sorted([item["category"] for item in items if item.get("category")])
    except Exception:
        return []


def get_document_count(container_name: str) -> int:
    """Get the number of documents in a container."""
    try:
        container = get_container(container_name)
        query = "SELECT VALUE COUNT(1) FROM c"
        items = list(container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        return items[0] if items else 0
    except Exception:
        return 0


def get_all_document_counts() -> dict:
    """Get document counts for all containers."""
    return {
        "flat": get_document_count(CONTAINER_FLAT),
        "quantizedFlat": get_document_count(CONTAINER_QUANTIZED),
        "diskANN": get_document_count(CONTAINER_DISKANN)
    }
