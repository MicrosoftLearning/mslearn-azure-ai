import os
import sys
import json
import redis
import numpy as np
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def clear_screen():
    """Clear console screen (cross-platform)"""
    os.system('cls' if os.name == 'nt' else 'clear')

clear_screen()

# BEGIN CONNECTION CODE SECTION
def connect_to_redis() -> redis.Redis:
    """Establish connection to Azure Managed Redis"""
    clear_screen()

    try:
        # Azure Managed Redis with Non-Clustered policy uses standard Redis connection
        redis_host = os.getenv("REDIS_HOST")
        redis_key = os.getenv("REDIS_KEY")
        
        # Non-clustered policy uses standard Redis client connection
        r = redis.Redis(
            host=redis_host,
            port=10000,  # Azure Managed Redis uses port 10000
            ssl=True,
            decode_responses=True, # Decode responses to strings
            password=redis_key,
            socket_timeout=30,  # Add timeout for better reliability
            socket_connect_timeout=30,
        )

        print(f"Connected to Redis at {redis_host}")
        return r

    # END CONNECTION CODE SECTION

    except redis.ConnectionError as e:
        print(f"Connection error: {e}")
        print("Check if Redis host and port are correct, and ensure network connectivity")
        sys.exit(1)
    except redis.AuthenticationError as e:
        print(f"Authentication error: {e}")
        print("Make sure the access key is correct")
        sys.exit(1)
    except redis.TimeoutError as e:
        print(f"Timeout error: {e}")
        print("Check network latency and Redis server performance")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        if "999" in str(e):
            print("Error 999 typically indicates a network connectivity issue or firewall restriction")
        sys.exit(1)

# BEGIN VECTOR STORAGE CODE SECTION

def store_vector_data(r, vector_key, vector, metadata=None) -> None:
    """Store a vector with metadata in Redis"""
    clear_screen()
    print(f"Storing vector data for key: {vector_key}")
    
    try:
        # Convert vector to JSON string for storage
        vector_json = json.dumps(vector)
        
        # Store vector and metadata as a hash
        data = {"vector": vector_json}
        if metadata:
            for key, value in metadata.items():
                data[key] = str(value)
        
        result = r.hset(vector_key, mapping=data)
        if result > 0:
            print(f"Vector stored successfully under key '{vector_key}'")
            if metadata:
                print("Associated metadata:")
                for key, value in metadata.items():
                    print(f"  {key}: {value}")
        else:
            print(f"Vector updated successfully under key '{vector_key}'")
        input("\nPress Enter to continue...")
    except Exception as e:
        print(f"Error storing vector: {e}")
        input("\nPress Enter to continue...")

def input_new_vector(r) -> None:
    """Prompt user to input a new vector and store it"""
    clear_screen()
    vector_key = input("Enter vector key (e.g., vector:product_001): ").strip()
    vector_str = input("Enter vector as comma-separated numbers\n  Example: 0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8\n  (8 dimensions recommended): ").strip()
    
    try:
        vector = [float(x.strip()) for x in vector_str.split(",")]
        
        has_metadata = input("\nAdd metadata? (y/n): ").strip().lower() == 'y'
        metadata = {}
        if has_metadata:
            print("\nEnter metadata fields (like name, category, etc.)")
            entry_num = 1
            while True:
                meta_key = input(f"  Field #{entry_num} - Enter key (or press Enter to finish): ").strip()
                if not meta_key:
                    break
                meta_value = input(f"    Enter value for '{meta_key}': ").strip()
                metadata[meta_key] = meta_value
                entry_num += 1
        
        store_vector_data(r, vector_key, vector, metadata)
    except ValueError:
        clear_screen()
        print("Error: Vector must be comma-separated numbers.")
        input("\nPress Enter to continue...")

def input_retrieve_vector(r) -> None:
    """Prompt user to retrieve a vector"""
    clear_screen()
    print("Retrieve a stored vector by its key")
    print("  Example keys: vector:product_001, vector:product_002\n")
    vector_key = input("Enter vector key to retrieve: ").strip()
    retrieve_vector_data(r, vector_key)

