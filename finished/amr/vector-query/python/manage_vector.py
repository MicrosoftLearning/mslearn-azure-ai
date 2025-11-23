import os
import json
import redis
import numpy as np
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class VectorManager:
    """Handles all vector storage and retrieval operations with Redis"""

    def __init__(self):
        """Initialize vector manager and establish Redis connection"""
        self.r = self._connect_to_redis()

    # BEGIN CONNECTION CODE SECTION

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
                decode_responses=True,  # Decode responses to strings
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

    # END CONNECTION CODE SECTION

    # BEGIN VECTOR STORAGE CODE SECTION

    def store_vector(self, vector_key: str, vector: list, metadata: dict = None) -> tuple[bool, str]:
        """Store a vector with metadata in Redis using hash data structure"""
        try:
            # Convert vector to JSON string for storage
            vector_json = json.dumps(vector)
            data = {"vector": vector_json}  # Store vector as JSON

            # Add metadata fields to the hash
            if metadata:
                for key, value in metadata.items():
                    data[key] = str(value)

            # Store the hash in Redis using hset() method
            result = self.r.hset(vector_key, mapping=data)

            if result > 0:
                return True, f"Vector stored successfully under key '{vector_key}'"
            else:
                return True, f"Vector updated successfully under key '{vector_key}'"

        except Exception as e:
            return False, f"Error storing vector: {e}"

    # END VECTOR STORAGE CODE SECTION

    # BEGIN VECTOR RETRIEVAL CODE SECTION

    def retrieve_vector(self, vector_key: str) -> tuple[bool, dict | str]:
        """Retrieve a vector and its metadata from Redis"""
        try:
            # Retrieve all hash fields for the given key using hgetall()
            retrieved_data = self.r.hgetall(vector_key)

            if retrieved_data:
                # Parse the stored vector from JSON
                result = {
                    "key": vector_key,
                    "vector": json.loads(retrieved_data["vector"]),
                    "metadata": {}
                }

                # Extract metadata fields
                for key, value in retrieved_data.items():
                    if key != "vector":
                        result["metadata"][key] = value

                return True, result
            else:
                return False, f"Key '{vector_key}' does not exist"

        except Exception as e:
            return False, f"Error retrieving vector: {e}"

    # END VECTOR RETRIEVAL CODE SECTION

    # BEGIN SIMILARITY CALCULATION CODE SECTION

    @staticmethod
    def calculate_similarity(vector1: list, vector2: list) -> float:
        """Calculate cosine similarity between two vectors using numpy array operations"""
        try:
            # Convert lists to numpy arrays with float64 precision
            v1 = np.array(vector1, dtype=np.float64)
            v2 = np.array(vector2, dtype=np.float64)

            # Check for dimension mismatch
            if v1.shape != v2.shape:
                return 0.0

            # Calculate dot product: a·b
            dot_product = np.dot(v1, v2)

            # Calculate magnitudes (norms): ||a|| and ||b||
            magnitude1 = np.linalg.norm(v1)
            magnitude2 = np.linalg.norm(v2)

            # Handle zero-magnitude vectors
            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0

            # Cosine similarity formula: (a·b) / (||a|| * ||b||)
            # Result ranges from -1 to 1 (1 = identical, -1 = opposite, 0 = perpendicular)
            similarity = dot_product / (magnitude1 * magnitude2)
            return float(similarity)
        except Exception:
            return 0.0

    # END SIMILARITY CALCULATION CODE SECTION

    # BEGIN VECTOR SEARCH CODE SECTION

    def search_similar_vectors(self, query_vector: list, top_k: int = 3) -> tuple[bool, list | str]:
        """Search for vectors similar to the query vector using cosine similarity"""
        try:
            # Retrieve all vector keys from Redis using pattern matching
            vector_keys = self.r.keys("vector:*")

            if not vector_keys:
                return False, "No vectors found in Redis"

            similarities = []

            # Calculate similarity score for each stored vector
            for key in vector_keys:
                vector_data = self.r.hgetall(key)  # Retrieve vector and metadata
                if "vector" in vector_data:
                    stored_vector = json.loads(vector_data["vector"])  # Parse vector from JSON
                    similarity = self.calculate_similarity(query_vector, stored_vector)  # Calculate similarity score

                    # Extract metadata
                    metadata = {k: v for k, v in vector_data.items() if k != "vector"}
                    similarities.append({
                        "key": key,
                        "similarity": similarity,
                        "metadata": metadata
                    })

            # Sort by similarity score in descending order and return top_k results
            similarities.sort(key=lambda x: x["similarity"], reverse=True)
            return True, similarities[:top_k]

        except Exception as e:
            return False, f"Error searching vectors: {e}"

    # END VECTOR SEARCH CODE SECTION

    # BEGIN DELETE CODE SECTION

    def delete_vector(self, vector_key: str) -> tuple[bool, str]:
        """Delete a vector from Redis using del() method"""
        try:
            # Delete the key using Redis del() method
            result = self.r.delete(vector_key)
            if result == 1:
                return True, f"Vector '{vector_key}' deleted successfully"
            else:
                return False, f"Vector '{vector_key}' does not exist"
        except Exception as e:
            return False, f"Error deleting vector: {e}"

    # END DELETE CODE SECTION

    def list_all_vectors(self) -> tuple[bool, list | str]:
        """List all vectors stored in Redis with their dimensions and metadata"""
        try:
            # Retrieve all vector keys using pattern matching keys()
            vector_keys = self.r.keys("vector:*")

            if not vector_keys:
                return False, "No vectors found in Redis"

            vectors = []
            for key in sorted(vector_keys):
                vector_data = self.r.hgetall(key)  # Retrieve all fields for the key
                if "vector" in vector_data:
                    vector = json.loads(vector_data["vector"])
                    metadata = {k: v for k, v in vector_data.items() if k != "vector"}

                    vectors.append({
                        "key": key,
                        "dimensions": len(vector),
                        "metadata": metadata
                    })

            return True, vectors

        except Exception as e:
            return False, f"Error listing vectors: {e}"

    def clear_all_vectors(self) -> tuple[bool, str]:
        """Delete all vectors from Redis"""
        try:
            # Retrieve all vector keys and delete them in bulk
            vector_keys = self.r.keys("vector:*")
            if vector_keys:
                self.r.delete(*vector_keys)  # Delete all keys at once
                return True, f"All {len(vector_keys)} vectors deleted successfully"
            else:
                return False, "No vectors to delete"
        except Exception as e:
            return False, f"Error clearing vectors: {e}"

    def load_sample_vectors(self) -> tuple[bool, str]:
        """Load sample vector data into Redis from sample_data.json"""
        try:
            # Read sample data from JSON file
            with open("sample_data.json", "r") as f:
                sample_vectors = json.load(f)

            count = 0
            for item in sample_vectors:
                # Prepare vector data for storage
                vector_json = json.dumps(item["vector"])
                data = {"vector": vector_json}
                data.update(item["metadata"])

                # Store each vector in Redis
                self.r.hset(item["key"], mapping=data)
                count += 1

            return True, f"{count} sample vectors loaded successfully"

        except FileNotFoundError:
            return False, "Error: sample_data.json file not found"
        except Exception as e:
            return False, f"Error loading sample vectors: {e}"
