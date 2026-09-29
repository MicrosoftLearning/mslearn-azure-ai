# =============================================================================
# Change the values of these variables as needed.
# =============================================================================

rg = "<your-resource-group-name>"  # Resource Group name
location = "<your-azure-region>"   # Azure region for the resources

# =============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# =============================================================================

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

DATABASE_NAME = "agent-memory"
CONTAINER_NAME = "memories"
DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 30
CONTAINER_API_VERSION = "2025-04-15"

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


def _run_capture(argv: list[str]) -> subprocess.CompletedProcess[str]:
    resolved_argv = [_resolve_exe(argv[0]), *argv[1:]]
    return subprocess.run(
        resolved_argv,
        capture_output=True,
        text=True,
        check=False,
    )


def _result_output(result: subprocess.CompletedProcess[str]) -> str:
    return ((result.stdout or "") + (result.stderr or "")).strip()


def _print_command_error(
    description: str,
    result: subprocess.CompletedProcess[str],
) -> None:
    print(f"Error: {description} failed (exit code {result.returncode}).")
    output = _result_output(result)
    if output:
        print(output)


def run_quiet(description: str, argv: list[str]) -> bool:
    result = _run_capture(argv)
    if result.returncode != 0:
        _print_command_error(description, result)
        return False
    return True


def az_query(argv: list[str]) -> str:
    result = _run_capture(argv)
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def clear_screen() -> None:
    command = "cls" if os.name == "nt" else "clear"
    if os.system(command) != 0:
        sys.stdout.write("\x1b[2J\x1b[3J\x1b[H")
        sys.stdout.flush()


def pause() -> None:
    try:
        input("Press Enter to continue...")
    except EOFError:
        print()


def write_env_files(env_vars: dict[str, str], directory: str = ".") -> None:
    """Write .env (bash) and .env.ps1 (PowerShell) side by side.

    Writes UTF-8 without BOM and LF line endings so both bash `source` and
    PowerShell dot-source read them correctly on every supported shell.
    """
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

    bash_lines = [f'export {key}="{bash_escape(value)}"\n' for key, value in env_vars.items()]
    ps_lines = [f'$env:{key} = "{ps_escape(value)}"\n' for key, value in env_vars.items()]

    with open(target_dir / ".env", "w", encoding="utf-8", newline="\n") as file:
        file.writelines(bash_lines)
    with open(target_dir / ".env.ps1", "w", encoding="utf-8", newline="\n") as file:
        file.writelines(ps_lines)


def require_az_login() -> str:
    user_object_id = az_query(
        ["az", "ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"]
    )
    if not user_object_id:
        print("Error: Not authenticated with Azure. Please run: az login")
        sys.exit(1)
    return user_object_id


def _derived_account_name(user_object_id: str) -> str:
    user_hash = hashlib.sha1(user_object_id.encode("utf-8")).hexdigest()[:8]
    return f"cosmos-memory-{user_hash}"


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


def _account_state(account_name: str) -> str:
    return az_query(
        [
            "az",
            "cosmosdb",
            "show",
            "--resource-group",
            rg,
            "--name",
            account_name,
            "--query",
            "provisioningState",
            "-o",
            "tsv",
        ]
    )


def _wait_for_account_name_release(account_name: str) -> bool:
    waited = 0
    while True:
        name_exists = az_query(
            [
                "az",
                "cosmosdb",
                "check-name-exists",
                "--name",
                account_name,
                "-o",
                "tsv",
            ]
        ).lower()
        if name_exists == "false":
            return True
        if name_exists != "true":
            print("Error: Unable to verify that the Cosmos DB account name was released.")
            print("Please wait a few minutes, then run option 1 again.")
            return False
        if waited >= 300:
            print("Error: Timed out waiting for the Cosmos DB account name to be released.")
            print("Please wait a few minutes, then run option 1 again.")
            return False
        if waited == 0:
            print("Waiting for Azure to release the globally unique account name...")
        time.sleep(10)
        waited += 10
        print(f"  Still waiting... {waited} seconds elapsed")


