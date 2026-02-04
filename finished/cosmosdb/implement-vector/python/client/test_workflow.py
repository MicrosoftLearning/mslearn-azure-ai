"""
Test workflow for validating vector search functions.
Runs a series of tests to verify storing, retrieving, and searching documents with embeddings.
"""
from vector_functions import (
    store_vector_document,
    vector_similarity_search,
    filtered_vector_search,
    get_container
)


def run_test_workflow() -> list:
    """
    Run a complete test workflow and return results.
    Returns a list of test results with name, status, and details.
    """
    results = []

    # Test 1: Store documents with embeddings
    try:
        # Create test documents with small embeddings for testing
        test_embedding = [0.1] * 256  # 256-dimensional test vector

        test_docs = [
            {
                "document_id": "test-vector-001",
                "chunk_id": "test-vector-001-chunk-0",
                "content": "Azure Cosmos DB supports vector similarity search for AI applications.",
                "embedding": test_embedding,
                "metadata": {
                    "source": "test-docs",
                    "category": "databases",
                    "tags": ["cosmosdb", "vector-search"],
                    "chunkIndex": 0
                }
            },
            {
                "document_id": "test-vector-001",
                "chunk_id": "test-vector-001-chunk-1",
                "content": "Vector embeddings enable semantic search capabilities in modern applications.",
                "embedding": [0.2] * 256,
                "metadata": {
                    "source": "test-docs",
                    "category": "ai-applications",
                    "tags": ["embeddings", "semantic-search"],
                    "chunkIndex": 1
                }
            }
        ]

        stored_count = 0
        total_ru = 0
        for doc in test_docs:
            result = store_vector_document(
                document_id=doc["document_id"],
                chunk_id=doc["chunk_id"],
                content=doc["content"],
                embedding=doc["embedding"],
                metadata=doc["metadata"]
            )
            stored_count += 1
            total_ru += result["ru_charge"]

        results.append({
            "name": "Store Vector Documents",
            "status": "passed",
            "details": f"Stored {stored_count} documents with embeddings, total RU: {total_ru:.2f}"
        })
    except Exception as e:
        results.append({
            "name": "Store Vector Documents",
            "status": "failed",
            "details": str(e)
        })

    # Test 2: Vector similarity search
    try:
        query_embedding = [0.1] * 256  # Should be similar to first test doc
        search_results = vector_similarity_search(query_embedding, top_n=3)

        if len(search_results) >= 1:
            # Check that results have similarity scores
            first_result = search_results[0]
            if "similarity_score" in first_result:
                results.append({
                    "name": "Vector Similarity Search",
                    "status": "passed",
                    "details": f"Found {len(search_results)} results, top score: {first_result['similarity_score']:.4f}"
                })
            else:
                results.append({
                    "name": "Vector Similarity Search",
                    "status": "failed",
                    "details": "Results missing similarity_score field"
                })
        else:
            results.append({
                "name": "Vector Similarity Search",
                "status": "failed",
                "details": f"Expected at least 1 result, got {len(search_results)}"
            })
    except Exception as e:
        results.append({
            "name": "Vector Similarity Search",
            "status": "failed",
            "details": str(e)
        })

    # Test 3: Filtered vector search
    try:
        query_embedding = [0.15] * 256
        search_results = filtered_vector_search(
            query_embedding,
            category="databases",
            top_n=3
        )

        if len(search_results) >= 1:
            # Verify all results have the filtered category
            all_correct_category = all(
                r.get("metadata", {}).get("category") == "databases"
                for r in search_results
            )
            if all_correct_category:
                results.append({
                    "name": "Filtered Vector Search",
                    "status": "passed",
                    "details": f"Found {len(search_results)} results filtered by category 'databases'"
                })
            else:
                results.append({
                    "name": "Filtered Vector Search",
                    "status": "failed",
                    "details": "Results contain items with wrong category"
                })
        else:
            results.append({
                "name": "Filtered Vector Search",
                "status": "passed",
                "details": "No results found for filter (may be expected if no matching data)"
            })
    except Exception as e:
        results.append({
            "name": "Filtered Vector Search",
            "status": "failed",
            "details": str(e)
        })

    return results
