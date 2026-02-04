"""
Test workflow for validating RAG document functions.
Runs a series of tests to verify storing, retrieving, and searching document chunks.
"""
from rag_functions import (
    store_document_chunk,
    get_chunks_by_document,
    search_chunks_by_metadata,
    get_chunk_by_id
)


def run_test_workflow() -> list:
    """
    Run a complete test workflow and return results.
    Returns a list of test results with name, status, and details.
    """
    results = []

    # Test 1: Store document chunks
    try:
        test_chunks = [
            {
                "document_id": "test-doc-001",
                "chunk_id": "test-doc-001-chunk-0",
                "content": "Azure Cosmos DB is a fully managed NoSQL database service.",
                "metadata": {
                    "source": "azure-docs",
                    "category": "databases",
                    "tags": ["nosql", "cosmosdb"],
                    "chunkIndex": 0
                }
            },
            {
                "document_id": "test-doc-001",
                "chunk_id": "test-doc-001-chunk-1",
                "content": "Cosmos DB offers multiple APIs including NoSQL, MongoDB, and Cassandra.",
                "metadata": {
                    "source": "azure-docs",
                    "category": "databases",
                    "tags": ["nosql", "api"],
                    "chunkIndex": 1
                }
            },
            {
                "document_id": "test-doc-002",
                "chunk_id": "test-doc-002-chunk-0",
                "content": "Azure Functions is a serverless compute service.",
                "metadata": {
                    "source": "azure-docs",
                    "category": "compute",
                    "tags": ["serverless", "functions"],
                    "chunkIndex": 0
                }
            }
        ]

        stored_count = 0
        total_ru = 0
        for chunk in test_chunks:
            result = store_document_chunk(
                document_id=chunk["document_id"],
                chunk_id=chunk["chunk_id"],
                content=chunk["content"],
                metadata=chunk["metadata"]
            )
            stored_count += 1
            total_ru += result["ru_charge"]

        results.append({
            "name": "Store Document Chunks",
            "status": "passed",
            "details": f"Stored {stored_count} chunks, total RU: {total_ru:.2f}"
        })
    except Exception as e:
        results.append({
            "name": "Store Document Chunks",
            "status": "failed",
            "details": str(e)
        })

    # Test 2: Get chunks by document
    try:
        chunks = get_chunks_by_document("test-doc-001")
        if len(chunks) >= 2:
            results.append({
                "name": "Get Chunks by Document",
                "status": "passed",
                "details": f"Retrieved {len(chunks)} chunks for test-doc-001"
            })
        else:
            results.append({
                "name": "Get Chunks by Document",
                "status": "failed",
                "details": f"Expected at least 2 chunks, got {len(chunks)}"
            })
    except Exception as e:
        results.append({
            "name": "Get Chunks by Document",
            "status": "failed",
            "details": str(e)
        })

    # Test 3: Search by metadata (category)
    try:
        chunks = search_chunks_by_metadata({"category": "databases"})
        if len(chunks) >= 2:
            results.append({
                "name": "Search by Category",
                "status": "passed",
                "details": f"Found {len(chunks)} chunks with category 'databases'"
            })
        else:
            results.append({
                "name": "Search by Category",
                "status": "failed",
                "details": f"Expected at least 2 chunks, got {len(chunks)}"
            })
    except Exception as e:
        results.append({
            "name": "Search by Category",
            "status": "failed",
            "details": str(e)
        })

    # Test 4: Search by metadata (tags)
    try:
        chunks = search_chunks_by_metadata({"tags": ["serverless"]})
        if len(chunks) >= 1:
            results.append({
                "name": "Search by Tag",
                "status": "passed",
                "details": f"Found {len(chunks)} chunks with tag 'serverless'"
            })
        else:
            results.append({
                "name": "Search by Tag",
                "status": "failed",
                "details": f"Expected at least 1 chunk, got {len(chunks)}"
            })
    except Exception as e:
        results.append({
            "name": "Search by Tag",
            "status": "failed",
            "details": str(e)
        })

    # Test 5: Point read
    try:
        chunk = get_chunk_by_id("test-doc-001", "test-doc-001-chunk-0")
        if chunk and chunk["content"]:
            results.append({
                "name": "Point Read (Get Chunk by ID)",
                "status": "passed",
                "details": f"Retrieved chunk with {len(chunk['content'])} characters"
            })
        else:
            results.append({
                "name": "Point Read (Get Chunk by ID)",
                "status": "failed",
                "details": "Chunk not found or empty"
            })
    except Exception as e:
        results.append({
            "name": "Point Read (Get Chunk by ID)",
            "status": "failed",
            "details": str(e)
        })

    return results
