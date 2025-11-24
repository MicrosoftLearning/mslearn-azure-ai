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

    def __init__(self):
        """Initialize the product manager and establish Redis connection"""
        self.r = self._connect_to_redis()
        self._create_vector_index()  # Create RediSearch index for product embeddings
        self.VECTOR_DIM = 8  # Product embedding dimensionality (matches sample_data.json)

    def _connect_to_redis(self) -> redis.Redis:
        """Establish connection to Azure Managed Redis using SSL encryption and authentication"""
        try:
            # Get connection parameters from environment variables
            redis_host = os.getenv("REDIS_HOST")
            redis_key = os.getenv("REDIS_KEY")

            # Create Redis connection with SSL and authentication
            r = redis.Redis(
                host=redis_host,
                port=10000,  # Azure Managed Redis uses port 10000
                ssl=True,  # Use SSL encryption
                decode_responses=False,  # Keep binary for embeddings - only decode text when needed
                password=redis_key,  # Authentication key
                socket_timeout=30,  # Connection timeout
                socket_connect_timeout=30,  # Socket timeout
            )

            # Test connection
            r.ping()  # Verify Redis connectivity
            return r

        except redis.ConnectionError as e:
            raise Exception(f"Connection error: {e}")
        except redis.AuthenticationError as e:
            raise Exception(f"Authentication error: {e}")
        except Exception as e:
            raise Exception(f"Unexpected error: {e}")

    def _create_vector_index(self):
        """Create a RediSearch index for product semantic search using HNSW algorithm"""
        try:
            # Define schema with embedding field for HNSW-based product similarity search
            # DIM=8 matches our sample data dimensions (in production, this would match your embedding model's output)
            schema = (
                TextField("name"),
                TextField("category"),
                TextField("product_id"),
                VectorField(
                    "embedding",
                    "HNSW",  # Hierarchical Navigable Small World - fast approximate search
                    {
                        "TYPE": "FLOAT32",           # Standard for embeddings
                        "DIM": 8,                    # Must match embedding dimensions in sample_data.json
                        "DISTANCE_METRIC": "COSINE"  # Cosine similarity for semantic search
                    }
                )
            )

            # Create index on hash keys starting with "vector:"
            definition = IndexDefinition(
                prefix=["vector:"],
                index_type=IndexType.HASH
            )
            self.r.ft("idx:products").create_index(
                fields=schema,
                definition=definition
            )
        except redis.ResponseError as e:
            if "already exists" in str(e):
                pass  # Index already exists, which is fine
            else:
                raise Exception(f"Error creating vector index: {str(e)}")
        except Exception as e:
            raise Exception(f"Error creating vector index: {str(e)}")

    # BEGIN STORE PRODUCT CODE SECTION

    def store_product(self, vector_key: str, vector: list, metadata: dict = None) -> tuple[bool, str]:
        """Store a product with embedding in Redis using hash data structure with binary embedding storage"""
        try:
            # Convert embedding to binary bytes using numpy for efficient storage
            # This follows redis-py best practices for storing embeddings
            embedding = np.array(vector, dtype=np.float32)
            data = {"embedding": embedding.tobytes()}  # Store embedding as binary bytes

            # Add metadata fields to the hash
            if metadata:
                for key, value in metadata.items():
                    data[key] = str(value)

            # Store the hash in Redis using hset() method
            result = self.r.hset(vector_key, mapping=data)

            if result > 0:
                return True, f"Product stored successfully under key '{vector_key}'"
            else:
                return True, f"Product updated successfully under key '{vector_key}'"

        except Exception as e:
            return False, f"Error storing product: {e}"

    # END STORE PRODUCT CODE SECTION

    # BEGIN RETRIEVE PRODUCT CODE SECTION

    def retrieve_product(self, vector_key: str) -> tuple[bool, dict | str]:
        """Retrieve a product and its embedding from Redis"""
        try:
            # Retrieve all fields for the product using hgetall()
            retrieved_data = self.r.hgetall(vector_key)

            if retrieved_data:
                # Convert binary embedding back to list for display
                embedding_bytes = retrieved_data.get("embedding")
                if embedding_bytes:
                    embedding_array = np.frombuffer(embedding_bytes, dtype=np.float32)
                    vector = embedding_array.tolist()
                else:
                    vector = []

                result = {
                    "key": vector_key,
                    "vector": vector,
                    "product_id": retrieved_data.get("product_id", ""),
                    "name": retrieved_data.get("name", ""),
                    "category": retrieved_data.get("category", "")
                }

                return True, result
            else:
                return False, f"Key '{vector_key}' does not exist"

        except Exception as e:
            return False, f"Error retrieving product: {e}"

    # END RETRIEVE PRODUCT CODE SECTION

    # BEGIN SEARCH SIMILAR PRODUCTS CODE SECTION

    def search_similar_products(self, query_vector: list, top_k: int = 3) -> tuple[bool, list | str]:
        """Search for products similar to the query vector using RediSearch KNN queries"""
        try:
            # Convert query vector to binary bytes for KNN search
            query_bytes = np.array(query_vector, dtype=np.float32).tobytes()

            # Build KNN query using RediSearch vector search syntax for semantic similarity
            # *=>[KNN k @field_name $query_vec] finds k most similar products based on embedding distance
            knn_query = (
                Query(f"*=>[KNN {top_k} @embedding $query_vec AS score]")
                .return_fields("name", "category", "product_id", "score")
                .sort_by("score")
                .dialect(2)  # Dialect 2 enables vector search syntax
            )

            # Execute KNN search with query vector as parameter
            results = self.r.ft("idx:products").search(
                knn_query,
                query_params={"query_vec": query_bytes}
            )

            if results.total == 0:
                return False, "No products found in Redis"

            # Format results
            similarities = []
            for doc in results.docs:
                similarities.append({
                    "key": doc.id,
                    "similarity": float(doc.score),
                    "product_id": doc.product_id,
                    "name": doc.name,
                    "category": doc.category
                })

            return True, similarities

        except Exception as e:
            return False, f"Error searching products: {e}"

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
            product_keys = self.r.keys("vector:*")
            if product_keys:
                self.r.delete(*product_keys)  # Delete all keys at once
                return True, f"All {len(product_keys)} products deleted successfully"
            else:
                return False, "No products to delete"
        except Exception as e:
            return False, f"Error clearing products: {e}"

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
