"""
Flask application demonstrating vector search with Azure Cosmos DB for NoSQL.
"""
import json
import os
from flask import Flask, render_template, request, redirect, url_for, flash

from vector_functions import (
    store_vector_document,
    vector_similarity_search,
    filtered_vector_search,
    get_all_categories,
    get_all_document_ids,
    get_container
)
from query_executor import execute_query

app = Flask(__name__)
app.secret_key = os.urandom(24)


def load_json_file(filename):
    """Load documents and queries from a JSON file."""
    filepath = os.path.join(os.path.dirname(__file__), filename)
    with open(filepath, "r") as f:
        data = json.load(f)
    return data


def get_sample_queries():
    """Get the pre-computed query vectors from the sample data file."""
    try:
        data = load_json_file("sample_vectors.json")
        return data.get("queries", [])
    except Exception:
        return []


@app.route("/")
def index():
    """Display the main page."""
    document_ids = get_all_document_ids()
    categories = get_all_categories()
    queries = get_sample_queries()
    return render_template(
        "index.html",
        document_ids=document_ids,
        categories=categories,
        queries=queries
    )


@app.route("/load-data", methods=["POST"])
def load_data():
    """Load sample documents with embeddings into the database."""
    try:
        data = load_json_file("sample_vectors.json")
        documents = data.get("documents", [])
        loaded_count = 0
        total_ru = 0

        for doc in documents:
            result = store_vector_document(
                document_id=doc["document_id"],
                chunk_id=doc["chunk_id"],
                content=doc["content"],
                embedding=doc["embedding"],
                metadata=doc["metadata"]
            )
            loaded_count += 1
            total_ru += result["ru_charge"]

        flash(f"Successfully loaded {loaded_count} tickets with embeddings! Total RU: {total_ru:.2f}", "success")
    except Exception as e:
        flash(f"Error loading data: {str(e)}", "error")

    return redirect(url_for("index"))


@app.route("/vector-search", methods=["POST"])
def search_vectors():
    """Perform vector similarity search using a pre-computed query vector."""
    query_id = request.form.get("query_id", "").strip()
    top_n = int(request.form.get("top_n", 5))

    if not query_id:
        flash("Please select a query", "error")
        return redirect(url_for("index"))

    try:
        # Get the query embedding from sample data
        queries = get_sample_queries()
        query = next((q for q in queries if q["id"] == query_id), None)

        if not query:
            flash("Query not found", "error")
            return redirect(url_for("index"))

        results = vector_similarity_search(query["embedding"], top_n)

        document_ids = get_all_document_ids()
        categories = get_all_categories()
        all_queries = get_sample_queries()

        return render_template(
            "index.html",
            document_ids=document_ids,
            categories=categories,
            queries=all_queries,
            vector_result=results,
            vector_query=query["description"],
            vector_top_n=top_n
        )
    except Exception as e:
        flash(f"Error performing vector search: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/filtered-vector-search", methods=["POST"])
def search_filtered_vectors():
    """Perform filtered vector search combining metadata and similarity."""
    query_id = request.form.get("filtered_query_id", "").strip()
    category = request.form.get("filter_category", "").strip()
    top_n = int(request.form.get("filtered_top_n", 5))

    if not query_id:
        flash("Please select a query", "error")
        return redirect(url_for("index"))

    try:
        # Get the query embedding from sample data
        queries = get_sample_queries()
        query = next((q for q in queries if q["id"] == query_id), None)

        if not query:
            flash("Query not found", "error")
            return redirect(url_for("index"))

        results = filtered_vector_search(
            query["embedding"],
            category=category if category else None,
            top_n=top_n
        )

        document_ids = get_all_document_ids()
        categories = get_all_categories()
        all_queries = get_sample_queries()

        return render_template(
            "index.html",
            document_ids=document_ids,
            categories=categories,
            queries=all_queries,
            filtered_result=results,
            filtered_query=query["description"],
            filtered_category=category,
            filtered_top_n=top_n
        )
    except Exception as e:
        flash(f"Error performing filtered search: {str(e)}", "error")
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
    queries = get_sample_queries()

    return render_template(
        "index.html",
        document_ids=document_ids,
        categories=categories,
        queries=queries,
        query_result=result,
        executed_query=sql_query
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
