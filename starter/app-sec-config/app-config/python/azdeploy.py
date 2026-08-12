# =============================================================================
# Change the values of these variables as needed.
# =============================================================================

rg = "<your-resource-group-name>"  # Resource Group name
location = "<your-azure-region>"   # Azure region for the resources

# =============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# =============================================================================

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("AZURE_CORE_ONLY_SHOW_ERRORS", "true")

_EXE_CACHE: dict[str, str] = {}


def _resolve_exe(name: str) -> str:
    cached = _EXE_CACHE.get(name)
    if cached:
        return cached
    resolved = shutil.which(name)
    if not resolved:
        print(f"Error: '{name}' not found on PATH. Install it and retry.")
        sys.exit(1)
    _EXE_CACHE[name] = resolved
    return resolved


def run_quiet(description: str, argv: list[str]) -> bool:
    argv = [_resolve_exe(argv[0]), *argv[1:]]
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"Error: {description} failed (exit code {result.returncode}).")
        combined = (result.stdout or "") + (result.stderr or "")
        if combined.strip():
            print(combined.rstrip())
        return False
    return True


def az_query(argv: list[str]) -> str:
    argv = [_resolve_exe(argv[0]), *argv[1:]]
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def clear_screen() -> None:
    cmd = "cls" if os.name == "nt" else "clear"
    if os.system(cmd) != 0:
        sys.stdout.write("\x1b[2J\x1b[3J\x1b[H")
        sys.stdout.flush()


def pause() -> None:
    try:
        input("Press Enter to continue...")
    except EOFError:
        print()


def write_env_files(env_vars: dict[str, str], directory: str = ".") -> None:
    """Write .env (bash) and .env.ps1 (PowerShell) side by side."""
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)

    def bash_escape(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("$", "\\$")
            .replace("`", "\\`")
        )

    def ps_escape(value: str) -> str:
        return (
            value.replace("`", "``")
            .replace('"', '`"')
            .replace("$", "`$")
        )

    bash_lines = [f'export {k}="{bash_escape(v)}"\n' for k, v in env_vars.items()]
    ps_lines = [f'$env:{k} = "{ps_escape(v)}"\n' for k, v in env_vars.items()]

    with open(target_dir / ".env", "w", encoding="utf-8", newline="\n") as f:
        f.writelines(bash_lines)
    with open(target_dir / ".env.ps1", "w", encoding="utf-8", newline="\n") as f:
        f.writelines(ps_lines)


def require_az_login() -> str:
    user_object_id = az_query(
        ["az", "ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"]
    )
    if not user_object_id:
        print("Error: Not authenticated with Azure. Please run: az login")
        sys.exit(1)
    return user_object_id


def _derived_names(user_object_id: str) -> tuple[str, str]:
    user_hash = hashlib.sha1(user_object_id.encode("utf-8")).hexdigest()[:8]
    return f"appconfig-exercise-{user_hash}", f"kv-exercise-{user_hash}"


def create_resource_group() -> bool:
    print(f"Checking/creating resource group '{rg}'...")
    exists = az_query(["az", "group", "exists", "--name", rg])
    if exists == "false":
        if not run_quiet(
            "Create resource group",
            ["az", "group", "create", "--name", rg, "--location", location],
        ):
            return False
        print(f"Resource group created: {rg}")
    else:
        print(f"Resource group already exists: {rg}")
    return True


def create_app_configuration(appconfig_name: str) -> bool:
    if not create_resource_group():
        return False
    print()
    print(f"Creating App Configuration store '{appconfig_name}'...")

    existing = az_query(
        ["az", "appconfig", "show", "--resource-group", rg, "--name", appconfig_name,
         "--query", "name", "-o", "tsv"]
    )
    if existing:
        print(f"App Configuration store already exists: {appconfig_name}")
    else:
        if not run_quiet(
            "Create App Configuration store",
            [
                "az", "appconfig", "create",
                "--name", appconfig_name,
                "--resource-group", rg,
                "--location", location,
                "--sku", "Standard",
            ],
        ):
            return False
        print(f"App Configuration store created: {appconfig_name}")

    print()
    print("Use option 2 to create Key Vault.")
    return True


