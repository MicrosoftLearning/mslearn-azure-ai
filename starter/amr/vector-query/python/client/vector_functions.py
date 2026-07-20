"""
Vector storage and search helpers for Azure Managed Redis.

This module contains the student-editable sections used by the Flask app:
- connect to Redis with Microsoft Entra ID
- create the RediSearch vector index
- store product embeddings and metadata
- execute vector similarity searches
"""
import json
import os
from typing import Any

import numpy as np
import redis
from redis.commands.search.field import TextField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from redis_entraid.cred_provider import create_from_default_azure_credential

VECTOR_DIM = 8
VECTOR_INDEX_NAME = "idx:products"


# BEGIN CONNECTION CODE SECTION
def get_client() -> redis.Redis:
    """Create a Redis client for Azure Managed Redis using Microsoft Entra ID."""
    redis_host = os.environ.get("REDIS_HOST")

    if not redis_host:
        raise ValueError("REDIS_HOST environment variable must be set")

    credential_provider = create_from_default_azure_credential(
        ("https://redis.azure.com/.default",),
    )

    return redis.Redis(
        host=redis_host,
        port=10000,
        ssl=True,
        decode_responses=False,
        credential_provider=credential_provider,
        socket_timeout=30,
        socket_connect_timeout=30,
    )
# END CONNECTION CODE SECTION


class VectorManager:
    """Coordinates product storage and vector search operations."""

    def __init__(self):
        self.r = get_client()
        self.r.ping()
        self._create_vector_index()

    # BEGIN CREATE VECTOR INDEX CODE SECTION
    def _create_vector_index(self):
        """Create a RediSearch index for product semantic search."""
        try:
            schema = (
                TextField("name"),
                TextField("category"),
                TextField("product_id"),
                VectorField(
                    "embedding",
                    "HNSW",
                    {
                        "TYPE": "FLOAT32",
                        "DIM": VECTOR_DIM,
                        "DISTANCE_METRIC": "COSINE",
                    },
                ),
            )

            definition = IndexDefinition(
                prefix=["product:"],
                index_type=IndexType.HASH,
            )

            self.r.ft(VECTOR_INDEX_NAME).create_index(
                fields=schema,
                definition=definition,
            )
        except redis.ResponseError as e:
            if "already exists" not in str(e):
                raise Exception(f"Error creating vector index: {e}")
        except Exception as e:
            raise Exception(f"Error creating vector index: {e}")
    # END CREATE VECTOR INDEX CODE SECTION

    # BEGIN STORE PRODUCT CODE SECTION
    def store_product(
        self,
        vector_key: str,
        vector: list[float],
        metadata: dict[str, str] | None = None,
    ) -> tuple[bool, str]:
        """Store or update a product hash containing embedding and metadata."""
        try:
            embedding = np.array(vector, dtype=np.float32)
            data: dict[str, Any] = {"embedding": embedding.tobytes()}

            if metadata:
                for key, value in metadata.items():
                    data[key] = str(value)

            result = self.r.hset(vector_key, mapping=data)
            if result > 0:
                return True, f"Product stored successfully under key '{vector_key}'"
            return True, f"Product updated successfully under key '{vector_key}'"
        except Exception as e:
            return False, f"Error storing product: {e}"
    # END STORE PRODUCT CODE SECTION

    def retrieve_product(self, vector_key: str) -> tuple[bool, dict[str, Any] | str]:
        """Retrieve a product and decode its embedding for display and queries."""
        try:
            record = self.r.hgetall(vector_key)
            if not record:
                return False, f"Key '{vector_key}' does not exist"

            embedding_bytes = record.get(b"embedding") or record.get("embedding")
            vector = np.frombuffer(embedding_bytes, dtype=np.float32).tolist() if embedding_bytes else []

            def decode_field(field_name: str) -> str:
                value = record.get(field_name.encode()) or record.get(field_name)
                if isinstance(value, bytes):
                    return value.decode()
                return value if value else ""

            return True, {
                "key": vector_key,
                "vector": vector,
                "product_id": decode_field("product_id"),
                "name": decode_field("name"),
                "category": decode_field("category"),
            }
        except Exception as e:
            return False, f"Error retrieving product: {e}"

    # BEGIN SEARCH SIMILAR PRODUCTS CODE SECTION
    def search_similar_products(
        self,
        query_vector: list[float],
        top_k: int = 3,
    ) -> tuple[bool, list[dict[str, Any]] | str]:
        """Run a KNN vector query against product embeddings."""
        try:
            query_bytes = np.array(query_vector, dtype=np.float32).tobytes()

            knn_query = (
                Query(f"*=>[KNN {top_k} @embedding $query_vec AS score]")
                .return_fields("name", "category", "product_id", "score")
                .sort_by("score")
                .dialect(2)
            )

            results = self.r.ft(VECTOR_INDEX_NAME).search(
                knn_query,
                query_params={"query_vec": query_bytes},
            )

            if results.total == 0:
                return False, "No products found in Redis. Load sample products first."

            similarities: list[dict[str, Any]] = []
            for doc in results.docs:
                similarities.append(
                    {
                        "key": doc.id,
                        "similarity": float(doc.score),
                        "product_id": doc.product_id.decode() if isinstance(doc.product_id, bytes) else doc.product_id,
                        "name": doc.name.decode() if isinstance(doc.name, bytes) else doc.name,
                        "category": doc.category.decode() if isinstance(doc.category, bytes) else doc.category,
                    }
                )

            return True, similarities
        except Exception as e:
            return False, f"Error searching products: {e}"
    # END SEARCH SIMILAR PRODUCTS CODE SECTION

    def remove_product(self, vector_key: str) -> tuple[bool, str]:
        """Remove one product by key."""
        try:
            result = self.r.delete(vector_key)
            if result == 1:
                return True, f"Product '{vector_key}' removed"
            return False, f"Product '{vector_key}' does not exist"
        except Exception as e:
            return False, f"Error removing product: {e}"

    def list_all_products(self) -> tuple[bool, list[str] | str]:
        """List all product keys in sorted order."""
        try:
            product_keys = self.r.keys("product:*")
            if not product_keys:
                return False, "No products found"

            decoded = [k.decode() if isinstance(k, bytes) else k for k in product_keys]
            decoded.sort()
            return True, decoded
        except Exception as e:
            return False, f"Error listing products: {e}"

    def load_sample_products(self) -> tuple[bool, str]:
        """Load sample products from the exercise sample_data.json file."""
        try:
            sample_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "sample_data.json")
            )

            with open(sample_path, "r", encoding="utf-8") as f:
                sample_products = json.load(f)

            count = 0
            for item in sample_products:
                embedding = np.array(item["embedding"], dtype=np.float32)
                data: dict[str, Any] = {"embedding": embedding.tobytes()}

                for key, value in item.items():
                    if key not in ["key", "embedding"]:
                        data[key] = str(value)

                self.r.hset(item["key"], mapping=data)
                count += 1

            return True, f"{count} sample products loaded successfully"
        except FileNotFoundError:
            return False, "Error: sample_data.json file not found"
        except Exception as e:
            return False, f"Error loading sample products: {e}"
