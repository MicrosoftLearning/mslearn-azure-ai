"""
Flask application demonstrating vector similarity search with PostgreSQL and pgvector.
"""
import json
import os
from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg
from azure.identity import DefaultAzureCredential

app = Flask(__name__)
app.secret_key = os.urandom(24)


def get_connection():
    """Create a database connection using Microsoft Entra authentication."""
    host = os.environ.get("DB_HOST")
    dbname = os.environ.get("DB_NAME", "postgres")
    user = os.environ.get("DB_USER")

    if not host or not user:
        raise ValueError("DB_HOST and DB_USER environment variables must be set")

    # Get access token using DefaultAzureCredential
    credential = DefaultAzureCredential()
    token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")

    conn = psycopg.connect(
        host=host,
        dbname=dbname,
        user=user,
        password=token.token,
        sslmode="require"
    )
    return conn


def load_json_file(filename):
    """Load products from a JSON file."""
    filepath = os.path.join(os.path.dirname(__file__), filename)
    with open(filepath, "r") as f:
        data = json.load(f)
    return data.get("products", [])


def get_products():
    """Retrieve all products from the database."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, category, description, price
                    FROM products
                    ORDER BY name
                """)
                rows = cur.fetchall()
                return [
                    {"id": r[0], "name": r[1], "category": r[2], "description": r[3], "price": r[4]}
                    for r in rows
                ]
    except Exception:
        return []


def get_new_products():
    """Load new products from JSON file that aren't in the database."""
    new_products = load_json_file("new_products.json")
    existing = {p["name"] for p in get_products()}
    return [(i, p) for i, p in enumerate(new_products) if p["name"] not in existing]


@app.route("/")
def index():
    """Display the main page with products and search form."""
    products = get_products()
    new_products = get_new_products()
    return render_template("index.html", products=products, new_products=new_products, results=None)

# BEGIN LOAD DATA SECTION



# END LOAD DATA SECTION

# BEGIN SEARCH SECTION



# END SEARCH SECTION

# BEGIN ADD PRODUCT SECTION



# END ADD PRODUCT SECTION

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