def create_key_vault(kv_name: str) -> bool:
    if not create_resource_group():
        return False
    print()
    print(f"Creating Key Vault '{kv_name}'...")

    existing = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "name", "-o", "tsv"]
    )
    if existing:
        print(f"Key Vault already exists: {kv_name}")
    else:
        soft_deleted = az_query(
            ["az", "keyvault", "show-deleted", "--name", kv_name,
             "--query", "name", "-o", "tsv"]
        )
        if soft_deleted:
            print(f"  Recovering soft-deleted Key Vault '{kv_name}'...")
            if not run_quiet(
                "Recover Key Vault",
                ["az", "keyvault", "recover", "--name", kv_name],
            ):
                print(f"You may need to purge it first: az keyvault purge --name {kv_name}")
                return False
            print(f"Key Vault recovered: {kv_name}")
        else:
            if not run_quiet(
                "Create Key Vault",
                [
                    "az", "keyvault", "create",
                    "--name", kv_name,
                    "--resource-group", rg,
                    "--location", location,
                    "--enable-rbac-authorization", "true",
                ],
            ):
                return False
            print(f"Key Vault created: {kv_name}")

    print()
    print("Use option 3 to assign roles.")
    return True


def assign_roles(appconfig_name: str, kv_name: str, user_object_id: str) -> bool:
    print("Assigning roles...")

    user_upn = az_query(
        ["az", "ad", "signed-in-user", "show",
         "--query", "userPrincipalName", "-o", "tsv"]
    )
    if not user_upn:
        print("Error: Unable to retrieve signed-in user information.")
        print("Please ensure you are logged in with 'az login'.")
        return False

    ac_status = az_query(
        ["az", "appconfig", "show", "--resource-group", rg, "--name", appconfig_name,
         "--query", "provisioningState", "-o", "tsv"]
    )
    if not ac_status:
        print(f"Error: App Configuration store '{appconfig_name}' not found.")
        print("Please run option 1 to create the store, then try again.")
        return False

    ac_id = az_query(
        ["az", "appconfig", "show", "--resource-group", rg, "--name", appconfig_name,
         "--query", "id", "-o", "tsv"]
    )

    ac_role_exists = az_query(
        ["az", "role", "assignment", "list",
         "--assignee", user_object_id,
         "--scope", ac_id,
         "--role", "App Configuration Data Owner",
         "--query", "[0].id", "-o", "tsv"]
    )
    if ac_role_exists:
        print("App Configuration Data Owner role already assigned")
    else:
        if not run_quiet(
            "Assign App Configuration Data Owner role",
            [
                "az", "role", "assignment", "create",
                "--role", "App Configuration Data Owner",
                "--assignee", user_object_id,
                "--scope", ac_id,
            ],
        ):
            return False
        print("App Configuration Data Owner role assigned")

    kv_status = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "properties.provisioningState", "-o", "tsv"]
    )
    if not kv_status:
        print(f"Error: Key Vault '{kv_name}' not found.")
        print("Please run option 2 to create the vault, then try again.")
        return False

    kv_id = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "id", "-o", "tsv"]
    )

    kv_role_exists = az_query(
        ["az", "role", "assignment", "list",
         "--assignee", user_object_id,
         "--scope", kv_id,
         "--role", "Key Vault Secrets Officer",
         "--query", "[0].id", "-o", "tsv"]
    )
    if kv_role_exists:
        print("Key Vault Secrets Officer role already assigned")
    else:
        if not run_quiet(
            "Assign Key Vault Secrets Officer role",
            [
                "az", "role", "assignment", "create",
                "--role", "Key Vault Secrets Officer",
                "--assignee", user_object_id,
                "--scope", kv_id,
            ],
        ):
            return False
        print("Key Vault Secrets Officer role assigned")

    print()
    print(f"Roles configured for: {user_upn}")
    print("  - App Configuration Data Owner: read, create, and update settings")
    print("  - Key Vault Secrets Officer: read, create, update, and delete secrets")
    return True