def input_search_vectors(r) -> None:
    """Prompt user to search for similar vectors"""
    clear_screen()
    print("Search for vectors similar to a query vector")
    query_str = input("Enter query vector as comma-separated numbers\n  Example: 0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8\n  (must match stored vector dimensions): ").strip()
    try:
        query_vector = [float(x.strip()) for x in query_str.split(",")]
        top_k_str = input("\nHow many similar vectors to return? (default 3, max 10): ").strip() or "3"
        top_k = int(top_k_str)
        if top_k < 1 or top_k > 10:
            print("Invalid number. Using default of 3.")
            top_k = 3
        search_similar_vectors(r, query_vector, top_k)
    except ValueError:
        clear_screen()
        print("Error: Query vector must be comma-separated numbers and count must be an integer.")
        input("\nPress Enter to continue...")

def input_delete_vector(r) -> None:
    """Prompt user to delete a vector"""
    clear_screen()
    print("Delete a stored vector by its key")
    print("  Example keys: vector:product_001, vector:product_002\n")
    vector_key = input("Enter vector key to delete: ").strip()
    delete_vector(r, vector_key)

# END VECTOR STORAGE CODE SECTION

# BEGIN VECTOR RETRIEVAL CODE SECTION

def retrieve_vector_data(r, vector_key) -> dict:
    """Retrieve a vector and its metadata from Redis"""
    clear_screen()
    print(f"Retrieving vector data for key: {vector_key}")
    
    try:
        retrieved_data = r.hgetall(vector_key)
        if retrieved_data:
            print("\nRetrieved vector data:")
            
            # Extract and display vector
            if "vector" in retrieved_data:
                vector = json.loads(retrieved_data["vector"])
                print(f"  Vector dimensions: {len(vector)}")
                print(f"  Vector (first 5 elements): {vector[:5]}...")
            
            # Display metadata
            metadata_keys = [k for k in retrieved_data.keys() if k != "vector"]
            if metadata_keys:
                print("\n  Metadata:")
                for key in metadata_keys:
                    print(f"    {key}: {retrieved_data[key]}")
            
            return retrieved_data
        else:
            print(f"Key '{vector_key}' does not exist.")
            return None
    except Exception as e:
        print(f"Error retrieving vector: {e}")
        return None
    finally:
        input("\nPress Enter to continue...")

# END VECTOR RETRIEVAL CODE SECTION

# BEGIN SIMILARITY SEARCH CODE SECTION

def calculate_similarity(vector1, vector2) -> float:
    """Calculate cosine similarity between two vectors"""
    try:
        v1 = np.array(vector1)
        v2 = np.array(vector2)
        
        # Calculate cosine similarity
        dot_product = np.dot(v1, v2)
        magnitude1 = np.linalg.norm(v1)
        magnitude2 = np.linalg.norm(v2)
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        similarity = dot_product / (magnitude1 * magnitude2)
        return float(similarity)
    except Exception:
        return 0.0

def search_similar_vectors(r, query_vector, top_k=3) -> None:
    """Search for similar vectors in Redis"""
    clear_screen()
    print("Searching for similar vectors...")
    print(f"Query vector (first 5 elements): {query_vector[:5]}...")
    print(f"Retrieving top {top_k} similar vectors\n")
    
    try:
        # Get all vector keys (pattern: vector:*)
        vector_keys = r.keys("vector:*")
        
        if not vector_keys:
            print("No vectors found in Redis.")
            input("\nPress Enter to continue...")
            return
        
        similarities = []
        
        # Calculate similarity for each stored vector
        for key in vector_keys:
            vector_data = r.hgetall(key)
            if "vector" in vector_data:
                stored_vector = json.loads(vector_data["vector"])
                similarity = calculate_similarity(query_vector, stored_vector)
                similarities.append((key, similarity, vector_data))
        
        # Sort by similarity descending and get top_k results
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_results = similarities[:top_k]
        
        if top_results:
            print("=" * 60)
            print("Top Similar Vectors")
            print("=" * 60)
            
            for idx, (key, similarity, data) in enumerate(top_results, 1):
                print(f"\n{idx}. Vector Key: {key}")
                print(f"   Similarity Score: {similarity:.4f}")
                
                # Display metadata
                metadata_keys = [k for k in data.keys() if k != "vector"]
                if metadata_keys:
                    print("   Metadata:")
                    for meta_key in metadata_keys:
                        print(f"     {meta_key}: {data[meta_key]}")
            print("\n" + "=" * 60)
        else:
            print("No similar vectors found.")
        
        input("\nPress Enter to continue...")
    except Exception as e:
        print(f"Error searching vectors: {e}")
        input("\nPress Enter to continue...")

# END SIMILARITY SEARCH CODE SECTION

# BEGIN DELETE CODE SECTION

