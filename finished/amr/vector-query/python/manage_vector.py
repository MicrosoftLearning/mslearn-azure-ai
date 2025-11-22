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
    
    def _connect_to_redis(self) -> redis.Redis:
        """Establish connection to Azure Managed Redis"""
        try:
            redis_host = os.getenv("REDIS_HOST")
            redis_key = os.getenv("REDIS_KEY")
            
            r = redis.Redis(
                host=redis_host,
                port=10000,
                ssl=True,
                decode_responses=True,
                password=redis_key,
                socket_timeout=30,
                socket_connect_timeout=30,
            )
            
            # Test connection
            r.ping()
            return r
        
        except redis.ConnectionError as e:
            raise Exception(f"Connection error: {e}")
        except redis.AuthenticationError as e:
            raise Exception(f"Authentication error: {e}")
        except Exception as e:
            raise Exception(f"Unexpected error: {e}")
    
    def store_vector(self, vector_key: str, vector: list, metadata: dict = None) -> tuple[bool, str]:
        """Store a vector with metadata in Redis"""
        try:
            vector_json = json.dumps(vector)
            data = {"vector": vector_json}
            
            if metadata:
                for key, value in metadata.items():
                    data[key] = str(value)
            
            result = self.r.hset(vector_key, mapping=data)
            
            if result > 0:
                return True, f"Vector stored successfully under key '{vector_key}'"
            else:
                return True, f"Vector updated successfully under key '{vector_key}'"
        
        except Exception as e:
            return False, f"Error storing vector: {e}"
    
    def retrieve_vector(self, vector_key: str) -> tuple[bool, dict | str]:
        """Retrieve a vector and its metadata from Redis"""
        try:
            retrieved_data = self.r.hgetall(vector_key)
            
            if retrieved_data:
                result = {
                    "key": vector_key,
                    "vector": json.loads(retrieved_data["vector"]),
                    "metadata": {}
                }
                
                # Extract metadata
                for key, value in retrieved_data.items():
                    if key != "vector":
                        result["metadata"][key] = value
                
                return True, result
            else:
                return False, f"Key '{vector_key}' does not exist"
        
        except Exception as e:
            return False, f"Error retrieving vector: {e}"
    
    @staticmethod
    def calculate_similarity(vector1: list, vector2: list) -> float:
        """Calculate cosine similarity between two vectors"""
        try:
            v1 = np.array(vector1, dtype=np.float64)
            v2 = np.array(vector2, dtype=np.float64)
            
            # Check for dimension mismatch
            if v1.shape != v2.shape:
                return 0.0
            
            dot_product = np.dot(v1, v2)
            magnitude1 = np.linalg.norm(v1)
            magnitude2 = np.linalg.norm(v2)
            
            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0
            
            similarity = dot_product / (magnitude1 * magnitude2)
            return float(similarity)
        except Exception:
            return 0.0
    
    def search_similar_vectors(self, query_vector: list, top_k: int = 3) -> tuple[bool, list | str]:
        """Search for similar vectors in Redis"""
        try:
            vector_keys = self.r.keys("vector:*")
            
            if not vector_keys:
                return False, "No vectors found in Redis"
            
            similarities = []
            
            for key in vector_keys:
                vector_data = self.r.hgetall(key)
                if "vector" in vector_data:
                    stored_vector = json.loads(vector_data["vector"])
                    similarity = self.calculate_similarity(query_vector, stored_vector)
                    
                    metadata = {k: v for k, v in vector_data.items() if k != "vector"}
                    similarities.append({
                        "key": key,
                        "similarity": similarity,
                        "metadata": metadata
                    })
            
            # Sort by similarity descending
            similarities.sort(key=lambda x: x["similarity"], reverse=True)
            return True, similarities[:top_k]
        
        except Exception as e:
            return False, f"Error searching vectors: {e}"
    
    def delete_vector(self, vector_key: str) -> tuple[bool, str]:
        """Delete a vector from Redis"""
        try:
            result = self.r.delete(vector_key)
            if result == 1:
                return True, f"Vector '{vector_key}' deleted successfully"
            else:
                return False, f"Vector '{vector_key}' does not exist"
        except Exception as e:
            return False, f"Error deleting vector: {e}"
    
    def list_all_vectors(self) -> tuple[bool, list | str]:
        """List all vectors stored in Redis"""
        try:
            vector_keys = self.r.keys("vector:*")
            
            if not vector_keys:
                return False, "No vectors found in Redis"
            
            vectors = []
            for key in sorted(vector_keys):
                vector_data = self.r.hgetall(key)
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
            vector_keys = self.r.keys("vector:*")
            if vector_keys:
                self.r.delete(*vector_keys)
                return True, f"All {len(vector_keys)} vectors deleted successfully"
            else:
                return False, "No vectors to delete"
        except Exception as e:
            return False, f"Error clearing vectors: {e}"
    
    def load_sample_vectors(self) -> tuple[bool, str]:
        """Load sample vector data into Redis from sample_data.json"""
        try:
            with open("sample_data.json", "r") as f:
                sample_vectors = json.load(f)
            
            count = 0
            for item in sample_vectors:
                vector_json = json.dumps(item["vector"])
                data = {"vector": vector_json}
                data.update(item["metadata"])
                
                self.r.hset(item["key"], mapping=data)
                count += 1
            
            return True, f"{count} sample vectors loaded successfully"
        
        except FileNotFoundError:
            return False, "Error: sample_data.json file not found"
        except Exception as e:
            return False, f"Error loading sample vectors: {e}"
