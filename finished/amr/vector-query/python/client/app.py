"""Flask app for vector storage and similarity search with Azure Managed Redis."""
import logging
import os
import threading

from flask import Flask, flash, redirect, render_template, request, url_for

from vector_functions import VectorManager

app = Flask(__name__)
app.secret_key = os.urandom(24)

_manager = None
_manager_lock = threading.Lock()


def get_manager() -> VectorManager:
    """Create a single shared VectorManager instance on first use."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = VectorManager()
        return _manager


def parse_embedding(embedding_text: str) -> list[float]:
    """Parse embedding input from the textarea into a float list."""
    value = embedding_text.strip().lstrip("[").rstrip("]").strip()
    if not value:
        raise ValueError("Embedding cannot be empty")
    return [float(item.strip()) for item in value.split(",")]


def parse_metadata(metadata_text: str) -> dict[str, str]:
    """Parse metadata lines in key=value format."""
    metadata: dict[str, str] = {}
    for line in metadata_text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        metadata[key.strip()] = value.strip()
    return metadata


@app.route("/")
def index():
    """Render the main page."""
    return render_template("index.html")


@app.route("/load-sample", methods=["POST"])
def load_sample():
    """Load sample vectors from sample_data.json."""
    try:
        success, message = get_manager().load_sample_products()
        if success:
            flash(message, "success")
        else:
            flash(message, "error")
    except Exception as e:
        flash(f"Error loading sample products: {e}", "error")
    return redirect(url_for("index"))


@app.route("/list-products", methods=["POST"])
def list_products():
    """List all product keys currently stored."""
    products = []
    try:
        success, result = get_manager().list_all_products()
        if success:
            products = result
            flash(f"Found {len(products)} product(s).", "success")
        else:
            flash(result, "error")
    except Exception as e:
        flash(f"Error listing products: {e}", "error")

    return render_template("index.html", products=products)


@app.route("/store-product", methods=["POST"])
def store_product():
    """Store or update a product vector and metadata."""
    key = request.form.get("product_key", "").strip()
    embedding_text = request.form.get("embedding", "").strip()
    metadata_text = request.form.get("metadata", "").strip()

    if not key or not embedding_text:
        flash("Product key and embedding are required.", "error")
        return redirect(url_for("index"))

    try:
        vector = parse_embedding(embedding_text)
        metadata = parse_metadata(metadata_text)
        success, message = get_manager().store_product(key, vector, metadata if metadata else None)

        if success:
            flash(message, "success")
            store_result = {
                "key": key,
                "embedding": vector,
                "metadata": metadata,
            }
            return render_template("index.html", store_result=store_result)

        flash(message, "error")
        return redirect(url_for("index"))
    except ValueError as e:
        flash(f"Invalid embedding format: {e}", "error")
        return redirect(url_for("index"))
    except Exception as e:
        flash(f"Error storing product: {e}", "error")
        return redirect(url_for("index"))


@app.route("/search-similar", methods=["POST"])
def search_similar():
    """Find products similar to the selected product key."""
    product_key = request.form.get("query_key", "").strip()
    top_k = request.form.get("top_k", default=5, type=int)
    top_k = max(1, min(10, top_k))

    if not product_key:
        flash("A product key is required for search.", "error")
        return redirect(url_for("index"))

    try:
        manager = get_manager()
        found, source = manager.retrieve_product(product_key)
        if not found or not isinstance(source, dict):
            flash(f"Product not found: {product_key}", "error")
            return redirect(url_for("index"))

        success, results = manager.search_similar_products(source["vector"], top_k)
        if not success:
            flash(results, "error")
            return redirect(url_for("index"))

        filtered = [r for r in results if r["key"] != product_key]
        flash(f"Found {len(filtered)} similar product(s) for {product_key}.", "success")
        return render_template(
            "index.html",
            query_product=source,
            search_results=filtered,
            top_k=top_k,
        )
    except Exception as e:
        flash(f"Error searching similar products: {e}", "error")
        return redirect(url_for("index"))


@app.route("/remove-product", methods=["POST"])
def remove_product():
    """Remove one product key from Redis."""
    product_key = request.form.get("remove_key", "").strip()
    if not product_key:
        flash("A product key is required to remove a product.", "error")
        return redirect(url_for("index"))

    try:
        success, message = get_manager().remove_product(product_key)
        if success:
            flash(message, "success")
        else:
            flash(message, "error")
    except Exception as e:
        flash(f"Error removing product: {e}", "error")

    return redirect(url_for("index"))


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(" * Running on http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
