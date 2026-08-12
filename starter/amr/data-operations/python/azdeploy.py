# =============================================================================
# Change the values of these variables as needed.
# =============================================================================

# rg = "<your-resource-group-name>"  # Resource Group name
# location = "<your-azure-region>"   # Azure region for the resources

rg = "rg-exercises"  # Resource Group name
location = "westus2"  # Azure region for the resources

# =============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# =============================================================================

import hashlib
import os
import shutil
import subprocess
import sys
import time
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


def derived_cache_name(user_object_id: str) -> str:
    user_hash = hashlib.sha1(user_object_id.encode("utf-8")).hexdigest()[:8]
    return f"amr-exercise-{user_hash}"


def create_resource_group() -> bool:
    print(f"Checking resource group '{rg}'...")
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


def create_redis_resource(cache_name: str) -> bool:
    if not create_resource_group():
        return False
    print()

    cluster_state = az_query(
        [
            "az", "redisenterprise", "show",
            "--resource-group", rg,
            "--name", cache_name,
            "--query", "provisioningState",
            "-o", "tsv",
        ]
    )
    if cluster_state == "Succeeded":
        print(
            f"Azure Managed Redis resource already exists: {cache_name} "
            f"(State: {cluster_state})"
        )
        return True
    if cluster_state in ("Failed", "Canceled"):
        print(f"A previous deployment of '{cache_name}' is in a {cluster_state} state.")
        print("Deleting the failed resource before trying again...")
        if not run_quiet(
            "Delete failed Azure Managed Redis resource",
            [
                "az", "redisenterprise", "delete",
                "--resource-group", rg,
                "--name", cache_name,
                "--yes",
            ],
        ):
            return False
        waited = 0
        while az_query(
            [
                "az", "redisenterprise", "show",
                "--resource-group", rg,
                "--name", cache_name,
                "--query", "provisioningState",
                "-o", "tsv",
            ]
        ):
            if waited >= 300:
                print("Error: Timed out waiting for the failed resource to finish deleting.")
                print("Please wait a few minutes, then run option 1 again.")
                return False
            time.sleep(10)
            waited += 10
        print("Failed resource deleted.")
        print()
    elif cluster_state:
        print(
            f"Azure Managed Redis resource '{cache_name}' is still provisioning "
            f"(State: {cluster_state})."
        )
        print("Please wait for it to finish, then check the deployment status from the menu.")
        return True

    print(f"Creating Azure Managed Redis resource '{cache_name}' in '{location}'...")
    print("This takes 5-10 minutes to complete. Please wait...")
    if not run_quiet(
        "Create Azure Managed Redis resource",
        [
            "az", "redisenterprise", "create",
            "--resource-group", rg,
            "--name", cache_name,
            "--location", location,
            "--sku", "Balanced_B0",
            "--public-network-access", "Enabled",
            "--no-database",
        ],
    ):
        print()
        print("The deployment failed. This is most often caused by a temporary")
        print(f"lack of capacity for this SKU in the '{location}' region.")
        print()
        print("To resolve this:")
        print("  1. Choose option 4 to exit the script.")
        print("  2. Near the top of this script, change the 'location' variable to a")
        print("     different region, such as eastus2, australiaeast, or canadacentral.")
        print("  3. Run the script again and choose option 1. The failed resource is")
        print("     deleted automatically before the next attempt.")
        return False

    print()
    print(f"Azure Managed Redis resource created successfully: {cache_name}")
    return True


def check_deployment_status(cache_name: str) -> bool:
    print("Checking deployment status...")
    print()
    print(f"Cluster ({cache_name}):")
    cluster_state = az_query(
        [
            "az", "redisenterprise", "show",
            "--resource-group", rg,
            "--name", cache_name,
            "--query", "provisioningState",
            "-o", "tsv",
        ]
    )
    print(f"  Provisioning state: {cluster_state}" if cluster_state else "  Status: Not created")

    print()
    print("Database:")
    db_state = az_query(
        [
            "az", "redisenterprise", "database", "show",
            "--resource-group", rg,
            "--cluster-name", cache_name,
            "--query", "provisioningState",
            "-o", "tsv",
        ]
    )
    print(f"  Provisioning state: {db_state}" if db_state else "  Status: Not created")
    return True


