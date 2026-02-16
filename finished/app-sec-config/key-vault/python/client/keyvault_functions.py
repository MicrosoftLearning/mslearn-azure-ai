"""
Key Vault secret management functions for storing, retrieving, and caching secrets.
These functions serve as the interface between the Flask app and Azure Key Vault.
"""
import os
import time
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError


def get_client():
    """Get a Key Vault SecretClient using Entra ID authentication."""
    vault_url = os.environ.get("KEY_VAULT_URL")

    if not vault_url:
        raise ValueError(
            "KEY_VAULT_URL environment variable must be set"
        )

    credential = DefaultAzureCredential()
    return SecretClient(vault_url=vault_url, credential=credential)


# BEGIN RETRIEVE SECRETS FUNCTION
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
# END RETRIEVE SECRETS FUNCTION


# BEGIN LIST SECRETS FUNCTION
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
# END LIST SECRETS FUNCTION


# BEGIN CREATE SECRET VERSION FUNCTION
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
# END CREATE SECRET VERSION FUNCTION


# BEGIN CACHED RETRIEVAL FUNCTION
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
# END CACHED RETRIEVAL FUNCTION
