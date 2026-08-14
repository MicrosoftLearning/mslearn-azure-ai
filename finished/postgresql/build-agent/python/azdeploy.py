# =============================================================================
# Change the values of these variables as needed.
# =============================================================================

# rg = "<your-resource-group-name>"  # Resource Group name
# location = "<your-azure-region>"   # Azure region for the resources

rg = "rg-exercises"  # Resource Group name
location = "canadacentral"  # Azure region for the resources

# =============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# =============================================================================

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

DB_NAME = "postgres"

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
    return f"psql-agent-{user_hash}"


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


def create_postgres_server(server_name: str, user_object_id: str) -> bool:
    if not create_resource_group():
        return False
    print()
    print(f"Creating Azure Database for PostgreSQL Flexible Server '{server_name}'...")
    print("This may take several minutes...")

    existing = az_query(
        ["az", "postgres", "flexible-server", "show",
         "--resource-group", rg, "--name", server_name,
         "--query", "name", "-o", "tsv"]
    )
    if existing:
        print(f"PostgreSQL server already exists: {server_name}")
        return True

    user_upn = az_query(
        ["az", "ad", "signed-in-user", "show",
         "--query", "userPrincipalName", "-o", "tsv"]
    )
    if not user_upn:
        print("Error: Unable to retrieve signed-in user information.")
        print("Please ensure you are logged in with 'az login'.")
        return False

    if not run_quiet(
        "Create PostgreSQL Flexible Server",
        [
            "az", "postgres", "flexible-server", "create",
            "--resource-group", rg,
            "--name", server_name,
            "--location", location,
            "--sku-name", "Standard_B1ms",
            "--tier", "Burstable",
            "--storage-size", "32",
            "--version", "16",
            "--public-access", "0.0.0.0-255.255.255.255",
            "--microsoft-entra-auth", "Enabled",
            "--password-auth", "Disabled",
            "--admin-object-id", user_object_id,
            "--admin-display-name", user_upn,
            "--admin-type", "User",
        ],
    ):
        return False
    print("PostgreSQL server created successfully")
    print(f"  Microsoft Entra administrator: {user_upn}")
    return True


def configure_entra_admin(server_name: str, user_object_id: str) -> bool:
    print("Configuring Microsoft Entra administrator...")

    state = az_query(
        ["az", "postgres", "flexible-server", "show",
         "--resource-group", rg, "--name", server_name,
         "--query", "state", "-o", "tsv"]
    )
    if not state:
        print(f"Error: PostgreSQL server '{server_name}' not found.")
        print("Please run option 1 to create the PostgreSQL server, then try again.")
        return False
    if state != "Ready":
        print(f"Error: PostgreSQL server is not ready (current state: {state}).")
        print("Please wait for deployment to complete. Use option 3 to check status.")
        return False

    user_upn = az_query(
        ["az", "ad", "signed-in-user", "show",
         "--query", "userPrincipalName", "-o", "tsv"]
    )
    if not user_upn:
        print("Error: Unable to retrieve signed-in user information.")
        print("Please ensure you are logged in with 'az login'.")
        return False

    print(f"Setting '{user_upn}' as Entra administrator...")

    if not run_quiet(
        "Configure Entra administrator",
        [
            "az", "postgres", "flexible-server", "microsoft-entra-admin", "create",
            "--resource-group", rg,
            "--server-name", server_name,
            "--display-name", user_upn,
            "--object-id", user_object_id,
        ],
    ):
        return False
    print(f"Microsoft Entra administrator configured: {user_upn}")
    return True


def check_deployment_status(server_name: str) -> bool:
    print("Checking deployment status...")
    print()

    print(f"PostgreSQL Server ({server_name}):")
    state = az_query(
        ["az", "postgres", "flexible-server", "show",
         "--resource-group", rg, "--name", server_name,
         "--query", "state", "-o", "tsv"]
    )
    if not state:
        print("  Status: Not created")
        return True

    print(f"  Status: {state}")
    if state == "Ready":
        print("  PostgreSQL server is ready")

    admin_name = az_query(
        ["az", "postgres", "flexible-server", "microsoft-entra-admin", "list",
         "--resource-group", rg, "--server-name", server_name,
         "--query", "[0].principalName", "-o", "tsv"]
    )
    if admin_name:
        print(f"  Entra administrator: {admin_name}")
    else:
        print("  WARNING: Entra administrator not configured")
    return True


