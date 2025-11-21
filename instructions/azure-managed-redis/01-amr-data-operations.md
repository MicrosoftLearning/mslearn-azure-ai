---
lab:
    topic: Azure Managed Redis
    title: 'Perform data operations in Azure Managed Redis'
    description: 'Learn how to perform data operations in Azure Managed Redis using the redis-py Python library.'
---

# Perform data operations in Azure Managed Redis

In this exercise, you create an Azure Managed Redis resource and build a Python console application that performs common data operations using the **redis-py** library. You work with Redis hash data structures to store and retrieve key-value pairs, manage key expiration with Time-To-Live (TTL) settings, and delete keys from the cache. 

Tasks performed in this exercise:

- Download the project starter files
- Create an Azure Managed Redis resource
- Add code to the starter files to complete the console app
- Run the console app to perform data operations

This exercise takes approximately **30** minutes to complete.

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
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/amr-data-operations-python.zip
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

    >**Note:** You may need to modify the commands for your environment. The *Scripts* folder may be *bin* depending on your operating system.

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

## Complete the app

In this section you add code to the *main.py* script to complete the console app. You run the app later in the exercise, after you confirm the Azure Managed Redis resource is fully deployed and create the *.env* file.

1. Open the *main.py* file to begin adding code.

>**Note:** The code blocks you add to the application should align with the comment for that section of the code.

### Add the client connection

In this section, you add code to establish a connection to Azure Managed Redis using the redis-py library. The code retrieves connection credentials from environment variables and creates a Redis client instance configured for secure SSL communication.

1. Locate the **# BEGIN CONNECTION CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    try:
        # Azure Managed Redis with Non-Clustered policy uses standard Redis connection
        redis_host = os.getenv("REDIS_HOST")
        redis_key = os.getenv("REDIS_KEY")
        
        # Non-clustered policy uses standard Redis client connection
        r = redis.Redis(
            host=redis_host,
            port=10000,  # Azure Managed Redis uses port 10000
            ssl=True,
            decode_responses=True, # Decode responses to strings
            password=redis_key,
            socket_timeout=30,  # Add timeout for better reliability
            socket_connect_timeout=30,
        )
    
        print(f"Connected to Redis at {redis_host}")
        input("\nPress Enter to continue...")
        return r
    ```

### Add code to store and retrieve data

In this section, you add code to work with Redis hash data structures using the **hset** and **hgetall** commands. The **hset** method stores multiple field-value pairs under a single key, while **hgetall** retrieves all fields and values for a given key. 

1. Locate the **# BEGIN STORE AND RETRIEVE CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def store_hash_data(r, key, value) -> None:
        """Store hash data in Redis"""
        clear_screen()
        print(f"Storing hash data for key: {key}")
        result = r.hset(key, mapping=value) # Store hash data
        if result > 0: # New fields were added
            print(f"Data stored successfully under key '{key}' ({result} new fields added)")
        else:
            print(f"Data updated successfully under key '{key}' (all fields already existed)")
        input("\nPress Enter to continue...")
    
    def retrieve_hash_data(r, key) -> None:
        """Retrieve hash data from Redis"""
        clear_screen()
        print(f"Retrieving hash data for key: {key}")
        retrieved_value = r.hgetall(key) # Retrieve hash data
        if retrieved_value:
            print("\nRetrieved hash data:")
            for field, value in retrieved_value.items():
                print(f"  {field}: {value}")
        else:
            print(f"Key '{key}' does not exist.")
    
        input("\nPress Enter to continue...")
    ```

### Add code to set and retrieve expiration

In this section, you add code to manage key expiration using the **expire** and **ttl** commands. The **expire** method sets a Time-To-Live (TTL) on a key, causing it to automatically expire after the specified number of seconds, while **ttl** retrieves the remaining time before a key expires.

1. Locate the **# BEGIN EXPIRATION CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def set_expiration(r, key) -> None:
        """Set an expiration time for a key"""
        clear_screen()
        print("Set expiration time for a key")
        # Set expiration time, 1 hour equals 3600 seconds
        expiration = int(input("Enter expiration time in seconds (default 3600): ") or 3600)
        result = r.expire(key, expiration) # Set expiration time
        if result:
            print(f"Expiration time of {expiration} seconds set for key '{key}'")
        else:
            print(f"Key '{key}' does not exist. Expiration not set.")
    
        input("\nPress Enter to continue...")
    
    def retrieve_expiration(r, key) -> None:
        """Retrieve the TTL of a key"""
        clear_screen()
        print(f"Retrieving the current TTL of {key}...")
        ttl = r.ttl(key) # Get current TTL
        if ttl == -2: # Key does not exist
            print(f"\nKey '{key}' does not exist.")
        elif ttl == -1: # No expiration set
            print(f"\nKey '{key}' has no expiration set (persists indefinitely).")
        else:
            print(f"\nCurrent TTL for '{key}': {ttl} seconds")
        input("\nPress Enter to continue...")
    ```

### Add code to delete data

In this section, you add code to remove keys from Redis using the **delete** command. The **delete** method permanently removes a key and its associated value from the cache, freeing up memory and ensuring the data is no longer accessible.

1. Locate the **# BEGIN DELETE CODE SECTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def delete_key(r, key) -> None:
        """Delete a key"""
        clear_screen()
        print(f"Deleting key: {key}...")
        result = r.delete(key) # Delete the key
        if result == 1:
            print(f"Key '{key}' deleted successfully.")
        else:
            print(f"Key '{key}' does not exist.")
        input("\nPress Enter to continue...")
    ```

1. Save your changes to the *main.py* file.

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

1. When the deployment menu appears, enter **2** to run the **2. Check deployment status** option. If the status shows **Succeeded**, proceed to the next step. If not, then wait a few minutes and try the option again.

1. After the deployment is complete, enter **3** to run the **3. Retrieve endpoint and access key** option. This will query the Azure Managed Redis resource and retrieve the endpoint and access key. It then creates the *.env* file with those values.

1. Review the *.env* file to verify the values are present, then enter **4** to exit the deployment script.

## Run the console app

In this section, you run the completed console application to perform various Redis data operations. The app provides a menu-driven interface that lets you store hash data, retrieve values, manage key expiration, and delete keys.

1. Run the following command in the terminal to start the console app. Refer to the commands from earlier in the exercise to activate the environment if needed.

    ```
    python main.py
    ```

1. The app has the following options. Select the **1. Store hash data** to get started.

    ```
    1. Store hash data
    2. Retrieve hash data
    3. Set expiration
    4. Retrieve expiration (TTL)
    5. Delete key
    6. Exit
    ```

1. Select the remaining options in order to run the different operations.

>**Note:** You can run the options in any order you choose. For example, after storing the hash data you can retrieve the expiration information to learn there is no expiration set on the key.

The mock hash data used in the app is defined in the beginning of the **main()** function. You can update the code to use a different key, or add more values to the hash data.

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
- Ensure all code blocks were added to the correct sections in *main.py* between the appropriate BEGIN/END comment markers.
- Verify that Python indentation is consistent (use spaces, not tabs) and that all code aligns properly within functions.
- Confirm that no code was accidentally removed or modified outside the designated sections.

**Verify environment variables**
- Check that the *.env* file exists in the project folder and contains valid **REDIS_HOST** and **REDIS_KEY** values.
- Ensure the *.env* file is in the same directory as *main.py*.

**Check Python environment and dependencies**
- Confirm the virtual environment is activated before running the app.
- Verify that all packages from *requirements.txt* were installed successfully by running **pip list**.

