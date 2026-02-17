"""
App Configuration management functions for loading, listing,
and refreshing configuration settings.
These functions serve as the interface between the Flask app and Azure App Configuration.
"""
import os
import time
from azure.identity import DefaultAzureCredential
from azure.appconfiguration import AzureAppConfigurationClient, ConfigurationSetting
from azure.appconfiguration.provider import (
    load,
    SettingSelector,
    AzureAppConfigurationKeyVaultOptions
)

# Module-level provider instance for refresh support
_provider = None


def get_client():
    """Get an App Configuration client for management operations."""
    endpoint = os.environ.get("AZURE_APPCONFIG_ENDPOINT")

    if not endpoint:
        raise ValueError(
            "AZURE_APPCONFIG_ENDPOINT environment variable must be set"
        )

    credential = DefaultAzureCredential()
    return AzureAppConfigurationClient(endpoint, credential)


def get_provider(force_new=False):
    """Get or create an App Configuration provider for loading settings."""
    global _provider

    if _provider is not None and not force_new:
        return _provider

    endpoint = os.environ.get("AZURE_APPCONFIG_ENDPOINT")

    if not endpoint:
        raise ValueError(
            "AZURE_APPCONFIG_ENDPOINT environment variable must be set"
        )

    credential = DefaultAzureCredential()
    key_vault_options = AzureAppConfigurationKeyVaultOptions(
        credential=credential
    )

    _provider = load(
        endpoint=endpoint,
        credential=credential,
        selects=[
            SettingSelector(key_filter="*", label_filter="\0"),
            SettingSelector(key_filter="*", label_filter="Production")
        ],
        key_vault_options=key_vault_options,
        refresh_on=["Sentinel"],
        refresh_interval=1
    )

    return _provider


# BEGIN LOAD SETTINGS FUNCTION
def load_settings():
    """Load all settings with label stacking and Key Vault reference resolution."""
    provider = get_provider()
    results = []

    # The provider resolves Key Vault references automatically and
    # applies label stacking: Production-labeled values override
    # unlabeled defaults for matching keys
    known_keys = [
        "OpenAI:Endpoint",
        "OpenAI:DeploymentName",
        "OpenAI:ApiKey",
        "Pipeline:BatchSize",
        "Pipeline:RetryCount",
        "Sentinel"
    ]

    for key in known_keys:
        try:
            value = provider[key]
            is_secret = key == "OpenAI:ApiKey"
            display_value = value[:10] + "..." if is_secret and len(value) > 10 else value
            results.append({
                "key": key,
                "value": display_value,
                "type": "Key Vault reference" if is_secret else "configuration",
                "status": "loaded"
            })
        except KeyError:
            results.append({
                "key": key,
                "value": None,
                "type": "unknown",
                "status": "not found"
            })

    return results
# END LOAD SETTINGS FUNCTION


# BEGIN LIST SETTINGS FUNCTION
def list_setting_properties():
    """List all setting properties from the App Configuration store."""
    client = get_client()
    results = []

    # list_configuration_settings returns every setting in the store
    # including all labels, showing the raw storage view rather than
    # the merged view that load() provides
    for setting in client.list_configuration_settings():
        results.append({
            "key": setting.key,
            "label": setting.label or "(no label)",
            "content_type": setting.content_type or "—",
            "last_modified": str(setting.last_modified) if setting.last_modified else "—",
            "read_only": setting.read_only
        })

    return results
# END LIST SETTINGS FUNCTION


# BEGIN REFRESH CONFIGURATION FUNCTION
def refresh_configuration():
    """Demonstrate sentinel-based dynamic refresh of configuration settings."""
    provider = get_provider()
    client = get_client()

    # Capture current values before the change
    tracked_keys = ["Pipeline:BatchSize"]
    before = {}
    for key in tracked_keys:
        try:
            before[key] = provider[key]
        except KeyError:
            before[key] = "—"

    # Update Pipeline:BatchSize with a new value to simulate a
    # configuration change, then increment the Sentinel key to
    # signal the provider that settings have changed
    import random
    new_batch = str(random.randint(100, 999))

    setting = ConfigurationSetting(
        key="Pipeline:BatchSize",
        value=new_batch,
        label="Production",
        content_type="text/plain"
    )
    client.set_configuration_setting(setting)

    # Update the Sentinel to signal the provider that settings have changed.
    # Using a timestamp ensures the value is always different from whatever
    # the provider has cached, even if settings were reset externally.
    new_sentinel = str(int(time.time()))

    sentinel_setting = ConfigurationSetting(
        key="Sentinel",
        value=new_sentinel
    )
    client.set_configuration_setting(sentinel_setting)

    # Wait briefly for the refresh interval to elapse, then call
    # refresh() to reload settings from the store
    time.sleep(2)
    provider.refresh()

    # Capture values after the refresh
    after = {}
    for key in tracked_keys:
        try:
            after[key] = provider[key]
        except KeyError:
            after[key] = "—"

    settings = []
    for key in tracked_keys:
        settings.append({
            "key": key,
            "before": before[key],
            "after": after[key],
            "changed": before[key] != after[key]
        })

    return {
        "settings": settings,
        "sentinel_value": new_sentinel,
        "new_batch_size": new_batch,
        "batch_size_updated": after["Pipeline:BatchSize"] == new_batch
    }
# END REFRESH CONFIGURATION FUNCTION