def _create_account_resource(account_name: str) -> bool:
    argv = [
        "az",
        "cosmosdb",
        "create",
        "--resource-group",
        rg,
        "--name",
        account_name,
        "--locations",
        f"regionName={location}",
        "--capabilities",
        "EnableServerless",
        "--default-consistency-level",
        "Session",
    ]
    waited = 0
    while True:
        if waited:
            print(f"Retrying deployment to '{location}'...", flush=True)
        result = _run_capture(argv)
        if result.returncode == 0:
            return True

        output = _result_output(result)
        if "InvalidResourceLocation" not in output:
            _print_command_error("Create Cosmos DB account", result)
            print()
            print("The deployment failed. This is most often caused by a temporary")
            print(f"lack of capacity in the '{location}' region.")
            print()
            print("To resolve this:")
            print("  1. Choose option 5 to exit the script.")
            print("  2. Near the top of this script, change the 'location' variable")
            print("     to a different Azure region.")
            print("  3. Run the script again and choose option 1. The failed account")
            print("     is deleted automatically before the next attempt.")
            return False

        if waited >= 120:
            _print_command_error("Create Cosmos DB account", result)
            print()
            print("Error: Azure did not release the account's previous region in time.")
            print("Please wait a few minutes, then run option 1 again.")
            return False

        if waited == 0:
            print("Azure is still releasing the account's previous region assignment.")
            print("Retrying account creation every 10 seconds...")
        time.sleep(10)
        waited += 10
        print(f"  Still waiting... {waited} seconds elapsed")


def _container_exists(account_name: str) -> bool:
    return bool(
        az_query(
            [
                "az",
                "cosmosdb",
                "sql",
                "container",
                "show",
                "--resource-group",
                rg,
                "--account-name",
                account_name,
                "--database-name",
                DATABASE_NAME,
                "--name",
                CONTAINER_NAME,
                "--query",
                "name",
                "-o",
                "tsv",
            ]
        )
    )


def _create_memory_container(account_name: str) -> bool:
    if _container_exists(account_name):
        print(f"Container already exists: {CONTAINER_NAME}")
        return True

    account_id = _account_id(account_name)
    if not account_id:
        print("Error: Unable to retrieve the Cosmos DB account ID.")
        return False

    container_url = (
        f"{account_id}/sqlDatabases/{DATABASE_NAME}/containers/{CONTAINER_NAME}"
        f"?api-version={CONTAINER_API_VERSION}"
    )
    container_body = json.dumps(
        {
            "properties": {
                "resource": {
                    "id": CONTAINER_NAME,
                    "partitionKey": {
                        "kind": "MultiHash",
                        "paths": ["/tenantId", "/threadId"],
                        "version": 2,
                    },
                    "defaultTtl": DEFAULT_TTL_SECONDS,
                },
                "options": {},
            }
        },
        separators=(",", ":"),
    )

    print(f"Creating hierarchical container '{CONTAINER_NAME}'...")
    if not run_quiet(
        "Create hierarchical memory container",
        [
            "az",
            "rest",
            "--method",
            "put",
            "--url",
            container_url,
            "--body",
            container_body,
        ],
    ):
        return False

    print(f"Container created: {CONTAINER_NAME}")
    print("  Partition key paths: /tenantId, /threadId")
    print(f"  Default TTL: {DEFAULT_TTL_SECONDS} seconds")
    return True


def create_cosmos_resources(account_name: str) -> bool:
    if not create_resource_group():
        return False
    print()

    account_state = _account_state(account_name)
    if account_state == "Succeeded":
        print(f"Cosmos DB account already exists: {account_name}")
    elif account_state in ("Failed", "Canceled"):
        print(f"A previous deployment is in a {account_state} state.")
        print("Deleting the failed account before trying again...")
        if not run_quiet(
            "Delete failed Cosmos DB account",
            [
                "az",
                "cosmosdb",
                "delete",
                "--resource-group",
                rg,
                "--name",
                account_name,
                "--yes",
            ],
        ):
            return False
        if not _wait_for_account_name_release(account_name):
            return False
        print("Failed account deleted.")
        account_state = ""
    elif account_state:
        print(
            f"Cosmos DB account '{account_name}' is still provisioning "
            f"(State: {account_state})."
        )
        print("Please wait for it to finish, then check the deployment status.")
        return True

    if not account_state:
        print(f"Creating Cosmos DB account '{account_name}' in '{location}'...")
        print("This may take several minutes...")
        if not _create_account_resource(account_name):
            return False
        print("Cosmos DB account created successfully")

    database_exists = az_query(
        [
            "az",
            "cosmosdb",
            "sql",
            "database",
            "show",
            "--resource-group",
            rg,
            "--account-name",
            account_name,
            "--name",
            DATABASE_NAME,
            "--query",
            "name",
            "-o",
            "tsv",
        ]
    )
    if database_exists:
        print(f"Database already exists: {DATABASE_NAME}")
    else:
        print(f"Creating database '{DATABASE_NAME}'...")
        if not run_quiet(
            "Create database",
            [
                "az",
                "cosmosdb",
                "sql",
                "database",
                "create",
                "--resource-group",
                rg,
                "--account-name",
                account_name,
                "--name",
                DATABASE_NAME,
            ],
        ):
            return False
        print(f"Database created: {DATABASE_NAME}")

    if not _create_memory_container(account_name):
        return False

    print()
    print("Use option 2 to configure Entra ID access.")
    return True


