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
import time
from pathlib import Path

CONTAINER_TYPE = "PythonLTS"
MAX_SESSIONS = "5"
COOLDOWN_PERIOD = "300"
NETWORK_STATUS = "EgressDisabled"
EXECUTOR_ROLE = "Azure ContainerApps Session Executor"

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


def _session_pool_name(user_object_id: str) -> str:
    user_hash = hashlib.sha1(user_object_id.encode("utf-8")).hexdigest()[:8]
    return f"sp-code-{user_hash}"


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
    elif exists == "true":
        print(f"Resource group already exists: {rg}")
    else:
        print("Error: Could not determine whether the resource group exists.")
        return False
    return True


def _pool_state(session_pool_name: str) -> str:
    return az_query(
        [
            "az",
            "containerapp",
            "sessionpool",
            "show",
            "--name",
            session_pool_name,
            "--resource-group",
            rg,
            "--query",
            "properties.provisioningState",
            "-o",
            "tsv",
        ]
    )


def _delete_failed_pool(session_pool_name: str) -> bool:
    print(f"Deleting failed session pool '{session_pool_name}' before retrying...")
    if not run_quiet(
        "Delete failed session pool",
        [
            "az",
            "containerapp",
            "sessionpool",
            "delete",
            "--name",
            session_pool_name,
            "--resource-group",
            rg,
            "--yes",
        ],
    ):
        return False

    for _ in range(30):
        if not _pool_state(session_pool_name):
            return True
        time.sleep(10)

    print("Error: Timed out waiting for the failed session pool to be deleted.")
    return False


def _save_environment(session_pool_name: str) -> bool:
    endpoint = az_query(
        [
            "az",
            "containerapp",
            "sessionpool",
            "show",
            "--name",
            session_pool_name,
            "--resource-group",
            rg,
            "--query",
            "properties.poolManagementEndpoint",
            "-o",
            "tsv",
        ]
    )
    if not endpoint:
        print("Error: The session pool management endpoint is not available.")
        return False

    write_env_files(
        {
            "RESOURCE_GROUP": rg,
            "SESSION_POOL_NAME": session_pool_name,
            "SESSION_POOL_ENDPOINT": endpoint,
            "LOCATION": location,
        }
    )
    print()
    print("Environment variables saved to .env and .env.ps1")
    print("Run 'source .env' (Bash) or '. .\\.env.ps1' (PowerShell) to load them.")
    return True


def create_session_pool(session_pool_name: str) -> bool:
    if not create_resource_group():
        return False

    print()
    print(f"Checking/creating session pool '{session_pool_name}'...")
    state = _pool_state(session_pool_name)
    if state == "Succeeded":
        print(f"Session pool already exists: {session_pool_name}")
        return _save_environment(session_pool_name)
    if state in {"Failed", "Canceled"}:
        if not _delete_failed_pool(session_pool_name):
            return False
    elif state:
        print(f"Session pool is still provisioning. Current status: {state}")
        return False

    print("Creating the Python code interpreter session pool...")
    print("This may take a few minutes...")
    if not run_quiet(
        "Create session pool",
        [
            "az",
            "containerapp",
            "sessionpool",
            "create",
            "--name",
            session_pool_name,
            "--resource-group",
            rg,
            "--location",
            location,
            "--container-type",
            CONTAINER_TYPE,
            "--max-sessions",
            MAX_SESSIONS,
            "--cooldown-period",
            COOLDOWN_PERIOD,
            "--network-status",
            NETWORK_STATUS,
        ],
    ):
        print(
            "The selected region might not have capacity for dynamic sessions. "
            "Change the location near the top of azdeploy.py and retry."
        )
        return False

    print(f"Session pool created: {session_pool_name}")
    return _save_environment(session_pool_name)


def _pool_resource_id(session_pool_name: str) -> str:
    return az_query(
        [
            "az",
            "containerapp",
            "sessionpool",
            "show",
            "--name",
            session_pool_name,
            "--resource-group",
            rg,
            "--query",
            "id",
            "-o",
            "tsv",
        ]
    )


def _role_assignment_id(user_object_id: str, resource_id: str) -> str:
    return az_query(
        [
            "az",
            "role",
            "assignment",
            "list",
            "--assignee-object-id",
            user_object_id,
            "--scope",
            resource_id,
            "--role",
            EXECUTOR_ROLE,
            "--query",
            "[0].id",
            "-o",
            "tsv",
        ]
    )


def assign_executor_role(
    session_pool_name: str, user_object_id: str
) -> bool:
    resource_id = _pool_resource_id(session_pool_name)
    if not resource_id:
        print("Error: Create the session pool before assigning the executor role.")
        return False

    print(f"Checking role assignment for '{EXECUTOR_ROLE}'...")
    if _role_assignment_id(user_object_id, resource_id):
        print("Executor role is already assigned to the signed-in user.")
        return True

    if not run_quiet(
        "Assign session executor role",
        [
            "az",
            "role",
            "assignment",
            "create",
            "--assignee-object-id",
            user_object_id,
            "--assignee-principal-type",
            "User",
            "--role",
            EXECUTOR_ROLE,
            "--scope",
            resource_id,
        ],
    ):
        return False

    print("Executor role assigned to the signed-in user.")
    print("The role assignment can take a few minutes to become effective.")
    return True


def check_deployment_status(
    session_pool_name: str, user_object_id: str
) -> bool:
    print("Checking deployment status...")
    print()
    print(f"Session Pool ({session_pool_name}):")
    state = _pool_state(session_pool_name)
    if not state:
        print("  Status: Not created")
        return True

    print(f"  Status: {state}")
    endpoint = az_query(
        [
            "az",
            "containerapp",
            "sessionpool",
            "show",
            "--name",
            session_pool_name,
            "--resource-group",
            rg,
            "--query",
            "properties.poolManagementEndpoint",
            "-o",
            "tsv",
        ]
    )
    if endpoint:
        print(f"  Management endpoint: {endpoint}")

    resource_id = _pool_resource_id(session_pool_name)
    role_assigned = bool(
        resource_id and _role_assignment_id(user_object_id, resource_id)
    )
    print(f"  Executor role assigned: {'Yes' if role_assigned else 'No'}")
    return True


def show_menu(session_pool_name: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("  Azure Container Apps Dynamic Sessions - Deployment Script")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"Session Pool: {session_pool_name}")
    print("=====================================================================")
    print("1. Create the code interpreter session pool")
    print("2. Assign the session executor role")
    print("3. Check deployment status")
    print("4. Exit")
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
    session_pool_name = _session_pool_name(user_object_id)

    while True:
        show_menu(session_pool_name)
        choice = input("Please select an option (1-4): ").strip()
        if choice in {"1", "2", "3", "4"}:
            clear_screen()

        if choice == "1":
            print()
            create_session_pool(session_pool_name)
            print()
            pause()
        elif choice == "2":
            print()
            assign_executor_role(session_pool_name, user_object_id)
            print()
            pause()
        elif choice == "3":
            print()
            check_deployment_status(session_pool_name, user_object_id)
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
