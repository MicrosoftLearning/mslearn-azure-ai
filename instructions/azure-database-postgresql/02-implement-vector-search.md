---
lab:
    topic: Azure Database for PostgreSQL
    title: 'Implement vector search on Azure Database for PostgreSQL'
    description: 'Learn how to implement vector similarity search using PostgreSQL and the pgvector extension'
---

# Implement vector search on Azure Database for PostgreSQL

In this exercise, you build a product similarity search application using Azure Database for PostgreSQL and the pgvector extension. You enable vector storage capabilities, create a database schema for products with embeddings, load sample data through a Flask web application, and perform similarity searches to find related products. This pattern provides a foundation for building recommendation systems, semantic search features, and other AI-powered applications.

Tasks performed in this exercise:

- Download project starter files and configure the deployment script
- Deploy an Azure Database for PostgreSQL Flexible Server with Microsoft Entra authentication
- Complete the Flask application code while the server deploys
- Enable the pgvector extension and create the products table schema
- Run the Flask application to load products and perform similarity searches
- Add new products and observe how similarity results change

This exercise takes approximately **30** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription with the permissions to deploy the necessary Azure services. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- [PostgreSQL command-line tools](https://www.postgresql.org/download/) (**psql**)

## Download project starter files and deploy Azure services

In this section you download the project starter files and use a script to deploy the necessary services to your Azure subscription. The PostgreSQL server deployment takes a few minutes to complete.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/postgresql-vector-search-python.zip
    ```

1. Copy, or move, the file to a location in your system where you want to work on the project. Then unzip the file into a folder.

1. Launch Visual Studio Code (VS Code) and select **File > Open Folder...** in the menu, then choose the folder containing the project files.

1. The project contains deployment scripts for both Bash (*azdeploy.sh*) and PowerShell (*azdeploy.ps1*). Open the appropriate file for your environment and change the two values at the top of the script to meet your needs, then save your changes. **Note:** Do not change anything else in the script.

    ```
    "<your-resource-group-name>" # Resource Group name
    "<your-azure-region>" # Azure region for the resources
    ```

1. In the menu bar select **Terminal > New Terminal** to open a terminal window in VS Code.

1. Run the following command to login to your Azure account. Answer the prompts to select your Azure account and subscription for the exercise.

    ```
    az login
    ```

1. Run the following command to ensure your subscription has the necessary resource provider for the exercise.

    ```azurecli
    az provider register --namespace Microsoft.DBforPostgreSQL
    ```

### Create resources in Azure

In this section you run the deployment script to deploy the PostgreSQL server and configure authentication.

1. Make sure you are in the root directory of the project and run the appropriate command in the terminal to launch the deployment script.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

1. When the script menu appears, enter **1** to launch the **Create PostgreSQL server with Entra authentication** option. This creates the server with Entra-only authentication enabled. **Note:** Deployment can take 5-10 minutes to complete.

    >**IMPORTANT:** Leave the terminal running the deployment open for the duration of the exercise. You can move on to the next section of the exercise while the deployment continues in the terminal.

## Complete the client application

In this section you complete the *app.py* file by adding route handlers that interact with the PostgreSQL database. These routes handle loading sample products, performing similarity searches, and adding new products. The Flask application provides a web interface for testing vector similarity search.

1. Open the *client/app.py* file in VS Code.

1. Search for the **BEGIN LOAD DATA SECTION** comment and add the following code directly after the comment. This route loads products from a JSON file and inserts them into the database with their embeddings.

    ```python
    @app.route("/load-data", methods=["POST"])
    def load_data():
        """Load sample products into the database."""
        try:
            products = load_json_file("sample_products.json")

            with get_connection() as conn:
                with conn.cursor() as cur:
                    for product in products:
                        # Check if product already exists
                        cur.execute("SELECT id FROM products WHERE name = %s", (product["name"],))
                        if cur.fetchone():
                            continue

                        # Format embedding as PostgreSQL array (pgvector expects bracket notation)
                        embedding_str = "[" + ",".join(str(x) for x in product["embedding"]) + "]"

                        cur.execute("""
                            INSERT INTO products (name, category, description, price, embedding)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (
                            product["name"],
                            product["category"],
                            product["description"],
                            product["price"],
                            embedding_str
                        ))
                    # Commit all inserts in a single transaction
                    conn.commit()

            flash(f"Successfully loaded {len(products)} sample products!", "success")
        except Exception as e:
            flash(f"Error loading data: {str(e)}", "error")

        return redirect(url_for("index"))
    ```

1. Search for the **BEGIN SEARCH SECTION** comment and add the following code directly after the comment. This route retrieves the embedding for a selected product and finds similar products using cosine distance.

    ```python
    @app.route("/search", methods=["POST"])
    def search():
        """Find products similar to the selected product using vector similarity."""
        product_id = request.form.get("product_id")

        if not product_id:
            flash("Please select a product", "error")
            return redirect(url_for("index"))

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # Get the embedding for the selected product
                    cur.execute("SELECT embedding FROM products WHERE id = %s", (product_id,))
                    row = cur.fetchone()

                    if not row:
                        flash("Product not found", "error")
                        return redirect(url_for("index"))

                    # Find similar products using cosine distance
                    # The <=> operator is pgvector's cosine distance operator
                    # Lower distance = more similar (0 = identical, 2 = opposite)
                    cur.execute("""
                        SELECT id, name, category, description, price, embedding <=> %s AS distance
                        FROM products
                        WHERE id != %s
                        ORDER BY distance
                        LIMIT 5
                    """, (row[0], product_id))

                    results = [
                        {"id": r[0], "name": r[1], "category": r[2], "description": r[3], "price": r[4], "distance": r[5]}
                        for r in cur.fetchall()
                    ]

            products = get_products()
            new_products = get_new_products()
            return render_template("index.html", products=products, new_products=new_products, results=results)

        except Exception as e:
            flash(f"Error searching: {str(e)}", "error")
            return redirect(url_for("index"))
    ```

1. Search for the **BEGIN ADD PRODUCT SECTION** comment and add the following code directly after the comment. This route adds a product from the *new_products.json* file to the database.

    ```python
    @app.route("/add-product", methods=["POST"])
    def add_product():
        """Add a new product from the new_products.json file."""
        product_index = request.form.get("product_index")

        if product_index is None or product_index == "":
            flash("Please select a product to add", "error")
            return redirect(url_for("index"))

        try:
            new_products = load_json_file("new_products.json")
            product = new_products[int(product_index)]

            with get_connection() as conn:
                with conn.cursor() as cur:
                    # Check if product already exists
                    cur.execute("SELECT id FROM products WHERE name = %s", (product["name"],))
                    if cur.fetchone():
                        flash(f"Product '{product['name']}' already exists", "error")
                        return redirect(url_for("index"))

                    # Format embedding as PostgreSQL array
                    embedding_str = "[" + ",".join(str(x) for x in product["embedding"]) + "]"

                    cur.execute("""
                        INSERT INTO products (name, category, description, price, embedding)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        product["name"],
                        product["category"],
                        product["description"],
                        product["price"],
                        embedding_str
                    ))
                    conn.commit()

            flash(f"Successfully added '{product['name']}'!", "success")
        except Exception as e:
            flash(f"Error adding product: {str(e)}", "error")

        return redirect(url_for("index"))
    ```

1. Save your changes to the *app.py* file.

1. Take a few minutes to review all of the code in the app. Notice how each route uses the **get_connection()** function to connect to PostgreSQL with Microsoft Entra authentication, and how the **\<=>** operator performs cosine distance calculations for similarity search.

## Complete the Azure resource deployment and create the schema

In this section you enable the pgvector extension and create the products table with a vector column for storing embeddings. The schema includes columns for product details and a 384-dimensional embedding vector used for similarity searches.

1. Wait for the PostgreSQL server to display the deployment is complete in the terminal.

1. In the deployment script menu, enter **2** to configure Microsoft Entra authentication. This sets your Azure account as the database administrator.

1. When the previous operation completes, enter **3** to launch the **Check deployment status** option. This verifies the server is ready.

1. Enter **4** to launch the **Retrieve connection info and access token** option. This creates a file with the necessary environment variables.

1. Enter **5** to exit the deployment script.

1. Run the following command to load the environment variables into your terminal session from the file created in a previous step.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

1. Run the following command to connect to the PostgreSQL server using **psql**. The command uses the environment variables you loaded in the previous step.

    ```bash
    psql "host=$DB_HOST dbname=$DB_NAME user=$DB_USER sslmode=require"
    ```

1. Enable the pgvector extension. This extension must be enabled before you can use vector data types.

    ```sql
    CREATE EXTENSION IF NOT EXISTS vector;
    ```

1. Create the products table with a vector column for embeddings. The embeddings column uses 384 dimensions, which matches common sentence transformer models.

    ```sql
    CREATE TABLE products (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT,
        description TEXT,
        price NUMERIC(10, 2),
        embedding vector(330)
    );
    ```

1. Create an HNSW index to enable fast similarity searches. This index type is optimized for approximate nearest neighbor queries on vector data.

    ```sql
    CREATE INDEX products_embedding_idx
    ON products USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
    ```

1. Verify the table and index were created by listing the table structure.

    ```sql
    \d products
    ```

    You should see the table structure with columns for id, name, category, description, price, and embedding, plus the HNSW index.

1. Enter **quit** to exit the session.


## Set up and run the Flask application

In this section you install the Python dependencies and run the Flask web application. The application provides a browser interface for loading products, searching for similar items, and adding new products to the database.

1. Run the following command to navigate to the *client* folder.

    ```
    cd client
    ```

1. Run the following command to create a Python virtual environment. Depending on your environment the command might be **python** or **python3**.

    ```
    python -m venv .venv
    ```

1. Run the following command to activate the Python environment. **Note:** On Linux/macOS, use the Bash command. On Windows, use the PowerShell command. If using Git Bash on Windows, use **source .venv/Scripts/activate**.

    **Bash**
    ```bash
    source .venv/bin/activate
    ```

    **PowerShell**
    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

1. Run the following command to install the required Python packages. The *requirements.txt* file includes **flask** for the web framework, **psycopg** for PostgreSQL connectivity, and **azure-identity** for authentication.

    ```bash
    pip install -r requirements.txt
    ```

1. Run the Flask application. The application starts on port 5000 and is accessible from your browser.

    ```bash
    python app.py
    ```

    You should see output indicating the Flask server is running:
    ```
    * Running on all addresses (0.0.0.0)
    * Running on http://127.0.0.1:5000
    ```

1. Open a web browser and navigate to `http://127.0.0.1:5000`. You should see the Vector Search Demo page with an empty product list.

