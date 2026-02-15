In this exercise, you create an Azure Key Vault, store secrets representing AI service credentials, and build a Python application that retrieves and caches those secrets using the Azure SDK. You also create a new version of a secret and verify that the application retrieves the updated value. By the end, you'll have a working application that demonstrates the complete lifecycle of secret storage, retrieval, versioning, and caching.

## Set up the Azure Key Vault

You can start by creating a resource group and Key Vault using the Azure CLI. The vault name must be globally unique, so replace `<your-vault-name>` with a unique identifier.

```azurecli
az group create --name rg-keyvault-exercise --location eastus

az keyvault create \
    --name <your-vault-name> \
    --resource-group rg-keyvault-exercise \
    --location eastus \
    --enable-rbac-authorization true
```

The `--enable-rbac-authorization true` flag configures the vault to use Azure RBAC instead of legacy access policies. This is the recommended authorization model for all new vaults.

## Assign RBAC permissions

You can assign yourself the `Key Vault Secrets Officer` role so you can create, read, update, and delete secrets in the vault. You need your Microsoft Entra ID user principal to create the role assignment.

```bash
USER_ID=$(az ad signed-in-user show --query id -o tsv)
VAULT_ID=$(az keyvault show --name <your-vault-name> \
    --resource-group rg-keyvault-exercise --query id -o tsv)

az role assignment create \
    --role "Key Vault Secrets Officer" \
    --assignee "$USER_ID" \
    --scope "$VAULT_ID"
```

Role assignments can take a few minutes to propagate. If you receive an authorization error in later steps, wait briefly and retry.

## Store secrets in the vault

You can store two secrets that represent credentials for an AI application: an API key for a model endpoint and a database connection string. These are sample values for this exercise.

```azurecli
az keyvault secret set \
    --vault-name <your-vault-name> \
    --name "openai-api-key" \
    --value "sk-exercise-key-12345" \
    --content-type "text/plain" \
    --tags environment=development service=azure-openai

az keyvault secret set \
    --vault-name <your-vault-name> \
    --name "cosmosdb-connection-string" \
    --value "AccountEndpoint=https://exercise-cosmosdb.documents.azure.com:443/;AccountKey=exercisekey123==" \
    --content-type "text/plain" \
    --tags environment=development service=cosmosdb
```

You can verify the secrets were created:

```azurecli
az keyvault secret list --vault-name <your-vault-name> -o table
```

## Install the Python SDK packages

You can create a project directory and install the required packages:

```bash
mkdir keyvault-exercise && cd keyvault-exercise

pip install azure-keyvault-secrets azure-identity
```

## Build the secret retrieval application

You can create a Python file named `app.py` that authenticates to Key Vault with `DefaultAzureCredential`, retrieves the stored secrets, and displays their metadata. The `DefaultAzureCredential` uses your Azure CLI login in this local development scenario.

```python
import time
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError

VAULT_URL = "https://<your-vault-name>.vault.azure.net/"

def retrieve_secrets():
    """Retrieve secrets and display their metadata."""
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=VAULT_URL, credential=credential)

    secret_names = ["openai-api-key", "cosmosdb-connection-string"]

    for name in secret_names:
        try:
            secret = client.get_secret(name)
            print(f"\nSecret: {secret.name}")
            print(f"  Value: {secret.value[:20]}...")
            print(f"  Version: {secret.properties.version}")
            print(f"  Content type: {secret.properties.content_type}")
            print(f"  Created: {secret.properties.created_on}")
            if secret.properties.tags:
                print(f"  Tags: {secret.properties.tags}")
        except ResourceNotFoundError:
            print(f"\nSecret '{name}' not found in vault.")
        except HttpResponseError as e:
            print(f"\nError accessing '{name}': {e.message}")

    # List all secret properties
    print("\n--- All secrets in vault ---")
    for prop in client.list_properties_of_secrets():
        print(f"  {prop.name} (enabled: {prop.enabled})")

if __name__ == "__main__":
    retrieve_secrets()
```

You can run the application:

```bash
python app.py
```

The output shows each secret's name, a truncated value, version identifier, content type, creation date, and tags. The listing section shows all secret names in the vault.

## Create a new secret version

You can simulate a credential rotation by creating a new version of the API key secret with an updated value:

```azurecli
az keyvault secret set \
    --vault-name <your-vault-name> \
    --name "openai-api-key" \
    --value "sk-rotated-key-67890" \
    --content-type "text/plain" \
    --tags environment=development service=azure-openai
```

You can run the application again and observe that it retrieves the new value:

```bash
python app.py
```

The version identifier changes, and the value prefix updates to reflect the rotated key. The `get_secret()` call always returns the latest version.

## Implement a simple time-based cache

You can add a caching layer to reduce Key Vault API calls. Create a file named `cached_app.py` with a `SecretCache` class that stores secret values in memory with a configurable TTL:

```python
import time
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

VAULT_URL = "https://<your-vault-name>.vault.azure.net/"

class SecretCache:
    def __init__(self, vault_url, cache_ttl_seconds=30):
        credential = DefaultAzureCredential()
        self._client = SecretClient(vault_url=vault_url, credential=credential)
        self._cache = {}
        self._cache_ttl = cache_ttl_seconds
        self._vault_calls = 0

    def get_secret(self, secret_name):
        cached = self._cache.get(secret_name)
        now = time.monotonic()

        if cached and (now - cached["timestamp"]) < self._cache_ttl:
            print(f"  [CACHE HIT] {secret_name}")
            return cached["value"]

        print(f"  [CACHE MISS] {secret_name} - fetching from Key Vault")
        secret = self._client.get_secret(secret_name)
        self._vault_calls += 1
        self._cache[secret_name] = {
            "value": secret.value,
            "timestamp": now
        }
        return secret.value

def main():
    cache = SecretCache(VAULT_URL, cache_ttl_seconds=30)

    # Simulate multiple requests
    for i in range(5):
        print(f"\nRequest {i + 1}:")
        api_key = cache.get_secret("openai-api-key")
        conn_str = cache.get_secret("cosmosdb-connection-string")
        time.sleep(2)

    print(f"\nTotal Key Vault API calls: {cache._vault_calls}")
    print("Without cache, this would have been 10 calls.")

if __name__ == "__main__":
    main()
```

You can run the cached application:

```bash
python cached_app.py
```

The output shows cache hits and misses. The first request makes two Key Vault calls (one per secret). Subsequent requests within the 30-second TTL return cached values without calling Key Vault. With a 30-second TTL and two-second intervals between requests, you see that most requests are served from cache. The total API call count is significantly lower than the number of secret accesses.

## Clean up resources

You can delete the resource group to remove all resources created during this exercise:

```azurecli
az group delete --name rg-keyvault-exercise --yes --no-wait
```
