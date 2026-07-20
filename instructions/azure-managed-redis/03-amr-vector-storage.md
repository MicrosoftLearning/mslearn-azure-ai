---
lab:
  topic: Azure Managed Redis
  title: Implement semantic search in Azure Managed Redis
  description: Learn how to store product vectors with embeddings, create semantic search indexes, and perform similarity searches in Azure Managed Redis using redis-py and RediSearch.
  level: 300
  duration: 30
  islab: true
  primarytopics:
    - Azure
    - Azure Managed Redis
---

# Implement semantic search in Azure Managed Redis

In this exercise, you deploy Azure Managed Redis and complete a Python Flask web app that stores product embeddings and metadata, creates a vector index, and performs similarity search using cosine distance. You add code to connect with Microsoft Entra ID, create the index, store product vectors, and query for similar products from a browser-based interface.

Tasks performed in this exercise:

- Download the project starter files
- Create an Azure Managed Redis resource
- Add code to the starter files to complete the app
- Run the app to load products, store vectors, and perform similarity searches

This exercise takes approximately **30** minutes to complete.

## Before you start

In this section you review the prerequisites needed for the exercise.

To complete the exercise, you need:

- An Azure subscription. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).
- The Azure CLI **redisenterprise** extension, version 2.75.0 or greater. A later step installs or upgrades the extension for you.

## Download project starter files and deploy Azure Managed Redis

In this section you download the starter files for the app and use a script to initialize the deployment of Azure Managed Redis to your subscription. The Azure Managed Redis deployment takes 5-10 minutes to complete, so you start the deployment first and add code to the app while it provisions.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/amr-vector-query-python.zip
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

1. Run the following command to ensure your subscription has the necessary resource provider for Azure Managed Redis.

    ```
    az provider register --namespace Microsoft.Cache
    ```

1. Run the following command to install or upgrade the **redisenterprise** extension for Azure CLI. Version 2.75.0 or greater is required to configure Microsoft Entra ID access on the database.

    ```
    az extension add --upgrade --name redisenterprise
    ```

1. Run the appropriate command in the terminal to launch the script.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

    > **Note:** If PowerShell blocks the script because it is not digitally signed, run the following command in the same terminal session, then run the deployment script again. This command changes the execution policy only for the current PowerShell process.

    ```powershell
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    ```

1. When the script is running, enter **1** to launch the **1. Create Azure Managed Redis resource** option.

    This option creates the resource group if it doesn't already exist, then deploys Azure Managed Redis. The script waits for the deployment to finish, which takes 5-10 minutes, and reports the result in the terminal. Leave the script running and continue to the next section to add code while the deployment provisions. Check back on the terminal periodically to watch for errors.

    When the deployment succeeds, a confirmation message like the following appears and the menu returns:

    *Azure Managed Redis resource created successfully: amr-exercise-\<hash>*

    > **Note:** If the deployment fails, it's most often due to a temporary lack of capacity for the SKU in your chosen region. Follow the on-screen guidance to exit the script, change the **location** variable near the top of the script to a different region such as eastus2, australiaeast, or canadacentral, then run the script again and choose option 1. The failed resource is deleted automatically before the next attempt.

## Complete the app

In this section you add code to the *client/vector_functions.py* file to complete vector storage and search operations. The Flask app in *client/app.py* calls these functions to execute the workflow from the browser. You don't need to edit *client/app.py*. You run the app later in the exercise.

1. Open the *client/vector_functions.py* file to begin adding code.

>**Note:** The code blocks you add to the application should align with the comment for that section of the code.

### Add code to connect to Azure Managed Redis

In this section you add code to create a Redis client that authenticates with Microsoft Entra ID. Using Entra ID means the app never handles an access key.

The **get_client()** function reads the Redis endpoint from the **REDIS_HOST** environment variable and calls **create_from_default_azure_credential()** to build a credential provider. The provider uses **DefaultAzureCredential** to acquire a Microsoft Entra token and refreshes it automatically in the background.

