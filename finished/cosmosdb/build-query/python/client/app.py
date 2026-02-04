"""
Flask application demonstrating RAG document storage with Azure Cosmos DB for NoSQL.
"""
import json
import os
from flask import Flask, render_template, request, redirect, url_for, flash

from rag_functions import (
    store_document_chunk,
    get_chunks_by_document,
    search_chunks_by_metadata,
    get_chunk_by_id,
    get_container
)
from test_workflow import run_test_workflow
from query_executor import execute_query, get_sample_queries

app = Flask(__name__)
app.secret_key = os.urandom(24)


def load_json_file(filename):
    """Load chunks from a JSON file."""
    filepath = os.path.join(os.path.dirname(__file__), filename)
    with open(filepath, "r") as f:
        data = json.load(f)
    return data.get("chunks", [])


def get_all_document_ids():
    """Get a list of unique document IDs from the container."""
    try:
        container = get_container()
        query = "SELECT DISTINCT c.documentId FROM c"
        items = container.query_items(
            query=query,
            enable_cross_partition_query=True
        )
        return sorted([item["documentId"] for item in items])
    except Exception:
        return []


def get_all_categories():
    """Get a list of unique categories from the container."""
    try:
        container = get_container()
        query = "SELECT DISTINCT c.metadata.category FROM c WHERE IS_DEFINED(c.metadata.category)"
        items = container.query_items(
            query=query,
            enable_cross_partition_query=True
        )
        return sorted([item["category"] for item in items if item.get("category")])
    except Exception:
        return []


@app.route("/")
def index():
    """Display the main page."""
    document_ids = get_all_document_ids()
    categories = get_all_categories()
    sample_queries = get_sample_queries()
    return render_template(
        "index.html",
        document_ids=document_ids,
        categories=categories,
        sample_queries=sample_queries
    )


@app.route("/load-data", methods=["POST"])
def load_data():
    """Load sample document chunks into the database."""
    try:
        chunks = load_json_file("sample_chunks.json")
        loaded_count = 0
        total_ru = 0

        for chunk in chunks:
            result = store_document_chunk(
                document_id=chunk["document_id"],
                chunk_id=chunk["chunk_id"],
                content=chunk["content"],
                metadata=chunk["metadata"]
            )
            loaded_count += 1
            total_ru += result["ru_charge"]

        flash(f"Successfully loaded {loaded_count} chunks! Total RU: {total_ru:.2f}", "success")
    except Exception as e:
        flash(f"Error loading data: {str(e)}", "error")

    return redirect(url_for("index"))


@app.route("/store-chunk", methods=["POST"])
def store_chunk():
    """Store a new document chunk."""
    document_id = request.form.get("document_id", "").strip()
    chunk_id = request.form.get("chunk_id", "").strip()
    content = request.form.get("content", "").strip()
    category = request.form.get("category", "").strip()
    tags_str = request.form.get("tags", "").strip()
    chunk_index = request.form.get("chunk_index", "0").strip()

    if not document_id or not chunk_id or not content:
        flash("Document ID, Chunk ID, and Content are required", "error")
        return redirect(url_for("index"))

    try:
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
        metadata = {
            "category": category,
            "tags": tags,
            "chunkIndex": int(chunk_index)
        }

        result = store_document_chunk(
            document_id=document_id,
            chunk_id=chunk_id,
            content=content,
            metadata=metadata
        )

        flash(f"Chunk stored successfully! RU charge: {result['ru_charge']:.2f}", "success")
    except Exception as e:
        flash(f"Error storing chunk: {str(e)}", "error")

    return redirect(url_for("index"))


@app.route("/get-chunks", methods=["POST"])
def get_chunks():
    """Get all chunks for a specific document."""
    document_id = request.form.get("document_id", "").strip()

    if not document_id:
        flash("Please select a document ID", "error")
        return redirect(url_for("index"))

    try:
        chunks = get_chunks_by_document(document_id)
        document_ids = get_all_document_ids()
        categories = get_all_categories()
        sample_queries = get_sample_queries()

        return render_template(
            "index.html",
            document_ids=document_ids,
            categories=categories,
            sample_queries=sample_queries,
            chunks_result=chunks,
            chunks_document_id=document_id
        )
    except Exception as e:
        flash(f"Error retrieving chunks: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/search-metadata", methods=["POST"])
def search_metadata():
    """Search chunks by metadata filters."""
    category = request.form.get("category", "").strip()
    tag = request.form.get("tag", "").strip()

    filters = {}
    if category:
        filters["category"] = category
    if tag:
        filters["tags"] = [tag]

    if not filters:
        flash("Please provide at least one filter (category or tag)", "error")
        return redirect(url_for("index"))

    try:
        chunks = search_chunks_by_metadata(filters)
        document_ids = get_all_document_ids()
        categories = get_all_categories()
        sample_queries = get_sample_queries()

        return render_template(
            "index.html",
            document_ids=document_ids,
            categories=categories,
            sample_queries=sample_queries,
            search_result=chunks,
            search_filters=filters
        )
    except Exception as e:
        flash(f"Error searching: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/run-tests", methods=["POST"])
def run_tests():
    """Run the test workflow."""
    try:
        test_results = run_test_workflow()
        document_ids = get_all_document_ids()
        categories = get_all_categories()
        sample_queries = get_sample_queries()

        return render_template(
            "index.html",
            document_ids=document_ids,
            categories=categories,
            sample_queries=sample_queries,
            test_results=test_results
        )
    except Exception as e:
        flash(f"Error running tests: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/execute-query", methods=["POST"])
def run_query():
    """Execute a custom SQL query."""
    sql_query = request.form.get("sql_query", "").strip()

    if not sql_query:
        flash("Please enter a SQL query", "error")
        return redirect(url_for("index"))

    result = execute_query(sql_query)
    document_ids = get_all_document_ids()
    categories = get_all_categories()
    sample_queries = get_sample_queries()

    return render_template(
        "index.html",
        document_ids=document_ids,
        categories=categories,
        sample_queries=sample_queries,
        query_result=result,
        executed_query=sql_query
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
