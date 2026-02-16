---
lab:
    topic: App secrets and configuration
    title: 'Manage secrets with Azure Key Vault'
    description: 'Learn how to store, retrieve, version, and cache secrets using Azure Key Vault with the Python SDK.'
    level: 200
    duration: 20
---

# Retrieve secrets from Azure Key Vault

AI applications typically depend on sensitive credentials such as API keys, connection strings, and certificates to access model endpoints and data stores. Azure Key Vault provides a centralized, secure store for these secrets with RBAC access control, automatic versioning, and audit logging so applications never need to embed credentials in code or configuration files.

In this exercise, you deploy an Azure Key Vault pre-loaded with sample secrets and build a Python Flask web application that demonstrates core secret management patterns using the Azure SDK. You retrieve secrets and inspect their metadata, list all secret properties without exposing values, create a new secret version to simulate credential rotation, and implement a time-based cache to reduce Key Vault API calls.

Tasks performed in this exercise:

- Download the project starter files
- Create an Azure Key Vault and store sample secrets
- Add code to the starter files to complete the app
- Run the app to perform secret operations

This exercise takes approximately **30** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).

## Download project starter files and deploy Azure Key Vault

In this section you download the starter files for the app and use a script to deploy an Azure Key Vault with sample secrets to your subscription.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/key-vault-python.zip
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

    ```
    az provider register --namespace Microsoft.KeyVault
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

1. When the script is running, enter **1** to launch the **1. Create Key Vault** option.

    This option creates the resource group if it doesn't already exist, and deploys an Azure Key Vault with RBAC authorization enabled. RBAC authorization is the recommended model for controlling access to vault secrets instead of legacy access policies.

1. Enter **2** to run the **2. Assign role** option. This assigns the Key Vault Secrets Officer role to your account so you can read, create, update, and delete secrets using Microsoft Entra authentication.

1. Enter **3** to run the **3. Store secrets** option. This stores two sample secrets in the vault: an API key for a model endpoint (**openai-api-key**) and a database connection string (**cosmosdb-connection-string**). Both are tagged with metadata for environment and service identification.

1. Enter **4** to run the **4. Check deployment status** option. Verify the vault status shows **Succeeded**, the role is assigned, and the secrets are stored before continuing. If the vault is still provisioning, wait a moment and try again.

1. Enter **5** to run the **5. Retrieve connection info** option. This creates the environment variable file with the Key Vault URL needed by the app.

1. Enter **6** to exit the deployment script.

1. Run the appropriate command to load the environment variables into your terminal session from the file created in a previous step.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

    >**Note:** Keep the terminal open. If you close it and create a new terminal, you need to run this command again to reload the environment variables.

## Complete the app

In this section you add code to the *keyvault_functions.py* file to complete the Key Vault secret management functions. The Flask app in *app.py* calls these functions and displays the results in the browser. You run the app later in the exercise.

1. Open the *client/keyvault_functions.py* file to begin adding code.

>**Note:** The code blocks you add to the application should align with the comment for that section of the code.

### Add code to retrieve secrets

In this section, you add code to retrieve two secrets from the vault and return their metadata. The function demonstrates how to access secret values, version identifiers, content types, creation dates, and custom tags.

The function calls **get_secret()** for each secret name, which returns both the secret value and a properties object containing metadata. It handles **ResourceNotFoundError** for missing secrets and **HttpResponseError** for authorization or network issues. The truncated value prevents full credentials from appearing in the UI while still confirming the secret was retrieved.

1. Locate the **# BEGIN RETRIEVE SECRETS FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def retrieve_secrets():
        """Retrieve secrets and display their metadata."""
        client = get_client()
        results = []

        secret_names = ["openai-api-key", "cosmosdb-connection-string"]

        for name in secret_names:
            try:
                # get_secret returns the secret value and its properties,
                # including version, content type, creation date, and tags
                secret = client.get_secret(name)
                results.append({
                    "name": secret.name,
                    "value": secret.value[:20] + "..." if len(secret.value) > 20 else secret.value,
                    "version": secret.properties.version,
                    "content_type": secret.properties.content_type,
                    "created_on": str(secret.properties.created_on),
                    "tags": secret.properties.tags or {},
                    "status": "retrieved"
                })
            except ResourceNotFoundError:
                results.append({
                    "name": name,
                    "value": None,
                    "version": None,
                    "content_type": None,
                    "created_on": None,
                    "tags": {},
                    "status": "not found"
                })
            except HttpResponseError as e:
                results.append({
                    "name": name,
                    "value": None,
                    "version": None,
                    "content_type": None,
                    "created_on": None,
                    "tags": {},
                    "status": f"error: {e.message}"
                })

        return results
    ```

