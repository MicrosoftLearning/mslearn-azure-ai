---
lab:
    topic: App secrets and configuration
    title: 'Retrieve settings and secrets through App Configuration'
    description: 'Learn how to load, list, and dynamically refresh configuration settings using Azure App Configuration with the Python SDK.'
    level: 200
    duration: 30
---

# Retrieve settings and secrets through App Configuration

AI applications depend on both non-sensitive configuration such as model endpoints and batch sizes, and sensitive credentials such as API keys. Azure App Configuration provides a centralized store for managing these settings with label-based environment overrides, Key Vault references for secrets, and sentinel-based dynamic refresh so applications can pick up configuration changes without restarting.

In this exercise, you deploy an Azure App Configuration store and Key Vault pre-loaded with sample settings and build a Python Flask web application that demonstrates core configuration management patterns using the Azure SDK. You load settings with label stacking and automatic Key Vault reference resolution, list all setting properties and metadata, and trigger a sentinel-based refresh to pick up changes dynamically.

Tasks performed in this exercise:

- Download the project starter files
- Create an Azure App Configuration store and Key Vault with sample settings
- Add code to the starter files to complete the app
- Run the app to perform configuration operations

This exercise takes approximately **30** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).

## Download project starter files and deploy Azure App Configuration

In this section you download the starter files for the app and use a script to deploy an Azure App Configuration store and Key Vault with sample settings to your subscription.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/app-config-python.zip
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

1. Run the following commands to ensure your subscription has the necessary resource providers for the exercise.

    ```
    az provider register --namespace Microsoft.AppConfiguration
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

1. When the script is running, enter **1** to launch the **1. Create App Configuration** option.

    This option creates the resource group if it doesn't already exist and deploys an Azure App Configuration store. App Configuration provides a centralized service for managing application settings separately from code.

1. Enter **2** to run the **2. Create Key Vault** option. This creates an Azure Key Vault with RBAC authorization enabled. The Key Vault stores sensitive values such as API keys that App Configuration references securely.

1. Enter **3** to run the **3. Assign roles** option. This assigns the App Configuration Data Owner role and the Key Vault Secrets Officer role to your account so you can read, create, and update settings and secrets using Microsoft Entra authentication.

1. Enter **4** to run the **4. Store settings** option. This stores configuration settings in the App Configuration store including default (unlabeled) values and Production-labeled overrides for environment-specific settings. It also stores a secret in Key Vault and creates a Key Vault reference in App Configuration that points to the secret. Finally, it creates a sentinel key used for dynamic refresh.

1. Enter **5** to run the **5. Check deployment status** option. Verify the App Configuration store and Key Vault both show **Succeeded**, the roles are assigned, and the settings are stored before continuing. If resources are still provisioning, wait a moment and try again.

1. Enter **6** to run the **6. Retrieve connection info** option. This creates the environment variable file with the App Configuration endpoint URL needed by the app.

1. Enter **7** to exit the deployment script.

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

In this section you add code to the *appconfig_functions.py* file to complete the App Configuration management functions. The Flask app in *app.py* calls these functions and displays the results in the browser. You run the app later in the exercise.

1. Open the *client/appconfig_functions.py* file to begin adding code.

>**Note:** The code blocks you add to the application should align with the comment for that section of the code.

### Add code to load settings

In this section, you add code to load all configuration settings from the App Configuration store with label stacking and automatic Key Vault reference resolution. The function creates a provider that merges unlabeled default values with Production-labeled overrides and resolves Key Vault references transparently.

The function calls **load()** with two **SettingSelector** entries: the first selects all unlabeled settings (using the null label filter **\0**), and the second selects all Production-labeled settings. Because the Production selector appears second, its values override the defaults for any matching keys. The **AzureAppConfigurationKeyVaultOptions** parameter tells the provider to resolve Key Vault references automatically using the same credential, so the application receives the actual secret value rather than a reference URI.

1. Locate the **# BEGIN LOAD SETTINGS FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
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
    ```

1. Take a few minutes to review the code.

### Add code to list setting properties

In this section, you add code to list the properties of all settings in the App Configuration store. Unlike the **load()** function which merges labels and resolves Key Vault references, this function shows the raw storage view with every individual setting entry, including all labels and content types.