def _account_id(account_name: str) -> str:
    return az_query(
        [
            "az",
            "cosmosdb",
            "show",
            "--resource-group",
            rg,
            "--name",
            account_name,
            "--query",
            "id",
            "-o",
            "tsv",
        ]
    )


def _cosmos_role_assignment(account_name: str, user_object_id: str) -> str:
    return az_query(
        [
            "az",
            "cosmosdb",
            "sql",
            "role",
            "assignment",
            "list",
            "--resource-group",
            rg,
            "--account-name",
            account_name,
            "--query",
            f"[?principalId=='{user_object_id}'] | [0].id",
            "-o",
            "tsv",
        ]
    )


def configure_entra_access(account_name: str, user_object_id: str) -> bool:
    print("Configuring Microsoft Entra ID access...")
    status = _account_state(account_name)
    if not status:
        print(f"Error: Cosmos DB account '{account_name}' not found.")
        print("Please run option 1 to create the resources, then try again.")
        return False
    if status != "Succeeded":
        print(f"Error: Cosmos DB account is not ready (current state: {status}).")
        print("Please wait for deployment to complete. Use option 3 to check status.")
        return False

    user_upn = az_query(
        [
            "az",
            "ad",
            "signed-in-user",
            "show",
            "--query",
            "userPrincipalName",
            "-o",
            "tsv",
        ]
    )
    account_id = _account_id(account_name)
    if not user_upn or not account_id:
        print("Error: Unable to retrieve the signed-in user or Cosmos DB account ID.")
        return False

    azure_role = az_query(
        [
            "az",
            "role",
            "assignment",
            "list",
            "--assignee",
            user_object_id,
            "--scope",
            account_id,
            "--role",
            "Contributor",
            "--query",
            "[0].id",
            "-o",
            "tsv",
        ]
    )
    if azure_role:
        print("Azure RBAC Contributor role already assigned")
    elif not run_quiet(
        "Assign Azure RBAC Contributor role",
        [
            "az",
            "role",
            "assignment",
            "create",
            "--assignee",
            user_object_id,
            "--scope",
            account_id,
            "--role",
            "Contributor",
        ],
    ):
        return False
    else:
        print("Azure RBAC Contributor role assigned")

    cosmos_role = _cosmos_role_assignment(account_name, user_object_id)
    if cosmos_role:
        print("Cosmos DB Data Contributor role already assigned")
    elif not run_quiet(
        "Assign Cosmos DB Data Contributor role",
        [
            "az",
            "cosmosdb",
            "sql",
            "role",
            "assignment",
            "create",
            "--resource-group",
            rg,
            "--account-name",
            account_name,
            "--role-definition-name",
            "Cosmos DB Built-in Data Contributor",
            "--principal-id",
            user_object_id,
            "--scope",
            account_id,
        ],
    ):
        return False
    else:
        print("Cosmos DB Data Contributor role assigned")

    print()
    print(f"Entra ID access configured for: {user_upn}")
    print("  - Azure RBAC Contributor: manage the database")
    print("  - Cosmos DB Data Contributor: read and write memory items")
    return True


