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
# END STORE DOCUMENT CHUNK FUNCTION


# BEGIN GET CHUNKS BY DOCUMENT FUNCTION
def get_chunks_by_document(document_id: str, limit: int = 100) -> list:
    """Retrieve all chunks for a specific document, ordered by chunk index."""
    container = get_container()

    query = """
        SELECT c.id, c.content, c.metadata, c.chunkIndex, c.createdAt
        FROM c
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
# END GET CHUNKS BY DOCUMENT FUNCTION


# BEGIN SEARCH CHUNKS BY METADATA FUNCTION
def search_chunks_by_metadata(
    filters: dict,
    limit: int = 10
) -> list:
    """Search for chunks across documents using metadata filters."""
    container = get_container()

    # Build dynamic WHERE clauses based on filters
    where_clauses = []
    parameters = []

    if "source" in filters and filters["source"]:
        where_clauses.append("c.metadata.source = @source")
        parameters.append({"name": "@source", "value": filters["source"]})

    if "category" in filters and filters["category"]:
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
        FROM c
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
# END SEARCH CHUNKS BY METADATA FUNCTION


# BEGIN GET CHUNK BY ID FUNCTION
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
# END GET CHUNK BY ID FUNCTION