def store_settings(appconfig_name: str, kv_name: str) -> bool:
    print("Storing configuration settings...")

    ac_status = az_query(
        ["az", "appconfig", "show", "--resource-group", rg, "--name", appconfig_name,
         "--query", "provisioningState", "-o", "tsv"]
    )
    if not ac_status:
        print(f"Error: App Configuration store '{appconfig_name}' not found.")
        print("Please run option 1 to create the store, then try again.")
        return False
    if ac_status != "Succeeded":
        print(f"Error: App Configuration store is not ready (current state: {ac_status}).")
        print("Please wait for deployment to complete. Use option 5 to check status.")
        return False

    kv_status = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "properties.provisioningState", "-o", "tsv"]
    )
    if not kv_status:
        print(f"Error: Key Vault '{kv_name}' not found.")
        print("Please run option 2 to create the vault, then try again.")
        return False
    if kv_status != "Succeeded":
        print(f"Error: Key Vault is not ready (current state: {kv_status}).")
        print("Please wait for deployment to complete. Use option 5 to check status.")
        return False

    default_settings = [
        ("OpenAI:Endpoint", "https://my-openai.openai.azure.com/"),
        ("OpenAI:DeploymentName", "gpt-4o"),
        ("Pipeline:BatchSize", "10"),
        ("Pipeline:RetryCount", "3"),
    ]
    for key, value in default_settings:
        if not run_quiet(
            f"Store setting {key}",
            [
                "az", "appconfig", "kv", "set",
                "--name", appconfig_name,
                "--key", key,
                "--value", value,
                "--yes",
            ],
        ):
            return False
        print(f"Setting stored: {key} (no label)")

    production_settings = [
        ("Pipeline:BatchSize", "200"),
        ("Pipeline:RetryCount", "5"),
    ]
    for key, value in production_settings:
        if not run_quiet(
            f"Store setting {key} (Production)",
            [
                "az", "appconfig", "kv", "set",
                "--name", appconfig_name,
                "--key", key,
                "--value", value,
                "--label", "Production",
                "--yes",
            ],
        ):
            return False
        print(f"Setting stored: {key} = {value} (Production)")

    if not run_quiet(
        "Store Sentinel key",
        [
            "az", "appconfig", "kv", "set",
            "--name", appconfig_name,
            "--key", "Sentinel",
            "--value", "1",
            "--yes",
        ],
    ):
        return False
    print("Setting stored: Sentinel = 1")

    if not run_quiet(
        "Store openai-api-key secret",
        [
            "az", "keyvault", "secret", "set",
            "--vault-name", kv_name,
            "--name", "openai-api-key",
            "--value", "sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx",
            "--content-type", "application/x-api-key",
        ],
    ):
        return False
    print("Secret stored in Key Vault: openai-api-key")

    secret_uri = az_query(
        ["az", "keyvault", "secret", "show",
         "--vault-name", kv_name, "--name", "openai-api-key",
         "--query", "id", "-o", "tsv"]
    )
    if not secret_uri:
        print("Error: Unable to retrieve secret identifier for openai-api-key.")
        return False

    if not run_quiet(
        "Create Key Vault reference in App Configuration",
        [
            "az", "appconfig", "kv", "set-keyvault",
            "--name", appconfig_name,
            "--key", "OpenAI:ApiKey",
            "--secret-identifier", secret_uri,
            "--yes",
        ],
    ):
        return False
    print("Key Vault reference created: OpenAI:ApiKey -> openai-api-key")

    print()
    print("Use option 5 to check deployment status.")
    return True