def delete_vector(r, vector_key) -> None:
    """Delete a vector from Redis"""
    clear_screen()
    print(f"Deleting vector: {vector_key}...")
    
    try:
        result = r.delete(vector_key)
        if result == 1:
            print(f"Vector '{vector_key}' deleted successfully.")
        else:
            print(f"Vector '{vector_key}' does not exist.")
    except Exception as e:
        print(f"Error deleting vector: {e}")
    finally:
        input("\nPress Enter to continue...")

# END DELETE CODE SECTION

# BEGIN LIST VECTORS CODE SECTION

def list_all_vectors(r) -> None:
    """List all vectors stored in Redis"""
    clear_screen()
    print("Listing all stored vectors...\n")
    
    try:
        vector_keys = r.keys("vector:*")
        
        if not vector_keys:
            print("No vectors found in Redis.")
        else:
            print(f"Total vectors stored: {len(vector_keys)}\n")
            print("Vector Keys:")
            for key in sorted(vector_keys):
                vector_data = r.hgetall(key)
                if "vector" in vector_data:
                    vector = json.loads(vector_data["vector"])
                    print(f"  • {key} ({len(vector)} dimensions)", end="")
                    
                    # Show metadata count if available
                    metadata_count = len([k for k in vector_data.keys() if k != "vector"])
                    if metadata_count > 0:
                        print(f" - {metadata_count} metadata field(s)")
                    else:
                        print()
    except Exception as e:
        print(f"Error listing vectors: {e}")
    finally:
        input("\nPress Enter to continue...")

# END LIST VECTORS CODE SECTION

def load_sample_vectors(r) -> None:
    """Load sample vector data into Redis from sample_data.json"""
    clear_screen()
    print("Loading sample vectors...")
    
    try:
        # Load sample data from JSON file
        with open("sample_data.json", "r") as f:
            sample_vectors = json.load(f)
        
        count = 0
        for item in sample_vectors:
            vector_json = json.dumps(item["vector"])
            data = {"vector": vector_json}
            data.update(item["metadata"])
            
            r.hset(item["key"], mapping=data)
            count += 1
            print(f"  Loaded: {item['metadata']['name']}")
        
        print(f"\n{count} sample vectors loaded successfully!")
        input("\nPress Enter to continue...")
    except FileNotFoundError:
        print("Error: sample_data.json file not found in the project directory.")
        input("\nPress Enter to continue...")
    except Exception as e:
        print(f"Error loading sample vectors: {e}")
        input("\nPress Enter to continue...")

def show_menu():
    """Display the main menu"""
    clear_screen()
    print("=" * 60)
    print("    Redis Vector Storage & Search Menu")
    print("=" * 60)
    print("1. Load sample vectors")
    print("2. Store a new vector")
    print("3. Retrieve a vector")
    print("4. Search for similar vectors")
    print("5. List all vectors")
    print("6. Delete a vector")
    print("7. Clear all vectors")
    print("8. Exit")
    print("=" * 60)

def main() -> None:
    clear_screen()
    r = connect_to_redis()
    
    try:
        while True:
            show_menu()
            choice = input("\nPlease select an option (1-8): ")
            
            if choice == "1":
                load_sample_vectors(r)
            
            elif choice == "2":
                input_new_vector(r)
            
            elif choice == "3":
                input_retrieve_vector(r)
            
            elif choice == "4":
                input_search_vectors(r)
            
            elif choice == "5":
                list_all_vectors(r)
            
            elif choice == "6":
                input_delete_vector(r)
            
            elif choice == "7":
                clear_screen()
                confirm = input("Are you sure you want to delete ALL vectors? (yes/no): ").strip().lower()
                if confirm == "yes":
                    try:
                        vector_keys = r.keys("vector:*")
                        if vector_keys:
                            r.delete(*vector_keys)
                            print(f"All {len(vector_keys)} vectors deleted successfully.")
                        else:
                            print("No vectors to delete.")
                    except Exception as e:
                        print(f"Error clearing vectors: {e}")
                else:
                    print("Operation cancelled.")
                input("\nPress Enter to continue...")
            
            elif choice == "8":
                clear_screen()
                print("Exiting...")
                break
            else:
                print("\nInvalid option. Please select 1-8.")
                input("\nPress Enter to continue...")
        
    finally:
        # Clean up connection
        try:
            r.close()
            print("Redis connection closed")
        except Exception as e:
            print(f"Error closing connection: {e}")

if __name__ == "__main__":
    main()
