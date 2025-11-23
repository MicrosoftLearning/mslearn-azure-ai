---
lab:
    topic: Azure Managed Redis
    title: 'Vector storage'
    description: 'Learn how to build ... in Azure Managed Redis using the redis-py Python library.'
---

# Publish and subscribe to events in Azure Managed Redis

In this exercise, you create an Azure Managed Redis resource and complete the code for a console-based publisher and a subscriber app. The publisher app sends event messages to Redis channels, while the subscriber app listens for those messages using a graphical interface built with **tkinter**. You implement core pub/sub patterns including direct channel subscriptions, wildcard pattern matching, message formatting, and background message listening.

Tasks performed in this exercise:

- Download the project starter files
- Create an Azure Managed Redis resource
- Add code to complete business logic
- Run the apps to load, store, and search vector data

This exercise takes approximately **40** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- The latest version of the [Azure CLI](/cli/azure/install-azure-cli?view=azure-cli-latest).
- The Azure CLI **redisenterprise** extension. You can install it by running the **az extension add --name redisenterprise** command.

## Download project starter files and deploy Azure Managed Redis

In this section you download the starter files for the console app and use a script to initialize the deployment of Azure Managed Redis to your subscription. The Azure Managed Redis deployment takes 5-10 minutes to complete.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/amr-pub-sub-python.zip
    ```

1. Copy, or move, the file to a location in your system where you want to work on the project. Then unzip the file into a folder.

1. Launch Visual Studio Code (VS Code) and select **File > Open Folder...** in the menu, then choose the folder containing the project files.

1. The project contains deployment scripts for both Bash (*azdeploy.sh*) and PowerShell (*azdeploy.ps1*). Open the appropriate file for your environment and change the two values at the top of script to meet your needs, then save your changes. **Note:** Do not change anything else in the script.

    ```
    "<your-resource-group-name>" # Resource Group name
    "<your-azure-region>" # Azure region for the resources
    ```

1. In the menu bar select **Terminal > New Terminal** to open a terminal window in VS Code.

1. Run the following command to login to your Azure account. Answer the prompts to select your Azure account and subscription for the exercise.

    ```
    az login
    ```

1. Run the following command to install the **redisenterprise** extension for Azure CLI.

    ```
    az extension add --name redisenterprise
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

1. When the script is running, enter **1** to launch the **1. Create Azure Managed Redis resource** option.

    This option creates the resource group if it doesn't already exist, and starts a deployment of Azure Managed Redis. The process is completed as a background task in Azure.

1. After the following messages appear in the console, select **Enter** to return to the menu and then select **4** to exit the script. You run the script again later to check on the deployment status and also to create the *.env* file for the project.

    *The Azure Managed Redis resource is being created and takes 5-10 minutes to complete.*

    *You can check the deployment status from the menu later in the exercise.*


## Configure the Python environment

In this section, you create the Python environment and install the dependencies.

1. Run the following command in the VS Code terminal to create the Python environment.

    ```
    python -m venv .venv
    ```

1. Run the following command in the VS Code terminal to activate the Python environment.

    **Bash**
    ```bash
    source .venv/Scripts/activate
    ```

    **PowerShell**
    ```powershell
    .venv\Scripts\Activate.ps1
    ```

    >**Note:** You may need to modify the commands for your environment. The *Scripts* folder may be *bin* depending on your operating system.

1. Run the following command in the VS Code terminal to install the dependencies.

    ```
    pip install -r requirements.txt
    ```

## Complete the manage vector app

In this section you add code to the *manage_vector.py* script to complete the console app. You run the app later in the exercise, after you confirm the Azure Managed Redis resource is fully deployed and create the *.env* file.

1. Open the *manage_vector.py* file to begin adding code.

>**Note:** The code blocks you add to the application should align with the comment for that section of the code.

### Add the store vector code


