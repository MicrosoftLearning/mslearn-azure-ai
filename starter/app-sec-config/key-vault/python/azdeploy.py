# =============================================================================
# Change the values of these variables as needed.
# =============================================================================

# rg = "<your-resource-group-name>"  # Resource Group name
# location = "<your-azure-region>"   # Azure region for the resources

rg = "rg-exercises"  # Resource Group name
location = "eastus2"  # Azure region for the resources

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


def _derived_names(user_object_id: str) -> str:
    user_hash = hashlib.sha1(user_object_id.encode("utf-8")).hexdigest()[:8]
    return f"kv-exercise-{user_hash}"


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
    print("Use option 2 to assign the role.")
    return True


def assign_role(kv_name: str, user_object_id: str) -> bool:
    print("Assigning Key Vault Secrets Officer role...")

    kv_status = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "properties.provisioningState", "-o", "tsv"]
    )
    if not kv_status:
        print(f"Error: Key Vault '{kv_name}' not found.")
        print("Please run option 1 to create the vault, then try again.")
        return False
    if kv_status != "Succeeded":
        print(f"Error: Key Vault is not ready (current state: {kv_status}).")
        print("Please wait for deployment to complete. Use option 4 to check status.")
        return False

    user_upn = az_query(
        ["az", "ad", "signed-in-user", "show",
         "--query", "userPrincipalName", "-o", "tsv"]
    )
    if not user_upn:
        print("Error: Unable to retrieve signed-in user information.")
        print("Please ensure you are logged in with 'az login'.")
        return False

    kv_id = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "id", "-o", "tsv"]
    )
    if not kv_id:
        print("Error: Unable to retrieve Key Vault resource ID.")
        return False

    role_exists = az_query(
        ["az", "role", "assignment", "list",
         "--assignee", user_object_id,
         "--scope", kv_id,
         "--role", "Key Vault Secrets Officer",
         "--query", "[0].id", "-o", "tsv"]
    )
    if role_exists:
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
    print(f"Role configured for: {user_upn}")
    print("  - Key Vault Secrets Officer: read, create, update, and delete secrets")
    return True


def store_secrets(kv_name: str) -> bool:
    print("Storing sample secrets...")

    status = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "properties.provisioningState", "-o", "tsv"]
    )
    if not status:
        print(f"Error: Key Vault '{kv_name}' not found.")
        print("Please run option 1 to create the vault, then try again.")
        return False
    if status != "Succeeded":
        print(f"Error: Key Vault is not ready (current state: {status}).")
        print("Please wait for deployment to complete. Use option 4 to check status.")
        return False

    if not run_quiet(
        "Store openai-api-key",
        [
            "az", "keyvault", "secret", "set",
            "--vault-name", kv_name,
            "--name", "openai-api-key",
            "--value", "sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx",
            "--content-type", "application/x-api-key",
            "--tags", "environment=development", "service=openai",
        ],
    ):
        return False
    print("Secret stored: openai-api-key")

    if not run_quiet(
        "Store cosmosdb-connection-string",
        [
            "az", "keyvault", "secret", "set",
            "--vault-name", kv_name,
            "--name", "cosmosdb-connection-string",
            "--value",
            "AccountEndpoint=https://mycosmosdb.documents.azure.com:443/;"
            "AccountKey=abc123def456ghi789==",
            "--content-type", "application/x-connection-string",
            "--tags", "environment=development", "service=cosmosdb",
        ],
    ):
        return False
    print("Secret stored: cosmosdb-connection-string")

    print()
    print("Use option 4 to check deployment status.")
    return True


