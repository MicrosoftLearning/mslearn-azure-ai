"""
Setup script to create three Cosmos DB containers with different vector indexing strategies.

This script creates containers configured for comparing vector index performance:
- vectors-flat: Flat index (exact search, higher RU for large datasets)
- vectors-quantized: Quantized flat index (compressed vectors, memory efficient)
- vectors-diskann: DiskANN index (approximate nearest neighbor, optimal for production)

Run this script after the Cosmos DB account is created and environment variables are set.
"""
import os
from azure.cosmos import CosmosClient, PartitionKey
from azure.identity import DefaultAzureCredential


def get_database():
    """Get a reference to the Cosmos DB database using Entra ID authentication."""
    endpoint = os.environ.get("COSMOS_ENDPOINT")
    database_name = os.environ.get("COSMOS_DATABASE")

    if not endpoint or not database_name:
        raise ValueError(
            "COSMOS_ENDPOINT and COSMOS_DATABASE environment variables must be set. "
            "Run 'source .env' (Bash) or '. .\\.env.ps1' (PowerShell) first."
        )

    credential = DefaultAzureCredential()
    client = CosmosClient(endpoint, credential=credential)
    database = client.get_database_client(database_name)

    return database


# BEGIN CREATE FLAT CONTAINER FUNCTION
def create_flat_container():
    """
    Create a container with a flat vector index.

    The flat index performs exact nearest neighbor search by comparing
    the query vector against every vector in the dataset. This provides
    100% recall but has O(n) complexity, making it suitable for:
    - Small datasets (< 10,000 vectors)
    - Scenarios requiring exact results
    - Baseline performance comparisons
    """
    database = get_database()
    container_name = "vectors-flat"

    # Vector embedding policy defines how Cosmos DB handles vector data
    vector_embedding_policy = {
        "vectorEmbeddings": [
            {
                "path": "/embedding",
                "dataType": "float32",
                "distanceFunction": "cosine",
                "dimensions": 256
            }
        ]
    }

    # Flat index: exact search, compares query against all vectors
    # Higher RU cost for large datasets but guaranteed best results
    indexing_policy = {
        "indexingMode": "consistent",
        "automatic": True,
        "includedPaths": [
            {"path": "/*"}
        ],
        "excludedPaths": [
            {"path": "/embedding/*"}
        ],
        "vectorIndexes": [
            {
                "path": "/embedding",
                "type": "flat"
            }
        ]
    }

    print(f"Creating container '{container_name}' with flat vector index...")

    container = database.create_container_if_not_exists(
        id=container_name,
        partition_key=PartitionKey(path="/documentId"),
        indexing_policy=indexing_policy,
        vector_embedding_policy=vector_embedding_policy
    )

    print(f"✓ Container '{container_name}' created with flat index")
    print("  - Index type: flat (exact nearest neighbor)")
    print("  - Best for: small datasets, exact results required")

    return container
# END CREATE FLAT CONTAINER FUNCTION


# BEGIN CREATE QUANTIZED CONTAINER FUNCTION
def create_quantized_container():
    """
    Create a container with a quantized flat vector index.

    The quantizedFlat index compresses vectors using scalar quantization,
    reducing memory usage while maintaining good search quality. It still
    performs exact search but on compressed representations. Suitable for:
    - Medium datasets (10,000 - 100,000 vectors)
    - Memory-constrained environments
    - Balance between performance and accuracy
    """
    database = get_database()
    container_name = "vectors-quantized"

    vector_embedding_policy = {
        "vectorEmbeddings": [
            {
                "path": "/embedding",
                "dataType": "float32",
                "distanceFunction": "cosine",
                "dimensions": 256
            }
        ]
    }

    # QuantizedFlat index: compressed vectors for memory efficiency
    # Lower memory footprint with slight accuracy trade-off
    indexing_policy = {
        "indexingMode": "consistent",
        "automatic": True,
        "includedPaths": [
            {"path": "/*"}
        ],
        "excludedPaths": [
            {"path": "/embedding/*"}
        ],
        "vectorIndexes": [
            {
                "path": "/embedding",
                "type": "quantizedFlat"
            }
        ]
    }

    print(f"Creating container '{container_name}' with quantizedFlat vector index...")

    container = database.create_container_if_not_exists(
        id=container_name,
        partition_key=PartitionKey(path="/documentId"),
        indexing_policy=indexing_policy,
        vector_embedding_policy=vector_embedding_policy
    )

    print(f"✓ Container '{container_name}' created with quantizedFlat index")
    print("  - Index type: quantizedFlat (compressed exact search)")
    print("  - Best for: medium datasets, memory efficiency")

    return container
# END CREATE QUANTIZED CONTAINER FUNCTION


# BEGIN CREATE DISKANN CONTAINER FUNCTION
def create_diskann_container():
    """
    Create a container with a DiskANN vector index.

    DiskANN (Disk-based Approximate Nearest Neighbor) uses a graph-based
    algorithm for efficient similarity search. It provides excellent
    performance with high recall rates (typically 95%+). Recommended for:
    - Large datasets (> 100,000 vectors)
    - Production workloads
    - Low-latency requirements
    """
    database = get_database()
    container_name = "vectors-diskann"

    vector_embedding_policy = {
        "vectorEmbeddings": [
            {
                "path": "/embedding",
                "dataType": "float32",
                "distanceFunction": "cosine",
                "dimensions": 256
            }
        ]
    }

    # DiskANN index: approximate nearest neighbor with graph-based search
    # Best performance for large datasets, slight accuracy trade-off
    indexing_policy = {
        "indexingMode": "consistent",
        "automatic": True,
        "includedPaths": [
            {"path": "/*"}
        ],
        "excludedPaths": [
            {"path": "/embedding/*"}
        ],
        "vectorIndexes": [
            {
                "path": "/embedding",
                "type": "diskANN"
            }
        ]
    }

    print(f"Creating container '{container_name}' with diskANN vector index...")

    container = database.create_container_if_not_exists(
        id=container_name,
        partition_key=PartitionKey(path="/documentId"),
        indexing_policy=indexing_policy,
        vector_embedding_policy=vector_embedding_policy
    )

    print(f"✓ Container '{container_name}' created with diskANN index")
    print("  - Index type: diskANN (approximate nearest neighbor)")
    print("  - Best for: large datasets, production workloads")

    return container
# END CREATE DISKANN CONTAINER FUNCTION


def main():
    """Create all three containers with different vector indexing strategies."""
    print("=" * 60)
    print("Creating Cosmos DB containers for vector index comparison")
    print("=" * 60)
    print()

    try:
        # Create each container with its specific indexing strategy
        create_flat_container()
        print()

        create_quantized_container()
        print()

        create_diskann_container()
        print()

        print("=" * 60)
        print("All containers created successfully!")
        print()
        print("Vector Index Comparison Summary:")
        print("-" * 60)
        print("| Container          | Index Type    | Use Case              |")
        print("|--------------------|--------------|-----------------------|")
        print("| vectors-flat       | flat         | Small datasets, exact |")
        print("| vectors-quantized  | quantizedFlat| Medium, memory efficient|")
        print("| vectors-diskann    | diskANN      | Large, production     |")
        print("-" * 60)
        print()
        print("Next: Run the Flask app to load data and compare performance.")
        print("=" * 60)

    except Exception as e:
        print(f"Error creating containers: {e}")
        raise


if __name__ == "__main__":
    main()