def check_deployment_status(account_name: str, user_object_id: str) -> bool:
    print("Checking deployment status...")
    print()
    status = _account_state(account_name)
    print(f"Cosmos DB Account ({account_name}):")
    if not status:
        print("  Status: Not created")
        return True
    print(f"  Status: {status}")
    if status != "Succeeded":
        return True

    database = az_query(
        [
            "az",
            "cosmosdb",
            "sql",
            "database",
            "show",
            "--resource-group",
            rg,
            "--account-name",
            account_name,
            "--name",
            DATABASE_NAME,
            "--query",
            "name",
            "-o",
            "tsv",
        ]
    )
    container = _container_exists(account_name)
    print(f"  Database {DATABASE_NAME}: {'Created' if database else 'Not created'}")
    print(f"  Container {CONTAINER_NAME}: {'Created' if container else 'Not created'}")

    account_id = _account_id(account_name)
    azure_role = az_query(
        [
            "az",
            "role",
            "assignment",
            "list",
            "--assignee",
            user_object_id,
            "--scope",
            account_id,
            "--role",
            "Contributor",
            "--query",
            "[0].id",
            "-o",
            "tsv",
        ]
    )
    cosmos_role = _cosmos_role_assignment(account_name, user_object_id)
    if azure_role and cosmos_role:
        print("  Entra ID access: Configured")
    elif azure_role or cosmos_role:
        print("  WARNING: Entra ID access is only partially configured")
    else:
        print("  WARNING: Entra ID access is not configured")
    return True


def retrieve_connection_info(account_name: str, user_object_id: str) -> bool:
    print("Retrieving connection information...")
    if _account_state(account_name) != "Succeeded":
        print(f"Error: Cosmos DB account '{account_name}' is not ready.")
        print("Please run option 1 to create the resources, then try again.")
        return False
    if not _cosmos_role_assignment(account_name, user_object_id):
        print("Error: Entra ID data access is not configured for this account.")
        print("Please run option 2 to configure Entra ID access, then try again.")
        return False
    if not _container_exists(account_name):
        print(f"Error: Cosmos DB container '{CONTAINER_NAME}' was not found.")
        print("Please run option 1 to create the resources, then try again.")
        return False

    endpoint = az_query(
        [
            "az",
            "cosmosdb",
            "show",
            "--resource-group",
            rg,
            "--name",
            account_name,
            "--query",
            "documentEndpoint",
            "-o",
            "tsv",
        ]
    )
    if not endpoint:
        print("Error: Unable to retrieve the Cosmos DB endpoint.")
        return False

    write_env_files(
        {
            "COSMOS_ENDPOINT": endpoint,
            "COSMOS_DATABASE": DATABASE_NAME,
            "COSMOS_CONTAINER": CONTAINER_NAME,
        }
    )
    print()
    print("Cosmos DB Connection Information")
    print("===========================================================")
    print(f"Endpoint: {endpoint}")
    print(f"Database: {DATABASE_NAME}")
    print(f"Container: {CONTAINER_NAME}")
    print("Authentication: Microsoft Entra ID (DefaultAzureCredential)")
    print()
    print("Environment variables saved to .env and .env.ps1")
    return True


def show_menu(account_name: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    Azure Cosmos DB Persistent Memory Deployment Menu")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Account Name: {account_name}")
    print(f"Location: {location}")
    print("=====================================================================")
    print("1. Create Cosmos DB account, database, and container")
    print("2. Configure Entra ID access")
    print("3. Check deployment status")
    print("4. Retrieve connection info")
    print("5. Exit")
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
    account_name = _derived_account_name(user_object_id)

    while True:
        show_menu(account_name)
        choice = input("Please select an option (1-5): ").strip()
        if choice in {"1", "2", "3", "4", "5"}:
            clear_screen()

        if choice == "1":
            print()
            create_cosmos_resources(account_name)
            print()
            pause()
        elif choice == "2":
            print()
            configure_entra_access(account_name, user_object_id)
            print()
            pause()
        elif choice == "3":
            print()
            check_deployment_status(account_name, user_object_id)
            print()
            pause()
        elif choice == "4":
            print()
            retrieve_connection_info(account_name, user_object_id)
            print()
            pause()
        elif choice == "5":
            print("Exiting...")
            clear_screen()
            sys.exit(0)
        else:
            print()
            print("Invalid option. Please select 1-5.")
            print()
            pause()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