## Load products and perform similarity searches

In this section you use the web application to load sample products into the database and perform similarity searches. The products include pre-computed embeddings that represent each product's semantic meaning, enabling the application to find similar items based on their descriptions.

1. On the web page, select **Load Sample Products**. This inserts 10 products with their embeddings into the database.

    You should see a success message and the product list now displays items like "Wireless Bluetooth Headphones", "Gaming Laptop", and "Running Shoes".

1. In the **Find Similar Products** section, select **Wireless Bluetooth Headphones** from the dropdown and select **Find Similar**.

    The application queries the database using vector similarity and returns products ordered by their semantic closeness to the selected item. You should see "Noise Cancelling Earbuds" near the top of the results since it's semantically similar (both are audio devices).

1. Try selecting different products and observe how the similar products change based on the selected item's category and description.

## Add new products and observe changes

In this section you add new products to the database and observe how they appear in similarity search results. This demonstrates how the vector search adapts as your data changes.

1. Return to the web browser with the Flask application.

1. In the **Add New Product** section, select **Espresso Machine** from the dropdown and select **Add Product**.

1. Now search for products similar to **Coffee Maker** by selecting it in the **Find Similar Products** dropdown and selecting **Find Similar**.

    Notice that "Espresso Machine" now appears in the results with a low distance score, since both products are semantically related (home coffee appliances).

