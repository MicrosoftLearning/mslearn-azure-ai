"""
Setup script for creating the Cosmos DB container with vector search policies.
This script configures the vector embedding policy and indexing policy required
for vector similarity search using the VectorDistance function.
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
            "COSMOS_ENDPOINT and COSMOS_DATABASE environment variables must be set"
        )

    credential = DefaultAzureCredential()
    client = CosmosClient(endpoint, credential=credential)
    database = client.get_database_client(database_name)

    return database


# BEGIN CREATE VECTOR CONTAINER FUNCTION
def create_vector_container():
    """
    Create a container with vector embedding and indexing policies.

    The vector embedding policy defines:
    - path: JSON path where vector embeddings are stored
    - dataType: Data type for vector components (float32)
    - distanceFunction: Similarity metric (cosine: 0=identical, 2=opposite)
    - dimensions: Number of dimensions in each vector (256)

    The indexing policy includes:
    - Standard indexing for all paths except embeddings
    - DiskANN vector index for efficient similarity search
    """
    database = get_database()
    container_name = os.environ.get("COSMOS_CONTAINER", "vectors")

    # Define the vector embedding policy
    # This tells Cosmos DB how to handle vector data at the /embedding path
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

    # Define the indexing policy with vector index
    # - DiskANN provides efficient approximate nearest neighbor search
    # - Exclude /embedding/* from standard indexing (vectors use their own index)
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

    # Create the container with vector policies
    # partition_key determines how data is distributed across physical partitions
    container = database.create_container_if_not_exists(
        id=container_name,
        partition_key=PartitionKey(path="/documentId"),
        indexing_policy=indexing_policy,
        vector_embedding_policy=vector_embedding_policy
    )

    return container
# END CREATE VECTOR CONTAINER FUNCTION


def main():
    """Main function to create the vector container."""
    print("Creating vector container with embedding policies...")
    print()

    try:
        container = create_vector_container()
        container_name = os.environ.get("COSMOS_CONTAINER", "vectors")

        print(f"✓ Container created: {container_name}")
        print()
        print("Vector embedding policy configured:")
        print("  - Path: /embedding")
        print("  - Data type: float32")
        print("  - Distance function: cosine")
        print("  - Dimensions: 256")
        print()
        print("Indexing policy configured:")
        print("  - Vector index type: DiskANN")
        print("  - Embedding path excluded from standard indexing")
        print()
        print("Container is ready for vector search operations.")

    except Exception as e:
        print(f"Error creating container: {e}")
        raise


if __name__ == "__main__":
    main()