def check_deployment_status(kv_name: str, user_object_id: str) -> bool:
    print("Checking deployment status...")
    print()
    print(f"Key Vault ({kv_name}):")
    kv_status = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "properties.provisioningState", "-o", "tsv"]
    )
    if not kv_status:
        print("  Status: Not created")
        return True

    print(f"  Status: {kv_status}")
    if kv_status != "Succeeded":
        print("  WARNING: Key Vault is still provisioning. Please wait and try again.")
        return True

    print("  Key Vault is ready")
    kv_uri = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "properties.vaultUri", "-o", "tsv"]
    )
    if kv_uri:
        print(f"  Vault URI: {kv_uri}")

    print()
    print("Secrets:")
    api_key = az_query(
        ["az", "keyvault", "secret", "show",
         "--vault-name", kv_name, "--name", "openai-api-key",
         "--query", "name", "-o", "tsv"]
    )
    print(f"  Secret openai-api-key: {'Stored' if api_key else 'Not stored'}")

    conn_str = az_query(
        ["az", "keyvault", "secret", "show",
         "--vault-name", kv_name, "--name", "cosmosdb-connection-string",
         "--query", "name", "-o", "tsv"]
    )
    print(f"  Secret cosmosdb-connection-string: {'Stored' if conn_str else 'Not stored'}")

    print()
    print("Role Assignment:")
    user_upn = az_query(
        ["az", "ad", "signed-in-user", "show",
         "--query", "userPrincipalName", "-o", "tsv"]
    )
    kv_id = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "id", "-o", "tsv"]
    )
    if kv_id:
        role_exists = az_query(
            ["az", "role", "assignment", "list",
             "--assignee", user_object_id,
             "--scope", kv_id,
             "--role", "Key Vault Secrets Officer",
             "--query", "[0].id", "-o", "tsv"]
        )
        if role_exists:
            print(f"  Role assigned: {user_upn} (Key Vault Secrets Officer)")
        else:
            print("  Role not assigned")
    return True


def retrieve_connection_info(kv_name: str, user_object_id: str) -> bool:
    print("Retrieving connection information...")

    existing = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "name", "-o", "tsv"]
    )
    if not existing:
        print(f"Error: Key Vault '{kv_name}' not found.")
        print("Please run option 1 to create the vault, then try again.")
        return False

    kv_id = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "id", "-o", "tsv"]
    )
    role_exists = az_query(
        ["az", "role", "assignment", "list",
         "--assignee", user_object_id,
         "--scope", kv_id,
         "--role", "Key Vault Secrets Officer",
         "--query", "[0].id", "-o", "tsv"]
    )
    if not role_exists:
        print("Error: Key Vault Secrets Officer role not assigned.")
        print("Please run option 2 to assign the role, then try again.")
        return False

    kv_uri = az_query(
        ["az", "keyvault", "show", "--resource-group", rg, "--name", kv_name,
         "--query", "properties.vaultUri", "-o", "tsv"]
    )
    if not kv_uri:
        print("Error: Unable to retrieve the Key Vault URI.")
        return False

    write_env_files({"KEY_VAULT_URL": kv_uri})
    clear_screen()
    print()
    print("Key Vault Connection Information")
    print("===========================================================")
    print(f"Vault URL: {kv_uri}")
    print("Authentication: Microsoft Entra ID (DefaultAzureCredential)")
    print()
    print("Environment variables saved to .env and .env.ps1")
    return True


def show_menu(kv_name: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    Key Vault Secrets Exercise - Deployment Script")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"Key Vault: {kv_name}")
    print("=====================================================================")
    print("1. Create Key Vault")
    print("2. Assign role")
    print("3. Store secrets")
    print("4. Check deployment status")
    print("5. Retrieve connection info")
    print("6. Exit")
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
    kv_name = _derived_names(user_object_id)

    while True:
        show_menu(kv_name)
        choice = input("Please select an option (1-6): ").strip()
        if choice in {"1", "2", "3", "4", "5", "6"}:
            clear_screen()

        if choice == "1":
            print()
            create_key_vault(kv_name)
            print()
            pause()
        elif choice == "2":
            print()
            assign_role(kv_name, user_object_id)
            print()
            pause()
        elif choice == "3":
            print()
            store_secrets(kv_name)
            print()
            pause()
        elif choice == "4":
            print()
            check_deployment_status(kv_name, user_object_id)
            print()
            pause()
        elif choice == "5":
            print()
            retrieve_connection_info(kv_name, user_object_id)
            print()
            pause()
        elif choice == "6":
            print("Exiting...")
            clear_screen()
            sys.exit(0)
        else:
            print()
            print("Invalid option. Please select 1-6.")
            print()
            pause()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