1. Locate the **# BEGIN STORE VECTOR CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def store_vector(self, vector_key: str, vector: list, metadata: dict = None) -> tuple[bool, str]:
        """Store a vector with metadata in Redis using hash data structure"""
        try:
            # Convert vector to JSON string for storage
            vector_json = json.dumps(vector)
            data = {"vector": vector_json}  # Store vector as JSON

            # Add metadata fields to the hash
            if metadata:
                for key, value in metadata.items():
                    data[key] = str(value)

            # Store the hash in Redis using hset() method
            result = self.r.hset(vector_key, mapping=data)

            if result > 0:
                return True, f"Vector stored successfully under key '{vector_key}'"
            else:
                return True, f"Vector updated successfully under key '{vector_key}'"

        except Exception as e:
            return False, f"Error storing vector: {e}"
    ```

1. Save your changes.

### Add the retrieve vector code



1. Locate the **# BEGIN PUBLISH MESSAGE CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def publish_order_created(r: redis.Redis) -> None:
        """Publish an order created event using r.publish() to the 'orders:created' channel"""
        clear_screen()
        print("=" * 60)
        print("Publishing: Order Created Event")
        print("=" * 60)

        order_data = {
            "event": "order_created",
            "order_id": f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "customer": "Jane Doe",
            "total": 129.99,
            "timestamp": datetime.now().isoformat()
        }

        message = json.dumps(order_data)
        channel = "orders:created"

        # Publish message and get subscriber count
        subscribers = r.publish(channel, message)  # Send message to channel, returns number of subscribers that received it

        print(f"\n[>] Published to channel: '{channel}'")
        print(f"[#] Active subscribers: {subscribers}")
        print(f"\n[i] Message content:")
        print(json.dumps(order_data, indent=2))

        input("\n[+] Press Enter to continue...")
    ```

1. Save your changes.

### Add the similarity calculation code



1. Locate the **# BEGIN SIMILARITY CALCULATION CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    @staticmethod
    def calculate_similarity(vector1: list, vector2: list) -> float:
        """Calculate cosine similarity between two vectors using numpy array operations"""
        try:
            # Convert lists to numpy arrays with float64 precision
            v1 = np.array(vector1, dtype=np.float64)
            v2 = np.array(vector2, dtype=np.float64)

            # Check for dimension mismatch
            if v1.shape != v2.shape:
                return 0.0

            # Calculate dot product: a·b
            dot_product = np.dot(v1, v2)

            # Calculate magnitudes (norms): ||a|| and ||b||
            magnitude1 = np.linalg.norm(v1)
            magnitude2 = np.linalg.norm(v2)

            # Handle zero-magnitude vectors
            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0

            # Cosine similarity formula: (a·b) / (||a|| * ||b||)
            # Result ranges from -1 to 1 (1 = identical, -1 = opposite, 0 = perpendicular)
            similarity = dot_product / (magnitude1 * magnitude2)
            return float(similarity)
        except Exception:
            return 0.0
    ```

1. Save your changes.

### Add the vector search code



1. Locate the **# BEGIN VECTOR SEARCH CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def search_similar_vectors(self, query_vector: list, top_k: int = 3) -> tuple[bool, list | str]:
        """Search for vectors similar to the query vector using cosine similarity"""
        try:
            # Retrieve all vector keys from Redis using pattern matching
            vector_keys = self.r.keys("vector:*")

            if not vector_keys:
                return False, "No vectors found in Redis"

            similarities = []

            # Calculate similarity score for each stored vector
            for key in vector_keys:
                vector_data = self.r.hgetall(key)  # Retrieve vector and metadata
                if "vector" in vector_data:
                    stored_vector = json.loads(vector_data["vector"])  # Parse vector from JSON
                    similarity = self.calculate_similarity(query_vector, stored_vector)  # Calculate similarity score

                    # Extract metadata
                    metadata = {k: v for k, v in vector_data.items() if k != "vector"}
                    similarities.append({
                        "key": key,
                        "similarity": similarity,
                        "metadata": metadata
                    })

            # Sort by similarity score in descending order and return top_k results
            similarities.sort(key=lambda x: x["similarity"], reverse=True)
            return True, similarities[:top_k]

        except Exception as e:
            return False, f"Error searching vectors: {e}"
    ```