1. Locate the **# BEGIN CONNECTION CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def get_client() -> redis.Redis:
        """Create a Redis client for Azure Managed Redis using Microsoft Entra ID."""
        redis_host = os.environ.get("REDIS_HOST")

        if not redis_host:
            raise ValueError("REDIS_HOST environment variable must be set")

        credential_provider = create_from_default_azure_credential(
            ("https://redis.azure.com/.default",),
        )

        return redis.Redis(
            host=redis_host,
            port=10000,
            ssl=True,
            decode_responses=False,
            credential_provider=credential_provider,
            socket_timeout=30,
            socket_connect_timeout=30,
        )
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to create the vector index

In this section you add code to create the RediSearch index used by similarity search.

The **_create_vector_index()** function defines text fields and a vector field named **embedding**. The vector field uses the HNSW algorithm with cosine distance and an embedding dimension of 8, matching the sample data.

1. Locate the **# BEGIN CREATE VECTOR INDEX CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def _create_vector_index(self):
        """Create a RediSearch index for product semantic search."""
        try:
            schema = (
                TextField("name"),
                TextField("category"),
                TextField("product_id"),
                VectorField(
                    "embedding",
                    "HNSW",
                    {
                        "TYPE": "FLOAT32",
                        "DIM": VECTOR_DIM,
                        "DISTANCE_METRIC": "COSINE",
                    },
                ),
            )

            definition = IndexDefinition(
                prefix=["product:"],
                index_type=IndexType.HASH,
            )

            self.r.ft(VECTOR_INDEX_NAME).create_index(
                fields=schema,
                definition=definition,
            )
        except redis.ResponseError as e:
            if "already exists" not in str(e):
                raise Exception(f"Error creating vector index: {e}")
        except Exception as e:
            raise Exception(f"Error creating vector index: {e}")
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to store product vectors

In this section you add code to store a product embedding and metadata in Redis.

The **store_product()** function converts the embedding list to **float32** bytes with numpy and writes the embedding plus metadata to a Redis hash using **hset()**.

1. Locate the **# BEGIN STORE PRODUCT CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def store_product(
        self,
        vector_key: str,
        vector: list[float],
        metadata: dict[str, str] | None = None,
    ) -> tuple[bool, str]:
        """Store or update a product hash containing embedding and metadata."""
        try:
            embedding = np.array(vector, dtype=np.float32)
            data: dict[str, Any] = {"embedding": embedding.tobytes()}

            if metadata:
                for key, value in metadata.items():
                    data[key] = str(value)

            result = self.r.hset(vector_key, mapping=data)
            if result > 0:
                return True, f"Product stored successfully under key '{vector_key}'"
            return True, f"Product updated successfully under key '{vector_key}'"
        except Exception as e:
            return False, f"Error storing product: {e}"
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to search similar products

In this section you add code to run KNN similarity search against the vector index.

The **search_similar_products()** function converts the query embedding to bytes, builds a RediSearch KNN query, and returns the closest product matches ordered by score.

1. Locate the **# BEGIN SEARCH SIMILAR PRODUCTS CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def search_similar_products(
        self,
        query_vector: list[float],
        top_k: int = 3,
    ) -> tuple[bool, list[dict[str, Any]] | str]:
        """Run a KNN vector query against product embeddings."""
        try:
            query_bytes = np.array(query_vector, dtype=np.float32).tobytes()

            knn_query = (
                Query(f"*=>[KNN {top_k} @embedding $query_vec AS score]")
                .return_fields("name", "category", "product_id", "score")
                .sort_by("score")
                .dialect(2)
            )

            results = self.r.ft(VECTOR_INDEX_NAME).search(
                knn_query,
                query_params={"query_vec": query_bytes},
            )

            if results.total == 0:
                return False, "No products found in Redis. Load sample products first."

            similarities: list[dict[str, Any]] = []
            for doc in results.docs:
                similarities.append(
                    {
                        "key": doc.id,
                        "similarity": float(doc.score),
                        "product_id": doc.product_id.decode() if isinstance(doc.product_id, bytes) else doc.product_id,
                        "name": doc.name.decode() if isinstance(doc.name, bytes) else doc.name,
                        "category": doc.category.decode() if isinstance(doc.category, bytes) else doc.category,
                    }
                )

            return True, similarities
        except Exception as e:
            return False, f"Error searching products: {e}"
    ```

1. Save your changes and take a few minutes to review the code.

## Verify resource deployment

In this section you return to the deployment script to create the vector database, configure Microsoft Entra ID access, and generate the environment variable file with the Redis endpoint.

1. Return to the terminal where the deployment script is running. After a successful deployment, you see the confirmation message and the menu. If you exited the script, run the appropriate command to start it again.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

1. Enter **2** to run the **2. Create database and configure access** option. This creates the vector-ready database with the RediSearch module, assigns a data access policy to your account, and creates the environment variable file with **REDIS_HOST**.

1. (Optional) Enter **3** to run the **3. Check deployment status** option as a final check.

1. Enter **4** to exit the deployment script.

1. Run the appropriate command to load the environment variables into your terminal session from the file created in the previous step.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

    >**Note:** Keep the terminal open. If you close it and create a new terminal, you need to run this command again to reload the environment variables.

## Configure the Python environment

In this section you navigate to the client directory, create the Python environment, and install the dependencies.

1. Run the following command in the VS Code terminal to navigate to the *client* directory.

    ```
    cd client
    ```

1. Run the following command to create the Python environment.

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

1. Run the following command in the VS Code terminal to install the dependencies.

    ```
    pip install -r requirements.txt
    ```

## Run the app

In this section you run the completed Flask application to perform vector storage and similarity search from a single web page.

1. Run the following command in the terminal to start the app. Refer to the commands from earlier in the exercise to activate the environment and load the environment variables, if needed, before running the command. If you navigated away from the *client* directory, run **cd client** first.

    ```
    python app.py
    ```

1. Open a browser and navigate to `http://localhost:5000` to access the app.

