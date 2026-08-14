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



# END CREATE FLAT CONTAINER FUNCTION


# BEGIN CREATE QUANTIZED CONTAINER FUNCTION



# END CREATE QUANTIZED CONTAINER FUNCTION


# BEGIN CREATE DISKANN CONTAINER FUNCTION



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