def create_database_and_get_key(cache_name: str) -> bool:
    cluster_state = az_query(
        [
            "az", "redisenterprise", "show",
            "--resource-group", rg,
            "--name", cache_name,
            "--query", "provisioningState",
            "-o", "tsv",
        ]
    )
    if cluster_state != "Succeeded":
        print(f"Error: Cluster is not ready (State: {cluster_state or 'Not created'}).")
        print("Please check the deployment status (option 2) and wait until provisioning succeeds.")
        return False

    db_state = az_query(
        [
            "az", "redisenterprise", "database", "show",
            "--resource-group", rg,
            "--cluster-name", cache_name,
            "--query", "provisioningState",
            "-o", "tsv",
        ]
    )
    if db_state:
        print(f"Database already exists (State: {db_state}). Enabling access key auth...")
        if not run_quiet(
            "Enable database access key authentication",
            [
                "az", "redisenterprise", "database", "update",
                "--resource-group", rg,
                "--cluster-name", cache_name,
                "--access-keys-auth", "Enabled",
            ],
        ):
            return False
    else:
        print("Creating database with access key authentication enabled...")
        if not run_quiet(
            "Create database",
            [
                "az", "redisenterprise", "database", "create",
                "--resource-group", rg,
                "--cluster-name", cache_name,
                "--client-protocol", "Encrypted",
                "--clustering-policy", "NoCluster",
                "--eviction-policy", "AllKeysLRU",
                "--port", "10000",
                "--access-keys-auth", "Enabled",
            ],
        ):
            return False

    print("Retrieving endpoint and access key...")
    hostname = az_query(
        [
            "az", "redisenterprise", "show",
            "--resource-group", rg,
            "--name", cache_name,
            "--query", "hostName",
            "-o", "tsv",
        ]
    )
    primary_key = az_query(
        [
            "az", "redisenterprise", "database", "list-keys",
            "--cluster-name", cache_name,
            "--resource-group", rg,
            "--query", "primaryKey",
            "-o", "tsv",
        ]
    )
    if not hostname or not primary_key:
        print()
        print("Error: Unable to retrieve endpoint or access key.")
        print("Please check the deployment status to ensure the resource is fully provisioned.")
        return False

    write_env_files({"REDIS_HOST": hostname, "REDIS_KEY": primary_key})
    clear_screen()
    print()
    print("Redis Connection Information")
    print("===========================================================")
    print(f"Endpoint: {hostname}")
    print(f"Primary Key: {primary_key}")
    print()
    print("Values have been saved to .env and .env.ps1 files")
    return True


def show_menu(cache_name: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    Azure Managed Redis Deployment Menu")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Cache Name: {cache_name}")
    print(f"Location: {location}")
    print("=====================================================================")
    print("1. Create Azure Managed Redis resource")
    print("2. Check deployment status")
    print("3. Create database and retrieve endpoint and access key")
    print("4. Exit")
    print("=====================================================================")


def _preflight() -> None:
    script_dir = Path(__file__).resolve().parent
    if not (script_dir / "main.py").is_file():
        print(
            "Error: 'main.py' is missing next to azdeploy.py. "
            "Make sure you kept the exercise folder intact."
        )
        sys.exit(1)
    os.chdir(script_dir)


def main() -> None:
    _preflight()
    cache_name = derived_cache_name(require_az_login())

    while True:
        show_menu(cache_name)
        choice = input("Please select an option (1-4): ").strip()
        if choice in {"1", "2", "3", "4"}:
            clear_screen()

        if choice == "1":
            print()
            create_redis_resource(cache_name)
            print()
            pause()
        elif choice == "2":
            print()
            check_deployment_status(cache_name)
            print()
            pause()
        elif choice == "3":
            print()
            create_database_and_get_key(cache_name)
            print()
            pause()
        elif choice == "4":
            print("Exiting...")
            clear_screen()
            sys.exit(0)
        else:
            print()
            print("Invalid option. Please select 1-4.")
            print()
            pause()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)