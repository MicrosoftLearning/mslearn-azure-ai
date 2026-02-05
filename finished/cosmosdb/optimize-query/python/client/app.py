"""
Flask application for comparing vector index performance in Azure Cosmos DB.

This app demonstrates how different vector indexing strategies (flat, quantizedFlat,
diskANN) affect query performance and RU consumption. Users can load sample data,
run vector similarity searches, and compare results side-by-side.
"""
import json
import os
from flask import Flask, render_template, request, redirect, url_for, flash

from index_functions import (
    bulk_load_documents,
    compare_index_performance,
    compare_filtered_performance,
    get_all_categories,
    get_all_document_counts,
    CONTAINER_FLAT,
    CONTAINER_QUANTIZED,
    CONTAINER_DISKANN
)

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
    """Display the main page with index comparison interface."""
    categories = get_all_categories()
    queries = get_sample_queries()
    document_counts = get_all_document_counts()

    return render_template(
        "index.html",
        categories=categories,
        queries=queries,
        document_counts=document_counts
    )


@app.route("/load-data", methods=["POST"])
def load_data():
    """Load sample documents with embeddings into all three containers using parallel processing."""
    try:
        data = load_json_file("sample_vectors.json")
        documents = data.get("documents", [])

        # Use bulk loader with parallel processing for faster uploads
        result = bulk_load_documents(documents)
        loaded_count = result["loaded_count"]
        total_ru = result["total_ru"]

        flash(
            f"Loaded {loaded_count} documents to all containers. "
            f"RU costs - flat: {total_ru['flat']:.2f}, "
            f"quantizedFlat: {total_ru['quantizedFlat']:.2f}, "
            f"diskANN: {total_ru['diskANN']:.2f}",
            "success"
        )
    except Exception as e:
        flash(f"Error loading data: {str(e)}", "error")

    return redirect(url_for("index"))


@app.route("/compare-search", methods=["POST"])
def compare_search():
    """Run vector similarity search against all containers and compare results."""
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

        # Run comparison across all three containers
        comparison = compare_index_performance(query["embedding"], top_n)

        categories = get_all_categories()
        all_queries = get_sample_queries()
        document_counts = get_all_document_counts()

        return render_template(
            "index.html",
            categories=categories,
            queries=all_queries,
            document_counts=document_counts,
            comparison_result=comparison,
            comparison_query=query["description"],
            comparison_top_n=top_n
        )
    except Exception as e:
        flash(f"Error performing comparison: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/compare-filtered", methods=["POST"])
def compare_filtered():
    """Run filtered vector search against all containers and compare."""
    query_id = request.form.get("filtered_query_id", "").strip()
    category = request.form.get("filter_category", "").strip()
    top_n = int(request.form.get("filtered_top_n", 5))

    if not query_id:
        flash("Please select a query", "error")
        return redirect(url_for("index"))

    try:
        queries = get_sample_queries()
        query = next((q for q in queries if q["id"] == query_id), None)

        if not query:
            flash("Query not found", "error")
            return redirect(url_for("index"))

        # Run filtered comparison across all containers
        comparison = compare_filtered_performance(
            query["embedding"],
            category=category if category else None,
            top_n=top_n
        )

        categories = get_all_categories()
        all_queries = get_sample_queries()
        document_counts = get_all_document_counts()

        return render_template(
            "index.html",
            categories=categories,
            queries=all_queries,
            document_counts=document_counts,
            filtered_result=comparison,
            filtered_query=query["description"],
            filtered_category=category,
            filtered_top_n=top_n
        )
    except Exception as e:
        flash(f"Error performing filtered comparison: {str(e)}", "error")
        return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