def check_deployment_status(
    appconfig_name: str, kv_name: str, user_object_id: str
) -> bool:
    print("Checking deployment status...")
    print()

    print(f"App Configuration ({appconfig_name}):")
    ac_status = az_query(
        ["az", "appconfig", "show", "--resource-group", rg, "--name", appconfig_name,
         "--query", "provisioningState", "-o", "tsv"]
    )
    if not ac_status:
        print("  Status: Not created")
    else:
        print(f"  Status: {ac_status}")
        if ac_status == "Succeeded":
            print("  App Configuration store is ready")
            ac_endpoint = az_query(
                ["az", "appconfig", "show", "--resource-group", rg, "--name", appconfig_name,
                 "--query", "endpoint", "-o", "tsv"]
            )
            if ac_endpoint:
                print(f"  Endpoint: {ac_endpoint}")

            print()
            print("  Settings:")
            setting_count = az_query(
                ["az", "appconfig", "kv", "list",
                 "--name", appconfig_name,
                 "--query", "length(@)", "-o", "tsv"]
            )
            if setting_count and setting_count.isdigit() and int(setting_count) > 0:
                print(f"  {setting_count} setting(s) stored")
            else:
                print("  WARNING: No settings stored")

            kv_ref = az_query(
                ["az", "appconfig", "kv", "list",
                 "--name", appconfig_name,
                 "--key", "OpenAI:ApiKey",
                 "--query", "[0].contentType", "-o", "tsv"]
            )
            if kv_ref:
                print("  Key Vault reference: OpenAI:ApiKey")
            else:
                print("  WARNING: Key Vault reference not found: OpenAI:ApiKey")
        else:
            print("  WARNING: App Configuration store is still provisioning. Please wait and try again.")

    print()
    print(f"Key Vault ({kv_name}):")
    kv_status = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "properties.provisioningState", "-o", "tsv"]
    )
    if not kv_status:
        print("  Status: Not created")
    else:
        print(f"  Status: {kv_status}")
        if kv_status == "Succeeded":
            print("  Key Vault is ready")
            kv_uri = az_query(
                ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
                 "--query", "properties.vaultUri", "-o", "tsv"]
            )
            if kv_uri:
                print(f"  Vault URI: {kv_uri}")

            print()
            print("  Secrets:")
            api_key = az_query(
                ["az", "keyvault", "secret", "show",
                 "--vault-name", kv_name, "--name", "openai-api-key",
                 "--query", "name", "-o", "tsv"]
            )
            if api_key:
                print("  Secret stored: openai-api-key")
            else:
                print("  WARNING: Secret not stored: openai-api-key")
        else:
            print("  WARNING: Key Vault is still provisioning. Please wait and try again.")

    print()
    print("Role Assignments:")
    user_upn = az_query(
        ["az", "ad", "signed-in-user", "show",
         "--query", "userPrincipalName", "-o", "tsv"]
    )
    ac_id = az_query(
        ["az", "appconfig", "show", "--resource-group", rg, "--name", appconfig_name,
         "--query", "id", "-o", "tsv"]
    )
    if ac_id:
        ac_role = az_query(
            ["az", "role", "assignment", "list",
             "--assignee", user_object_id,
             "--scope", ac_id,
             "--role", "App Configuration Data Owner",
             "--query", "[0].id", "-o", "tsv"]
        )
        if ac_role:
            print(f"  Role assigned: {user_upn} (App Configuration Data Owner)")
        else:
            print("  WARNING: App Configuration Data Owner role not assigned")

    kv_id = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "id", "-o", "tsv"]
    )
    if kv_id:
        kv_role = az_query(
            ["az", "role", "assignment", "list",
             "--assignee", user_object_id,
             "--scope", kv_id,
             "--role", "Key Vault Secrets Officer",
             "--query", "[0].id", "-o", "tsv"]
        )
        if kv_role:
            print(f"  Role assigned: {user_upn} (Key Vault Secrets Officer)")
        else:
            print("  WARNING: Key Vault Secrets Officer role not assigned")
    return True