1. Add the remaining products from the dropdown (**Wireless Gaming Mouse** and **Fitness Tracker Band**) and observe how they appear in similarity searches for related products.

## Summary

In this exercise, you built a product similarity search application using Azure Database for PostgreSQL and the pgvector extension. You deployed a PostgreSQL Flexible Server with Microsoft Entra authentication, enabled the pgvector extension, and created a products table with a 384-dimensional vector column for storing embeddings. You added an HNSW index to optimize similarity queries, then used a Flask web application to load sample products and perform vector similarity searches using the cosine distance operator (**\<=>**). This pattern demonstrates how to build recommendation systems and semantic search features that find related items based on their semantic meaning rather than exact keyword matches.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues during this exercise, try these steps:

**psql connection fails**
- Ensure the *.env* file was created by running the deployment script option **4**
- Ensure you ran **source .env** (Bash) or **. .\.env.ps1** (PowerShell) to load environment variables
- The access token expires after approximately one hour; run the deployment script option **4** again to generate a new token
- Verify the server is ready by running the deployment script option **3**

**Access denied or authentication errors**
- Ensure the Microsoft Entra administrator was configured by running the deployment script option **2**
- Verify **PGPASSWORD** is set correctly in your terminal session
- Ensure you're using the correct **DB_USER** value (your Azure account email)

**Flask application fails to start**
- Ensure Python virtual environment is activated (you should see **(.venv)** in your terminal prompt)
- Ensure dependencies are installed: **pip install -r requirements.txt**
- Verify all three route functions were added to *app.py* correctly

**Database connection errors in Flask**
- Ensure environment variables are loaded in the terminal running Flask
- Verify the products table exists by connecting with **psql** and running **\d products**
- Ensure the pgvector extension is enabled: **CREATE EXTENSION IF NOT EXISTS vector;**

**No products appear after loading**
- Check the Flask terminal for error messages
- Verify the *sample_products.json* file exists in the *client* folder
- Ensure the products table was created with the correct schema

**Python venv activation issues**
- On Linux/macOS, use: **source .venv/bin/activate**
- On Windows PowerShell, use: **.\.venv\Scripts\Activate.ps1**
- If using Git Bash on Windows, use: **source .venv/Scripts/activate**