1. Take a few minutes to review the code.

### Add code to list secret properties

In this section, you add code to list the properties of all secrets in the vault without retrieving their values. This follows the principle of least privilege by exposing only metadata such as name, enabled status, content type, and timestamps.

The function calls **list_properties_of_secrets()**, which returns an iterable of secret property objects. Unlike **get_secret()**, this method does not return secret values, making it safe for inventory and audit operations where you need to know what secrets exist without accessing their contents.

1. Locate the **# BEGIN LIST SECRETS FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def list_secret_properties():
        """List all secret properties without retrieving values."""
        client = get_client()
        results = []

        # list_properties_of_secrets returns metadata for every secret
        # in the vault without exposing the secret values, which follows
        # the principle of least privilege
        for prop in client.list_properties_of_secrets():
            results.append({
                "name": prop.name,
                "enabled": prop.enabled,
                "content_type": prop.content_type,
                "created_on": str(prop.created_on),
                "updated_on": str(prop.updated_on)
            })

        return results
    ```

1. Save your changes and take a few minutes to review the code.

### Add code to create a new secret version

In this section, you add code to create a new version of a secret, simulating a credential rotation. The function retrieves the current version, writes a new value with **set_secret()**, and then confirms the update by retrieving the secret again.

The function uses **set_secret()** to write a new value for an existing secret name, which automatically creates a new version while preserving the previous one. Previous versions remain accessible by their version ID, but **get_secret()** without a version parameter always returns the latest. The function also attaches updated tags to the new version for tracking rotation metadata.

1. Locate the **# BEGIN CREATE SECRET VERSION FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def create_secret_version(secret_name, new_value):
        """Create a new version of a secret and verify the update."""
        client = get_client()

        # Retrieve the current version before updating
        try:
            current = client.get_secret(secret_name)
            old_version = current.properties.version
            old_value = current.value[:20] + "..." if len(current.value) > 20 else current.value
        except ResourceNotFoundError:
            old_version = None
            old_value = None

        # set_secret creates a new version of the secret. The previous
        # version is preserved and can still be retrieved by version ID.
        client.set_secret(
            secret_name,
            new_value,
            content_type="text/plain",
            tags={"environment": "development", "rotated": "true"}
        )

        # Confirm the update by retrieving the secret again —
        # get_secret always returns the latest version
        confirmed = client.get_secret(secret_name)

        return {
            "name": secret_name,
            "old_version": old_version,
            "old_value": old_value,
            "new_version": confirmed.properties.version,
            "new_value": confirmed.value[:20] + "..." if len(confirmed.value) > 20 else confirmed.value,
            "created_on": str(confirmed.properties.created_on),
            "tags": confirmed.properties.tags or {}
        }
    ```

1. Save your changes and take a few minutes to review the code.

### Add code for cached secret retrieval

In this section, you add code that implements a time-based cache to reduce the number of Key Vault API calls when secrets are accessed frequently. The cache stores secret values in memory with a configurable time-to-live (TTL) and tracks cache hits and misses.

The function creates a dictionary-based cache with a 30-second TTL using **time.monotonic()** for elapsed time tracking. It simulates five rounds of accessing two secrets. The first round produces cache misses because the cache starts empty and has no entries to return, so the code fetches each secret from Key Vault and stores it. Subsequent rounds within the TTL find the cached entries and return them without making API calls. The access log shows each hit or miss, and the summary reports total API calls versus total accesses to demonstrate the efficiency gain.