1. Save your changes.

### Review the code

Take a few minutes to review all of the code in the *manage_vector.py* file.

## Verify resource deployment

In this section you run the deployment script again to verify if the Azure Managed Redis deployment is completed, and create the *.env* file with the endpoint and access key values.

1. Run the appropriate command in the terminal to start the deployment script. If you closed the previous terminal, select **Terminal > New Terminal** in the menu to open a new one.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

1. When the deployment menu appears, enter **2** to run the **2. Check deployment status** option. If the status **Successful** returned proceed to the next step. If not, then wait a few minutes and try the option again.

1. After the deployment is complete, enter **3** to run the **3. Enable access key auth and retrieve endpoint and access key** option. This will query the Azure Managed Redis resource and retrieve the endpoint and access key. It then creates the *.env* file with those values.

1. Review the *.env* file to verify the values are present, then enter **4** to exit the deployment script.

## Run the app

In this section, you run the completed application and practice loading, storing, searching, vector data.The app uses **tkinter** to create a GUI so you can more easily view and manage data.

1. Run the following command in the terminal to start the app. Refer to the commands from earlier in the exercise to activate the environment, if needed, before running the command.

    ```
    python vectorapp.py
    ```

    The app should look similar to the following image:

    ![Screenshot of the vector app running.](./media/vector-app.png)

### Send and receive messages

You need to first subscribe to a channel before you can receive messages.

1. In the subscriber app, select **Subscribe to Channel**. Enter **orders:created** in the channel name input box and select **Subscribe**.

    You should see a *Subscribed to channel: 'orders:created'* message  in the **Received Messages** area. Next you publish a message.

1. In the publisher app, enter **1** to publish an order created event. You should see an event was published successfully to the channel.

    ```
    [>] Published to channel: 'orders:created'
    [#] Active subscribers: 1

    [i] Message content:
    {
      "event": "order_created",
      "order_id": "ORD-20251120123114",
      "customer": "Jane Doe",
      "total": 129.99,
      "timestamp": "2025-11-20T12:31:14.906797"
    }
    ```

    The message should appear in the **Received Messages** section of the subscriber app.

    ```
    [12:31:14] Message on 'orders:created'
    ──────────────────────────────────────────────────
    Event: order_created
    Order ID: ORD-20251120123114
    Customer: Jane Doe
    Total: $129.99
    ──────────────────────────────────────────────────
    ```

1. In the publisher app, enter **2** to publish an **Order Shipped** event. The event will be sent, but it will not appear in the subscriber app because you only subscribed to the **orders:created** channel.

### Experiment with other subscription/publishing options

Take some time to experiment subscribing and publishing messages to different channels. Following is a table with details on each of the subscriber options:

| Subscriber Option | Description |
|--|--|
| Subscribe to Channel | Subscribes to a single channel. The channel options are listed in the dialog box. |
| Subscribe with Pattern | Subscribe to multiple channels. For example, subscribing with the **orders:*** pattern subscribes to all **orders** channels. |
| Unsubscribe from Channel | Unsubscribe from a single channel. Note: you can't unsubscribe using a pattern using this option. |
| Unsubscribe All | Unsubscribe from all channels, including pattern subscriptions. |
| View Active Subscriptions | Lists all of the subscribed channels, including pattern subscriptions. |

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
- Check that the resource has **Public network access** enabled and **Access keys authentication** set to **Enabled**.

**Check code completeness and indentation**
- Ensure all code blocks were added to the correct sections and between the appropriate BEGIN/END comment markers.
- Verify that Python indentation is consistent (use spaces, not tabs) and that all code aligns properly within functions.
- Confirm that no code was accidentally removed or modified outside the designated sections.

**Verify environment variables**
- Check that the *.env* file exists in the project folder and contains valid **REDIS_HOST** and **REDIS_KEY** values.
- Ensure the *.env* file is in the root of the project.

**Check Python environment and dependencies**
- Confirm the virtual environment is activated before running the app.
- Verify that all packages from *requirements.txt* were installed successfully by running **pip list**.