def retrieve_connection_info(appconfig_name: str, user_object_id: str) -> bool:
    print("Retrieving connection information...")

    existing = az_query(
        ["az", "appconfig", "show", "--resource-group", rg, "--name", appconfig_name,
         "--query", "name", "-o", "tsv"]
    )
    if not existing:
        print(f"Error: App Configuration store '{appconfig_name}' not found.")
        print("Please run option 1 to create the store, then try again.")
        return False

    ac_id = az_query(
        ["az", "appconfig", "show", "--resource-group", rg, "--name", appconfig_name,
         "--query", "id", "-o", "tsv"]
    )
    ac_role = az_query(
        ["az", "role", "assignment", "list",
         "--assignee", user_object_id,
         "--scope", ac_id,
         "--role", "App Configuration Data Owner",
         "--query", "[0].id", "-o", "tsv"]
    )
    if not ac_role:
        print("Error: App Configuration Data Owner role not assigned.")
        print("Please run option 3 to assign roles, then try again.")
        return False

    ac_endpoint = az_query(
        ["az", "appconfig", "show", "--resource-group", rg, "--name", appconfig_name,
         "--query", "endpoint", "-o", "tsv"]
    )
    if not ac_endpoint:
        print("Error: Unable to retrieve the App Configuration endpoint.")
        return False

    write_env_files({"AZURE_APPCONFIG_ENDPOINT": ac_endpoint})
    clear_screen()
    print()
    print("App Configuration Connection Information")
    print("===========================================================")
    print(f"Endpoint: {ac_endpoint}")
    print("Authentication: Microsoft Entra ID (DefaultAzureCredential)")
    print()
    print("Environment variables saved to .env and .env.ps1")
    return True


def show_menu(appconfig_name: str, kv_name: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    App Configuration Exercise - Deployment Script")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"App Configuration: {appconfig_name}")
    print(f"Key Vault: {kv_name}")
    print("=====================================================================")
    print("1. Create App Configuration")
    print("2. Create Key Vault")
    print("3. Assign roles")
    print("4. Store sample settings")
    print("5. Check deployment status")
    print("6. Retrieve connection info")
    print("7. Exit")
    print("=====================================================================")


def _preflight() -> None:
    script_dir = Path(__file__).resolve().parent
    if not (script_dir / "client" / "app.py").is_file():
        print(
            "Error: 'client/app.py' is missing next to azdeploy.py. "
            "Make sure you kept the exercise folder intact."
        )
        sys.exit(1)
    os.chdir(script_dir)


def main() -> None:
    _preflight()
    user_object_id = require_az_login()
    appconfig_name, kv_name = _derived_names(user_object_id)

    while True:
        show_menu(appconfig_name, kv_name)
        choice = input("Please select an option (1-7): ").strip()
        if choice in {"1", "2", "3", "4", "5", "6", "7"}:
            clear_screen()

        if choice == "1":
            print()
            create_app_configuration(appconfig_name)
            print()
            pause()
        elif choice == "2":
            print()
            create_key_vault(kv_name)
            print()
            pause()
        elif choice == "3":
            print()
            assign_roles(appconfig_name, kv_name, user_object_id)
            print()
            pause()
        elif choice == "4":
            print()
            store_settings(appconfig_name, kv_name)
            print()
            pause()
        elif choice == "5":
            print()
            check_deployment_status(appconfig_name, kv_name, user_object_id)
            print()
            pause()
        elif choice == "6":
            print()
            retrieve_connection_info(appconfig_name, user_object_id)
            print()
            pause()
        elif choice == "7":
            print("Exiting...")
            clear_screen()
            sys.exit(0)
        else:
            print()
            print("Invalid option. Please select 1-7.")
            print()
            pause()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