def retrieve_connection_info(server_name: str) -> bool:
    print("Retrieving connection information...")

    state = az_query(
        ["az", "postgres", "flexible-server", "show",
         "--resource-group", rg, "--name", server_name,
         "--query", "state", "-o", "tsv"]
    )
    if not state:
        print(f"Error: PostgreSQL server '{server_name}' not found.")
        print("Please run option 1 to create the PostgreSQL server, then try again.")
        return False
    if state != "Ready":
        print(f"Error: PostgreSQL server is not ready (current state: {state}).")
        print("Please wait for deployment to complete. Use option 3 to check status.")
        return False

    admin_name = az_query(
        ["az", "postgres", "flexible-server", "microsoft-entra-admin", "list",
         "--resource-group", rg, "--server-name", server_name,
         "--query", "[0].principalName", "-o", "tsv"]
    )
    if not admin_name:
        print(f"Error: Microsoft Entra administrator not configured on '{server_name}'.")
        print("Please run option 2 to configure the Entra administrator, then try again.")
        return False

    user_upn = az_query(
        ["az", "ad", "signed-in-user", "show",
         "--query", "userPrincipalName", "-o", "tsv"]
    )
    if not user_upn:
        print("Error: Unable to retrieve signed-in user information.")
        print("Please ensure you are logged in with 'az login'.")
        return False

    print("Retrieving access token...")
    access_token = az_query(
        ["az", "account", "get-access-token",
         "--resource-type", "oss-rdbms",
         "--query", "accessToken", "-o", "tsv"]
    )
    if not access_token:
        print("Error: Unable to retrieve access token.")
        return False

    db_host = f"{server_name}.postgres.database.azure.com"

    write_env_files({
        "DB_HOST": db_host,
        "DB_NAME": DB_NAME,
        "DB_USER": user_upn,
        "PGPASSWORD": access_token,
    })
    print()
    print("PostgreSQL Connection Information")
    print("===========================================================")
    print(f"Host: {db_host}")
    print(f"Database: {DB_NAME}")
    print(f"User: {user_upn}")
    print("Password: (Entra token - expires in ~1 hour)")
    print()
    print("Environment variables saved to .env and .env.ps1")
    return True


def show_menu(server_name: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    Azure Database for PostgreSQL Deployment Menu")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Server Name: {server_name}")
    print(f"Location: {location}")
    print("=====================================================================")
    print("1. Create PostgreSQL server with Entra authentication")
    print("2. Configure Microsoft Entra administrator")
    print("3. Check deployment status")
    print("4. Retrieve connection info and access token")
    print("5. Exit")
    print("=====================================================================")


def _preflight() -> None:
    script_dir = Path(__file__).resolve().parent
    if not (script_dir / "agent-backend").is_dir():
        print(
            "Error: 'agent-backend/' folder is missing next to azdeploy.py. "
            "Make sure you kept the exercise folder intact."
        )
        sys.exit(1)
    os.chdir(script_dir)


def main() -> None:
    _preflight()
    user_object_id = require_az_login()
    server_name = _derived_names(user_object_id)

    while True:
        show_menu(server_name)
        choice = input("Please select an option (1-5): ").strip()
        if choice in {"1", "2", "3", "4", "5"}:
            clear_screen()

        if choice == "1":
            print()
            create_postgres_server(server_name, user_object_id)
            print()
            pause()
        elif choice == "2":
            print()
            configure_entra_admin(server_name, user_object_id)
            print()
            pause()
        elif choice == "3":
            print()
            check_deployment_status(server_name)
            print()
            pause()
        elif choice == "4":
            print()
            retrieve_connection_info(server_name)
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
