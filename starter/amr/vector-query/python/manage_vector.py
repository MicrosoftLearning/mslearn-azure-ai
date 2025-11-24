import os
import json
import redis
import numpy as np
from dotenv import load_dotenv
from redis.commands.search.field import TextField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query

# Load environment variables from .env file
load_dotenv()

class VectorManager:
    """Handles all product storage, retrieval, and semantic search operations with Redis embeddings"""

    # BEGIN INITIALIZATION AND CONNECTION CODE SECTION



    # END INITIALIZATION AND CONNECTION CODE SECTION

    # BEGIN CREATE VECTOR INDEX CODE SECTION



    # END CREATE VECTOR INDEX CODE SECTION

    # BEGIN STORE PRODUCT CODE SECTION



    # END STORE PRODUCT CODE SECTION

    def retrieve_product(self, vector_key: str) -> tuple[bool, dict | str]:
        """Retrieve a product and its embedding from Redis"""
        try:
            # Retrieve all fields for the product using hgetall()
            retrieved_data = self.r.hgetall(vector_key)

            if retrieved_data:
                # Convert binary embedding back to list for display
                embedding_bytes = retrieved_data.get(b"embedding") or retrieved_data.get("embedding")
                if embedding_bytes:
                    embedding_array = np.frombuffer(embedding_bytes, dtype=np.float32)
                    vector = embedding_array.tolist()
                else:
                    vector = []

                # Decode bytes to strings for text fields
                def get_field(field_name):
                    val = retrieved_data.get(field_name.encode()) or retrieved_data.get(field_name)
                    if isinstance(val, bytes):
                        return val.decode()
                    return val if val else ""

                result = {
                    "key": vector_key,
                    "vector": vector,
                    "product_id": get_field("product_id"),
                    "name": get_field("name"),
                    "category": get_field("category")
                }

                return True, result
            else:
                return False, f"Key '{vector_key}' does not exist"

        except Exception as e:
            return False, f"Error retrieving product: {e}"

    # BEGIN SEARCH SIMILAR PRODUCTS CODE SECTION



    # END SEARCH SIMILAR PRODUCTS CODE SECTION

    def delete_product(self, vector_key: str) -> tuple[bool, str]:
        """Delete a product from Redis using del() method"""
        try:
            # Delete the key using Redis del() command
            result = self.r.delete(vector_key)
            if result == 1:
                return True, f"Product '{vector_key}' deleted successfully"
            else:
                return False, f"Product '{vector_key}' does not exist"
        except Exception as e:
            return False, f"Error deleting product: {e}"

    def clear_all_products(self) -> tuple[bool, str]:
        """Delete all products from Redis"""
        try:
            # Retrieve all product keys and delete them in bulk
            product_keys = self.r.keys("product:*")
            if product_keys:
                self.r.delete(*product_keys)  # Delete all keys at once
                return True, f"All {len(product_keys)} products deleted successfully"
            else:
                return False, "No products to delete"
        except Exception as e:
            return False, f"Error clearing products: {e}"

    def list_all_products(self) -> tuple[bool, list | str]:
        """List all product keys available in Redis"""
        try:
            product_keys = self.r.keys("product:*")
            if product_keys:
                # Convert bytes to strings if needed
                keys_list = [k.decode() if isinstance(k, bytes) else k for k in product_keys]
                keys_list.sort()  # Sort for consistent display
                return True, keys_list
            else:
                return False, "No products found"
        except Exception as e:
            return False, f"Error listing products: {e}"

    def load_sample_products(self) -> tuple[bool, str]:
        """Load sample product data into Redis from sample_data.json using binary embedding storage"""
        try:
            # Read sample data from JSON file
            with open("sample_data.json", "r") as f:
                sample_products = json.load(f)

            count = 0
            for item in sample_products:
                # Convert embedding to binary bytes for efficient storage
                embedding = np.array(item["embedding"], dtype=np.float32)
                data = {"embedding": embedding.tobytes()}

                # Add product metadata (all fields except key and embedding)
                for key, value in item.items():
                    if key not in ["key", "embedding"]:
                        data[key] = str(value)

                # Store each product in Redis
                self.r.hset(item["key"], mapping=data)
                count += 1

            return True, f"{count} sample products loaded successfully"

        except FileNotFoundError:
            return False, "Error: sample_data.json file not found"
        except Exception as e:
            return False, f"Error loading sample products: {e}"
