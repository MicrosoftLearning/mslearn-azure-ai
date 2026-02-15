In this exercise, you create an Azure App Configuration store and an Azure Key Vault, populate both with settings for an AI document processing pipeline, create Key Vault references, and build a Python application that retrieves all settings through the App Configuration provider. By the end of the exercise, your application loads non-sensitive settings and resolved Key Vault secrets through a single `load()` call.

> [!NOTE]
> This exercise uses the Azure CLI and Python. You can complete it in Azure Cloud Shell or in a local terminal with the Azure CLI installed. You need an Azure subscription with permissions to create resources.

## Create the Azure resources

You start by creating a resource group, an App Configuration store, and a Key Vault. These three resources form the configuration infrastructure for your application.

1. You can set environment variables for the resource names you'll use throughout the exercise. Choose a unique suffix to avoid naming conflicts.

    ```bash
    RESOURCE_GROUP="rg-appconfig-exercise"
    LOCATION="eastus"
    APPCONFIG_NAME="appconfig-docpipeline-$RANDOM"
    KEYVAULT_NAME="kv-docpipeline-$RANDOM"
    ```

1. You can create the resource group.

    ```azurecli
    az group create --name $RESOURCE_GROUP --location $LOCATION
    ```

1. You can create the App Configuration store.

    ```azurecli
    az appconfig create \
        --name $APPCONFIG_NAME \
        --resource-group $RESOURCE_GROUP \
        --location $LOCATION \
        --sku Free
    ```

1. You can create the Key Vault.

    ```azurecli
    az keyvault create \
        --name $KEYVAULT_NAME \
        --resource-group $RESOURCE_GROUP \
        --location $LOCATION
    ```

## Assign RBAC roles to your identity

Your user identity needs permissions to read and write settings in App Configuration and secrets in Key Vault. You can assign the required roles using the Azure CLI.

1. You can retrieve your signed-in user's object ID.

    ```azurecli
    USER_ID=$(az ad signed-in-user show --query id -o tsv)
    ```

1. You can assign the **App Configuration Data Owner** role so you can both read and write settings.

    ```azurecli
    az role assignment create \
        --role "App Configuration Data Owner" \
        --assignee $USER_ID \
        --scope $(az appconfig show --name $APPCONFIG_NAME --resource-group $RESOURCE_GROUP --query id -o tsv)
    ```

1. You can assign the **Key Vault Secrets Officer** role so you can create and read secrets.

    ```azurecli
    az role assignment create \
        --role "Key Vault Secrets Officer" \
        --assignee $USER_ID \
        --scope $(az keyvault show --name $KEYVAULT_NAME --resource-group $RESOURCE_GROUP --query id -o tsv)
    ```

    > [!NOTE]
    > Role assignments can take a few minutes to propagate. If subsequent commands return authorization errors, wait two to three minutes and try again.

## Add configuration settings with labels

You can add non-sensitive configuration settings to the App Configuration store. You'll create default (unlabeled) settings and environment-specific overrides using labels.

1. You can add default settings with no label. These serve as fallback values for any environment.

    ```azurecli
    az appconfig kv set --name $APPCONFIG_NAME --key "OpenAI:Endpoint" --value "https://my-openai.openai.azure.com/" --yes
    az appconfig kv set --name $APPCONFIG_NAME --key "OpenAI:DeploymentName" --value "gpt-4o" --yes
    az appconfig kv set --name $APPCONFIG_NAME --key "Pipeline:BatchSize" --value "10" --yes
    az appconfig kv set --name $APPCONFIG_NAME --key "Pipeline:RetryCount" --value "3" --yes
    ```

1. You can add production-specific overrides with a `Production` label. These values override the defaults when the application loads with the `Production` label.

    ```azurecli
    az appconfig kv set --name $APPCONFIG_NAME --key "Pipeline:BatchSize" --value "200" --label "Production" --yes
    az appconfig kv set --name $APPCONFIG_NAME --key "Pipeline:RetryCount" --value "5" --label "Production" --yes
    ```

1. You can add a sentinel key that the application watches for configuration refresh.

    ```azurecli
    az appconfig kv set --name $APPCONFIG_NAME --key "Sentinel" --value "1" --yes
    ```

