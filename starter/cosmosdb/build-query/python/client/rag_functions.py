"""
RAG document functions for storing and retrieving document chunks from Cosmos DB.
These functions serve as the interface between the Flask app and Cosmos DB.
"""
import os
from datetime import datetime
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential


def get_container():
    """Get a reference to the Cosmos DB container using Entra ID authentication."""
    endpoint = os.environ.get("COSMOS_ENDPOINT")
    database_name = os.environ.get("COSMOS_DATABASE")
    container_name = os.environ.get("COSMOS_CONTAINER")

    if not endpoint or not database_name or not container_name:
        raise ValueError(
            "COSMOS_ENDPOINT, COSMOS_DATABASE, and COSMOS_CONTAINER "
            "environment variables must be set"
        )

    credential = DefaultAzureCredential()
    client = CosmosClient(endpoint, credential=credential)
    database = client.get_database_client(database_name)
    container = database.get_container_client(container_name)

    return container


# BEGIN STORE DOCUMENT CHUNK FUNCTION
def store_document_chunk(
    document_id: str,
    chunk_id: str,
    content: str,
    metadata: dict = None,
    embedding: list = None
) -> dict:
    """Store a document chunk with metadata and optional embedding placeholder."""
    container = get_container()

    # Build the document structure following our RAG schema
    # The 'id' field is required by Cosmos DB and must be unique within the partition
    # The 'documentId' field is our partition key - chunks from the same source document
    # are stored together for efficient retrieval
    chunk = {
        "id": chunk_id,
        "documentId": document_id,
        "content": content,
        "metadata": metadata or {},
        "embedding": embedding or [],  # Placeholder for vector embeddings
        "createdAt": datetime.utcnow().isoformat(),
        "chunkIndex": metadata.get("chunkIndex", 0) if metadata else 0
    }

    # upsert_item inserts if new, updates if exists (based on id + partition key)
    # This is idempotent - safe to call multiple times with the same data
    response = container.upsert_item(body=chunk)

    # Request Units (RUs) measure the cost of database operations in Cosmos DB
    # Tracking RU consumption helps optimize queries and estimate costs
    ru_charge = response.get_response_headers()['x-ms-request-charge']

    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "ru_charge": float(ru_charge)
    }
# END STORE DOCUMENT CHUNK FUNCTION


# BEGIN GET CHUNKS BY DOCUMENT FUNCTION
def get_chunks_by_document(document_id: str, limit: int = 100) -> list:
    """Retrieve all chunks for a specific document, ordered by chunk index."""
    container = get_container()

    # SQL query using parameterized values (@documentId, @limit) to prevent injection
    # The 'c' alias represents each document in the container
    query = """
        SELECT c.id, c.content, c.metadata, c.chunkIndex, c.createdAt
        FROM c
        WHERE c.documentId = @documentId
        ORDER BY c.chunkIndex
        OFFSET 0 LIMIT @limit
    """

    # Single-partition query: providing partition_key limits the query to one partition
    # This is more efficient than cross-partition queries because Cosmos DB only
    # needs to read from one physical partition instead of fanning out to all partitions
    items = container.query_items(
        query=query,
        parameters=[
            {"name": "@documentId", "value": document_id},
            {"name": "@limit", "value": limit}
        ],
        partition_key=document_id  # Scopes query to a single partition
    )

    # Transform Cosmos DB items into a consistent response format
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
# END GET CHUNKS BY DOCUMENT FUNCTION


# BEGIN SEARCH CHUNKS BY METADATA FUNCTION
def search_chunks_by_metadata(
    filters: dict,
    limit: int = 10
) -> list:
    """Search for chunks across documents using metadata filters."""
    container = get_container()

    # Build WHERE clauses dynamically based on provided filters
    # This allows flexible querying by any combination of metadata fields
    where_clauses = []
    parameters = []

    if "source" in filters and filters["source"]:
        where_clauses.append("c.metadata.source = @source")
        parameters.append({"name": "@source", "value": filters["source"]})

    if "category" in filters and filters["category"]:
        where_clauses.append("c.metadata.category = @category")
        parameters.append({"name": "@category", "value": filters["category"]})

    if "tags" in filters and filters["tags"]:
        # ARRAY_CONTAINS checks if a value exists within an array field
        # This is useful for searching tags, keywords, or other list-based metadata
        where_clauses.append("ARRAY_CONTAINS(c.metadata.tags, @tag)")
        parameters.append({"name": "@tag", "value": filters["tags"][0]})

    # Default to "1=1" (always true) if no filters provided
    where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
    parameters.append({"name": "@limit", "value": limit})

    query = f"""
        SELECT c.id, c.documentId, c.content, c.metadata, c.chunkIndex
        FROM c
        WHERE {where_clause}
        OFFSET 0 LIMIT @limit
    """

    # Cross-partition query: searches across ALL partitions in the container
    # Required when you don't know which partition contains the data you need
    # More expensive than single-partition queries but necessary for metadata searches
    items = container.query_items(
        query=query,
        parameters=parameters,
        enable_cross_partition_query=True  # Fan out to all partitions
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
# END SEARCH CHUNKS BY METADATA FUNCTION


# BEGIN GET CHUNK BY ID FUNCTION
def get_chunk_by_id(document_id: str, chunk_id: str) -> dict:
    """Retrieve a specific chunk using a point read (most efficient)."""
    container = get_container()

    try:
        # Point read: the most efficient Cosmos DB operation
        # By providing both the item ID and partition key, Cosmos DB can go
        # directly to the exact location of the document without any query execution
        # This results in the lowest latency and RU cost (typically 1 RU for small docs)
        item = container.read_item(
            item=chunk_id,         # The unique ID within the partition
            partition_key=document_id  # The partition where this item lives
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
        # Return None if the item doesn't exist rather than raising an exception
        # This allows the caller to handle missing items gracefully
        return None
# END GET CHUNK BY ID FUNCTION
