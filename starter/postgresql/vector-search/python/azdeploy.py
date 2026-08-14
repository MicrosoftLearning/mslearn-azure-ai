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
import secrets
import shutil
import string
import subprocess
import sys
import time
from pathlib import Path

DB_NAME = "postgres"

os.environ.setdefault("AZURE_CORE_ONLY_SHOW_ERRORS", "true")

_EXE_CACHE: dict[str, str] = {}


def _throwaway_admin_password() -> str:
    # Password auth is disabled on the server, so this value is never used to
    # authenticate. It exists only to satisfy the CLI's create-time validation
    # across versions. It meets Azure's complexity rules: length 32 with at
    # least one uppercase, lowercase, digit, and non-alphanumeric character.
    upper = secrets.choice(string.ascii_uppercase)
    lower = secrets.choice(string.ascii_lowercase)
    digit = secrets.choice(string.digits)
    symbol = secrets.choice("!@#$%^&*()-_=+")
    pool = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    remaining = [secrets.choice(pool) for _ in range(28)]
    chars = [upper, lower, digit, symbol, *remaining]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


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
    return f"psql-vector-{user_hash}"


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


def _server_state(server_name: str) -> str:
    """Return the server's current state, or '' if it doesn't exist.

    Uses `az resource show` (an ARM read) instead of `az postgres flexible-server
    show` because ARM stays responsive even when the server is mid-operation,
    when the data-plane command can exit non-zero and hide an existing server.
    """
    return az_query([
        "az", "resource", "show",
        "--resource-group", rg,
        "--name", server_name,
        "--resource-type", "Microsoft.DBforPostgreSQL/flexibleServers",
        "--query", "properties.state", "-o", "tsv",
    ])


def _server_exists(server_name: str) -> bool:
    """Return True if the server exists as an ARM resource.

    Uses the resource id, which ARM populates as soon as the PUT is accepted,
    even before `properties.state` becomes meaningful. This catches an
    in-flight create started by a previous run that our state probe would miss.
    """
    return bool(az_query([
        "az", "resource", "show",
        "--resource-group", rg,
        "--name", server_name,
        "--resource-type", "Microsoft.DBforPostgreSQL/flexibleServers",
        "--query", "id", "-o", "tsv",
    ]))


def create_postgres_server(server_name: str, user_object_id: str) -> bool:
    if not create_resource_group():
        return False
    print()

    if _server_exists(server_name):
        state = _server_state(server_name) or "Provisioning"
        if state == "Ready":
            print(f"PostgreSQL server already exists: {server_name}")
            return True
        print(f"PostgreSQL server '{server_name}' already exists (state: {state}).")
        print("Azure is still processing an operation on this server, most likely")
        print("a create that was started by an earlier attempt.")
        print("Wait a few minutes, then use option 3 to check status.")
        return True

    print(f"Creating Azure Database for PostgreSQL Flexible Server '{server_name}'...")
    print("This may take several minutes...")

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
            "--admin-user", "pgadmin",
            "--admin-password", _throwaway_admin_password(),
            "--admin-object-id", user_object_id,
            "--admin-display-name", user_upn,
            "--admin-type", "User",
            "--yes",
        ],
    ):
        return False
    print("PostgreSQL server created successfully")
    print(f"  Microsoft Entra administrator: {user_upn}")
    return True


def _wait_for_ready(server_name: str, timeout_seconds: int = 600, poll_seconds: int = 15) -> bool:
    """Poll the server state until it returns to 'Ready' or the timeout elapses."""
    deadline = time.monotonic() + timeout_seconds
    last_state = ""
    while time.monotonic() < deadline:
        state = _server_state(server_name)
        if state == "Ready":
            return True
        if state and state != last_state:
            print(f"  Server state: {state} (waiting...)")
            last_state = state
        time.sleep(poll_seconds)
    print(f"Error: Timed out waiting for server '{server_name}' to return to Ready.")
    print("Use option 3 to check the current status, then try option 2 again.")
    return False


def configure_vector_parameter(server_name: str) -> bool:
    print("Configuring the vector extension allow-list...")

    state = _server_state(server_name)
    if not state:
        print(f"Error: PostgreSQL server '{server_name}' not found.")
        print("Please run option 1 to create the PostgreSQL server, then try again.")
        return False

    if state != "Ready":
        print(f"Server is not Ready (current state: {state}). Waiting for it to become Ready...")
        if not _wait_for_ready(server_name):
            return False

    current = az_query([
        "az", "postgres", "flexible-server", "parameter", "show",
        "--resource-group", rg,
        "--server-name", server_name,
        "--name", "azure.extensions",
        "--query", "value", "-o", "tsv",
    ])
    allowed = {item.strip().lower() for item in current.split(",") if item.strip()}
    if "vector" in allowed:
        print("Vector extension is already allow-listed. No changes needed.")
        return True

    print("Adding the vector extension to the server's allow-list.")
    print("The server will restart to apply the change. This can take 1-2 minutes...")
    if not run_quiet(
        "Allow-list vector extension",
        [
            "az", "postgres", "flexible-server", "parameter", "set",
            "--resource-group", rg,
            "--server-name", server_name,
            "--name", "azure.extensions",
            "--value", "vector",
        ],
    ):
        return False

    if not _wait_for_ready(server_name):
        return False
    print("Vector extension allow-listed and server is ready.")
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

    allowed_value = az_query([
        "az", "postgres", "flexible-server", "parameter", "show",
        "--resource-group", rg,
        "--server-name", server_name,
        "--name", "azure.extensions",
        "--query", "value", "-o", "tsv",
    ])
    allowed = {item.strip().lower() for item in allowed_value.split(",") if item.strip()}
    if "vector" in allowed:
        print("  Vector extension: allow-listed")
    else:
        print("  Vector extension: not allow-listed (run option 2 to configure)")
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
        print("Please run option 1 to create the PostgreSQL server, then try again.")
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
    print("2. Configure vector extension allow-list")
    print("3. Check deployment status")
    print("4. Retrieve connection info and access token")
    print("5. Exit")
    print("=====================================================================")


def _preflight() -> None:
    script_dir = Path(__file__).resolve().parent
    if not (script_dir / "client").is_dir():
        print(
            "Error: 'client/' folder is missing next to azdeploy.py. "
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
            configure_vector_parameter(server_name)
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