## Store a secret in Key Vault and create a reference

You can store a sensitive value in Key Vault and create a Key Vault reference in App Configuration that points to it.

1. You can add a secret to Key Vault. This simulates storing an API key for the Azure OpenAI service.

    ```azurecli
    az keyvault secret set \
        --vault-name $KEYVAULT_NAME \
        --name "openai-api-key" \
        --value "sk-exercise-sample-key-12345"
    ```

1. You can get the secret's URI to use in the Key Vault reference.

    ```bash
    SECRET_URI=$(az keyvault secret show --vault-name $KEYVAULT_NAME --name "openai-api-key" --query id -o tsv)
    ```

1. You can create a Key Vault reference in App Configuration that points to the secret.

    ```azurecli
    az appconfig kv set-keyvault \
        --name $APPCONFIG_NAME \
        --key "OpenAI:ApiKey" \
        --secret-identifier $SECRET_URI \
        --yes
    ```

## Build the Python application

You can now create a Python application that loads all settings and resolved secrets through a single `load()` call.

1. You can create a working directory and install the required packages.

    ```bash
    mkdir appconfig-exercise && cd appconfig-exercise
    pip install azure-appconfiguration-provider azure-identity
    ```

1. You can create a file named `app.py` with the following code. Replace `<your-appconfig-name>` with the name of your App Configuration store.

    ```python
    from azure.appconfiguration.provider import (
        load,
        SettingSelector,
        AzureAppConfigurationKeyVaultOptions,
        WatchKey
    )
    from azure.identity import DefaultAzureCredential
    import os

    endpoint = os.environ.get("AZURE_APPCONFIG_ENDPOINT")
    credential = DefaultAzureCredential()
    environment = os.environ.get("APP_ENVIRONMENT", "Production")

    # Configure Key Vault reference resolution
    key_vault_options = AzureAppConfigurationKeyVaultOptions(credential=credential)

    # Load settings with label stacking and Key Vault resolution
    config = load(
        endpoint=endpoint,
        credential=credential,
        selects=[
            SettingSelector(key_filter="*", label_filter="\0"),
            SettingSelector(key_filter="*", label_filter=environment)
        ],
        key_vault_options=key_vault_options,
        refresh_on=[WatchKey("Sentinel")],
        refresh_interval=30
    )

    # Display all loaded settings
    print("=== Configuration Settings ===")
    print(f"OpenAI Endpoint:       {config['OpenAI:Endpoint']}")
    print(f"OpenAI Deployment:     {config['OpenAI:DeploymentName']}")
    print(f"OpenAI API Key:        {config['OpenAI:ApiKey'][:10]}...")
    print(f"Pipeline Batch Size:   {config['Pipeline:BatchSize']}")
    print(f"Pipeline Retry Count:  {config['Pipeline:RetryCount']}")
    ```

1. You can set the endpoint environment variable and run the application.

    ```bash
    export AZURE_APPCONFIG_ENDPOINT="https://$APPCONFIG_NAME.azconfig.io"
    python app.py
    ```

    The output shows default and production-overridden settings and the resolved Key Vault secret (partially masked).

## Verify dynamic refresh

You can change a setting in App Configuration and verify that the application picks up the change.

1. You can update the batch size and the sentinel key to trigger a refresh.

    ```azurecli
    az appconfig kv set --name $APPCONFIG_NAME --key "Pipeline:BatchSize" --value "500" --label "Production" --yes
    az appconfig kv set --name $APPCONFIG_NAME --key "Sentinel" --value "2" --yes
    ```

1. You can modify `app.py` to call `config.refresh()` after a delay. Add the following code at the end of the file.

    ```python
    import time

    print("\nWaiting 35 seconds for refresh interval...")
    time.sleep(35)
    config.refresh()

    print("\n=== After Refresh ===")
    print(f"Pipeline Batch Size:   {config['Pipeline:BatchSize']}")
    ```

1. You can run the application again to see the updated values.

    ```bash
    python app.py
    ```

    After the refresh interval, the application displays the updated batch size.

## Clean up resources

When you're finished with the exercise, you can delete the resource group to remove all resources.

```azurecli
az group delete --name $RESOURCE_GROUP --yes --no-wait
```
