"""
Vector search functions for storing and retrieving documents with embeddings from Cosmos DB.
These functions serve as the interface between the Flask app and Cosmos DB vector search.
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


# BEGIN STORE VECTOR DOCUMENT FUNCTION


# END STORE VECTOR DOCUMENT FUNCTION


# BEGIN VECTOR SIMILARITY SEARCH FUNCTION


# END VECTOR SIMILARITY SEARCH FUNCTION


# BEGIN FILTERED VECTOR SEARCH FUNCTION


# END FILTERED VECTOR SEARCH FUNCTION


def get_all_categories() -> list:
    """Get a list of unique categories from the container."""
    try:
        container = get_container()
        query = "SELECT DISTINCT c.metadata.category FROM c WHERE IS_DEFINED(c.metadata.category)"
        items = container.query_items(
            query=query,
            enable_cross_partition_query=True
        )
        return sorted([item["category"] for item in items if item.get("category")])
    except Exception:
        return []


def get_all_document_ids() -> list:
    """Get a list of unique document IDs from the container."""
    try:
        container = get_container()
        query = "SELECT DISTINCT c.documentId FROM c"
        items = container.query_items(
            query=query,
            enable_cross_partition_query=True
        )
        return sorted([item["documentId"] for item in items])
    except Exception:
        return []