### Load sample data and perform similarity search

In this section you load sample product embeddings and run your first similarity search.

1. In **Data Operations**, select **Load Sample Products**.

1. Select **List All Products** and confirm product keys are displayed in **Operation Results**.

1. In **Similarity Search**, enter **product:001** and leave **top_k** set to **5**, then select **Find Similar**.

1. Review the returned products and their distance scores in **Operation Results**.

### Store a new product and search again

In this section you store a new product embedding and run similarity search again to see how nearest neighbors change.

1. In **Store Product**, enter the following values and select **Store Product**.

    Product key:

    ```
    product:011
    ```

    Embedding:

    ```
    [0.53, 0.63, 0.58, 0.37, 0.68, 0.47, 0.73, 0.57]
    ```

    Metadata:

    ```
    product_id=011
    name=Gym Bag
    category=Sports
    ```

1. In **Similarity Search**, enter **product:009** and select **Find Similar**.

1. Review the results and verify that product similarity ordering reflects the newly stored vector.

### Remove a product

In this section you remove one product key to validate delete behavior.

1. In **Remove Product**, enter **product:011** and select **Remove**.

1. Select **List All Products** and confirm **product:011** no longer appears in the product list.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues while completing this exercise, try the following troubleshooting steps:

**Verify Azure Managed Redis resource deployment**
- Navigate to the [Azure portal](https://portal.azure.com) and locate your resource group.
- Confirm that the Azure Managed Redis resource shows a **Provisioning State** of **Succeeded**.
- Run the deployment script's **Check deployment status** option and confirm the cluster and database are ready before running the app.

**Check authentication and access**
- Confirm you are logged in to Azure CLI by running **az account show**.
- Ensure the deployment script's **Create database and configure access** option completed successfully so your account has a data access policy on the database.
- If the app reports an authentication error, wait a moment and try again, as the access policy assignment can take a short time to take effect.

**Check code completeness and indentation**
- Ensure all code blocks were added to the correct sections in *client/vector_functions.py* between the appropriate BEGIN/END comment markers.
- Verify that Python indentation is consistent (use spaces, not tabs).
- Confirm that no code was accidentally removed or modified outside the designated sections.

**Verify environment variables**
- Check that the *.env* file exists in the project root and contains the **REDIS_HOST** value.
- Ensure you ran **source .env** (Bash) or **. .\.env.ps1** (PowerShell) to load environment variables into your terminal session.
- If variables are empty, run **source .env** (Bash) or **. .\.env.ps1** (PowerShell) again.

**Check Python environment and dependencies**
- Confirm the virtual environment is activated before running the app.
- Verify that all packages from *client/requirements.txt* were installed successfully by running **pip list**.

**No search results or missing products**
- Confirm you loaded sample products before running similarity searches.
- Verify the query product key exists by selecting **List All Products**.
- Ensure embeddings contain 8 numeric values to match the index configuration.