The function calls **list_configuration_settings()** on the management client, which returns an iterable of setting objects with metadata such as key, label, content type, last modified timestamp, and read-only status. This is useful for inventory and audit operations where you need to see exactly what is stored, including the separate unlabeled and Production-labeled entries.

1. Locate the **# BEGIN LIST SETTINGS FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
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
    ```

1. Save your changes and take a few minutes to review the code.

### Add code for dynamic refresh

In this section, you add code that demonstrates sentinel-based dynamic refresh. The function updates a setting and sets a new sentinel value, then calls **refresh()** on the provider to reload configuration without restarting the application.

The function captures the current provider values, then uses the management client to update **Pipeline:BatchSize** with a new random value and set the **Sentinel** key to a new timestamp value. The sentinel acts as a change signal: the provider watches it, and when its value changes, a call to **refresh()** triggers a reload of all settings. The function waits briefly for the refresh interval to elapse, then calls **refresh()** and compares the before and after values to confirm the update propagated.

1. Locate the **# BEGIN REFRESH CONFIGURATION FUNCTION** comment and add the following code under the comment. Be sure to check for proper code alignment.

    ```python
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

In this section, you run the completed Flask application to perform various App Configuration management operations. The app provides a web interface that lets you load settings, list their properties, and test dynamic refresh.

1. Run the following command in the terminal to start the app. Refer to the commands from earlier in the exercise to activate the environment, if needed, before running the command. If you navigated away from the *client* directory, run **cd client** first.

    ```
    python app.py
    ```

1. Open a browser and navigate to `http://localhost:5000` to access the app.

1. Select **Load Settings** in the left panel. This loads all configuration settings with label stacking and Key Vault reference resolution. The results show each setting's key, value, and type. Settings labeled as **configuration** are regular App Configuration values, while **Key Vault reference** indicates the value was resolved from a Key Vault secret.

1. Select **List Setting Properties**. This lists every individual setting entry in the store, including both unlabeled defaults and Production-labeled overrides as separate rows. The results show each setting's key, label, content type, last modified timestamp, and read-only status. Notice that **Pipeline:BatchSize** appears twice: once with no label (value 10) and once with the **Production** label (value 200). The **Load Settings** results showed 200 because the Production-labeled override took precedence over the unlabeled default.

1. Select **Refresh Configuration**. This demonstrates sentinel-based dynamic refresh. The function updates **Pipeline:BatchSize** with a new random value, sets the **Sentinel** key to a new timestamp, waits briefly, and then calls **refresh()** on the provider. The results show the before and after values for tracked settings, confirming that the provider picked up the change without restarting the application.

## Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.

## Troubleshooting

If you encounter issues while completing this exercise, try the following troubleshooting steps:

**Verify Azure App Configuration deployment**
- Navigate to the [Azure portal](https://portal.azure.com) and locate your resource group.
- Confirm that the App Configuration store shows a **Provisioning State** of **Succeeded**.
- Confirm that the Key Vault shows a **Provisioning State** of **Succeeded** and has RBAC authorization enabled.

**Check settings**
- Run the deployment script's **Check deployment status** option to verify the settings were stored successfully.
- If settings are missing, run the **Store settings** option again.

**Check code completeness and indentation**
- Ensure all code blocks were added to the correct sections in *appconfig_functions.py* between the appropriate BEGIN/END comment markers.
- Verify that Python indentation is consistent (use spaces, not tabs) and that all code aligns properly within functions.
- Confirm that no code was accidentally removed or modified outside the designated sections.

**Verify environment variables**
- Check that the *.env* file exists in the project root and contains the **AZURE_APPCONFIG_ENDPOINT** value.
- Ensure you ran **source .env** (Bash) or **. .\.env.ps1** (PowerShell) to load environment variables into your terminal session.
- If variables are empty, re-run **source .env** (Bash) or **. .\.env.ps1** (PowerShell).

**Check authentication**
- Confirm you are logged in to Azure CLI by running **az account show**.
- Verify the App Configuration Data Owner and Key Vault Secrets Officer roles are assigned to your account by checking the role assignments in the Azure portal or running the deployment script's option to assign the roles again.

**Check Python environment and dependencies**
- Confirm the virtual environment is activated before running the app.
- Verify that all packages from *requirements.txt* were installed successfully by running **pip list**.
