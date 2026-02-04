"""
Query executor for running custom SQL queries against Cosmos DB.
Allows students to execute ad-hoc queries and see results.
"""
from rag_functions import get_container


def execute_query(sql_query: str, enable_cross_partition: bool = True) -> dict:
    """
    Execute a SQL query against the Cosmos DB container.

    Args:
        sql_query: The SQL query string to execute
        enable_cross_partition: Whether to enable cross-partition queries

    Returns:
        A dict with 'success', 'results', 'count', and 'error' keys
    """
    # Basic validation - only allow SELECT queries
    query_upper = sql_query.strip().upper()
    if not query_upper.startswith("SELECT"):
        return {
            "success": False,
            "results": [],
            "count": 0,
            "error": "Only SELECT queries are supported"
        }

    try:
        container = get_container()

        items = container.query_items(
            query=sql_query,
            enable_cross_partition_query=enable_cross_partition
        )

        # Convert iterator to list
        results = list(items)

        return {
            "success": True,
            "results": results,
            "count": len(results),
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "results": [],
            "count": 0,
            "error": str(e)
        }


def get_sample_queries() -> list:
    """Return a list of sample queries for the UI."""
    return [
        {
            "name": "All chunks (limit 10)",
            "query": "SELECT c.id, c.documentId, c.content, c.metadata FROM c OFFSET 0 LIMIT 10"
        },
        {
            "name": "Chunks by document ID",
            "query": "SELECT c.id, c.chunkIndex, c.content FROM c WHERE c.documentId = 'doc-azure-overview' ORDER BY c.chunkIndex"
        },
        {
            "name": "Search by category",
            "query": "SELECT c.documentId, c.id, c.content, c.metadata.category FROM c WHERE c.metadata.category = 'cloud-services'"
        },
        {
            "name": "Count chunks by document",
            "query": "SELECT c.documentId, COUNT(1) as chunkCount FROM c GROUP BY c.documentId"
        },
        {
            "name": "Search by tag",
            "query": "SELECT c.documentId, c.id, c.content, c.metadata.tags FROM c WHERE ARRAY_CONTAINS(c.metadata.tags, 'compute')"
        },
        {
            "name": "Chunks with embeddings",
            "query": "SELECT c.id, c.documentId, ARRAY_LENGTH(c.embedding) as embeddingSize FROM c WHERE ARRAY_LENGTH(c.embedding) > 0"
        }
    ]