1. Locate the **# BEGIN CACHED RETRIEVAL FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
    def cached_retrieval():
        """Demonstrate time-based caching to reduce Key Vault API calls."""
        client = get_client()
        cache = {}
        cache_ttl = 30
        vault_calls = 0
        access_log = []

        secret_names = ["openai-api-key", "cosmosdb-connection-string"]

        # Simulate five rounds of secret access. The first round fetches
        # from Key Vault (cache miss), and subsequent rounds return the
        # cached value if the TTL has not expired.
        for i in range(5):
            for name in secret_names:
                cached = cache.get(name)
                now = time.monotonic()

                if cached and (now - cached["timestamp"]) < cache_ttl:
                    access_log.append({
                        "round": i + 1,
                        "secret": name,
                        "result": "cache hit",
                        "value": cached["value"]
                    })
                else:
                    secret = client.get_secret(name)
                    vault_calls += 1
                    truncated = secret.value[:20] + "..." if len(secret.value) > 20 else secret.value
                    cache[name] = {
                        "value": truncated,
                        "timestamp": now
                    }
                    access_log.append({
                        "round": i + 1,
                        "secret": name,
                        "result": "cache miss",
                        "value": truncated
                    })

        return {
            "access_log": access_log,
            "vault_calls": vault_calls,
            "total_accesses": len(access_log),
            "cache_ttl_seconds": cache_ttl
        }
    ```

1. Save your changes and take a few minutes to review the code.

## Configure the Python environment

In this section, you navigate to the client app directory, create the Python environment, and install the dependencies.

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

In this section, you run the completed Flask application to perform various Key Vault secret management operations. The app provides a web interface that lets you retrieve secrets, list their properties, create new versions, and test cached retrieval.

1. Run the following command in the terminal to start the app. Refer to the commands from earlier in the exercise to activate the environment, if needed, before running the command. If you navigated away from the *client* directory, run **cd client** first.

    ```
    python app.py
    ```

1. Open a browser and navigate to `http://localhost:5000` to access the app.

1. Select **Retrieve Secrets** in the left panel. This retrieves the two secrets stored in the vault and displays their metadata in the right panel, including the secret name, a truncated value, version identifier, content type, creation date, and any custom tags. Both secrets should show a status of **retrieved**.

1. Select **List Secret Properties**. This lists the properties of all secrets in the vault without exposing their values. The results show each secret's name, enabled status, content type, creation date, and last updated date. This operation is useful for inventory and audit scenarios.

1. Select **Create New Version**. This creates a new version of the **openai-api-key** secret with a randomly generated value, simulating a credential rotation. The results show the previous version and value alongside the new version and value, confirming that **set_secret()** creates a new version while preserving the old one.

1. Select **Retrieve Secrets** in the left panel to verify the secret was updated.

1. Select **Run Cached Retrieval**. This simulates five rounds of accessing both secrets with a 30-second TTL cache. The first round shows two cache misses (one per secret) as the values are fetched from Key Vault. The remaining rounds show cache hits because the TTL has not expired. The summary confirms that only 2 Key Vault API calls were made for 10 total accesses.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues while completing this exercise, try the following troubleshooting steps:

**Verify Azure Key Vault deployment**
- Navigate to the [Azure portal](https://portal.azure.com) and locate your resource group.
- Confirm that the Key Vault shows a **Provisioning State** of **Succeeded**.
- Verify the vault has RBAC authorization enabled (not access policy mode).

**Check secrets**
- Run the deployment script's **Check deployment status** option to verify the secrets were stored successfully.
- If secrets are missing, run the **Store secrets** option again.

**Check code completeness and indentation**
- Ensure all code blocks were added to the correct sections in *keyvault_functions.py* between the appropriate BEGIN/END comment markers.
- Verify that Python indentation is consistent (use spaces, not tabs) and that all code aligns properly within functions.
- Confirm that no code was accidentally removed or modified outside the designated sections.

**Verify environment variables**
- Check that the *.env* file exists in the project root and contains the **KEY_VAULT_URL** value.
- Ensure you ran **source .env** (Bash) or **. .\.env.ps1** (PowerShell) to load environment variables into your terminal session.
- If variables are empty, re-run **source .env** (Bash) or **. .\.env.ps1** (PowerShell).

**Check authentication**
- Confirm you are logged in to Azure CLI by running **az account show**.
- Verify the Key Vault Secrets Officer role is assigned to your account by checking the role assignments in the Azure portal or running the deployment script's option to assign the role again.

**Check Python environment and dependencies**
- Confirm the virtual environment is activated before running the app.
- Verify that all packages from *requirements.txt* were installed successfully by running **pip list**.
