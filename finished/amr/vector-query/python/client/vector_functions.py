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



# END CONNECTION CODE SECTION


class VectorManager:
    """Coordinates product storage and vector search operations."""

    def __init__(self):
        self.r = get_client()
        self.r.ping()
        self._create_vector_index()

    # BEGIN CREATE VECTOR INDEX CODE SECTION



    # END CREATE VECTOR INDEX CODE SECTION

    # BEGIN STORE PRODUCT CODE SECTION



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
