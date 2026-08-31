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
import tempfile
import time
import zipfile
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


def _derived_names(user_object_id: str) -> dict[str, str]:
    user_hash = hashlib.sha1(user_object_id.encode("utf-8")).hexdigest()[:8]
    return {
        "storage": f"stdurable{user_hash}",
        "identity": f"id-durable-{user_hash}",
        "insights": f"appi-durable-{user_hash}",
        "function": f"func-durable-{user_hash}",
    }


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


def _ensure_storage_account(storage_name: str) -> str:
    state = az_query(
        [
            "az",
            "storage",
            "account",
            "show",
            "--name",
            storage_name,
            "--resource-group",
            rg,
            "--query",
            "provisioningState",
            "-o",
            "tsv",
        ]
    )
    if state == "Succeeded":
        print(f"Storage account already exists: {storage_name}")
    elif state:
        print(
            f"Error: Storage account '{storage_name}' is not ready "
            f"(current state: {state})."
        )
        return ""
    else:
        if not run_quiet(
            "Create storage account",
            [
                "az",
                "storage",
                "account",
                "create",
                "--name",
                storage_name,
                "--resource-group",
                rg,
                "--location",
                location,
                "--sku",
                "Standard_LRS",
                "--kind",
                "StorageV2",
                "--allow-blob-public-access",
                "false",
                "--allow-shared-key-access",
                "false",
            ],
        ):
            return ""
        print(f"Storage account created: {storage_name}")

    return az_query(
        [
            "az",
            "storage",
            "account",
            "show",
            "--name",
            storage_name,
            "--resource-group",
            rg,
            "--query",
            "id",
            "-o",
            "tsv",
        ]
    )


def _ensure_identity(identity_name: str) -> tuple[str, str, str]:
    identity_id = az_query(
        [
            "az",
            "identity",
            "show",
            "--name",
            identity_name,
            "--resource-group",
            rg,
            "--query",
            "id",
            "-o",
            "tsv",
        ]
    )
    if not identity_id:
        if not run_quiet(
            "Create managed identity",
            [
                "az",
                "identity",
                "create",
                "--name",
                identity_name,
                "--resource-group",
                rg,
                "--location",
                location,
            ],
        ):
            return "", "", ""
        print(f"Managed identity created: {identity_name}")
    else:
        print(f"Managed identity already exists: {identity_name}")

    identity_id = az_query(
        [
            "az",
            "identity",
            "show",
            "--name",
            identity_name,
            "--resource-group",
            rg,
            "--query",
            "id",
            "-o",
            "tsv",
        ]
    )
    principal_id = az_query(
        [
            "az",
            "identity",
            "show",
            "--name",
            identity_name,
            "--resource-group",
            rg,
            "--query",
            "principalId",
            "-o",
            "tsv",
        ]
    )
    client_id = az_query(
        [
            "az",
            "identity",
            "show",
            "--name",
            identity_name,
            "--resource-group",
            rg,
            "--query",
            "clientId",
            "-o",
            "tsv",
        ]
    )
    return identity_id, principal_id, client_id


def _assign_storage_roles(principal_id: str, storage_id: str) -> bool:
    roles = [
        "Storage Blob Data Contributor",
        "Storage Queue Data Contributor",
        "Storage Table Data Contributor",
    ]
    for role in roles:
        assignment = az_query(
            [
                "az",
                "role",
                "assignment",
                "list",
                "--assignee-object-id",
                principal_id,
                "--scope",
                storage_id,
                "--role",
                role,
                "--query",
                "[0].id",
                "-o",
                "tsv",
            ]
        )
        if assignment:
            print(f"Role already assigned: {role}")
            continue
        if not run_quiet(
            f"Assign {role}",
            [
                "az",
                "role",
                "assignment",
                "create",
                "--assignee-object-id",
                principal_id,
                "--assignee-principal-type",
                "ServicePrincipal",
                "--scope",
                storage_id,
                "--role",
                role,
            ],
        ):
            return False
        print(f"Role assigned: {role}")
    return True


def _ensure_application_insights(insights_name: str) -> bool:
    state = az_query(
        [
            "az",
            "monitor",
            "app-insights",
            "component",
            "show",
            "--app",
            insights_name,
            "--resource-group",
            rg,
            "--query",
            "provisioningState",
            "-o",
            "tsv",
        ]
    )
    if state == "Succeeded":
        print(f"Application Insights already exists: {insights_name}")
        return True
    if state:
        print(
            f"Error: Application Insights '{insights_name}' is not ready "
            f"(current state: {state})."
        )
        return False
    if not run_quiet(
        "Create Application Insights",
        [
            "az",
            "monitor",
            "app-insights",
            "component",
            "create",
            "--app",
            insights_name,
            "--resource-group",
            rg,
            "--location",
            location,
            "--kind",
            "web",
            "--application-type",
            "web",
        ],
    ):
        return False
    print(f"Application Insights created: {insights_name}")
    return True


def _delete_failed_function_app(function_name: str) -> bool:
    print(f"Deleting failed Function App '{function_name}' before retrying...")
    if not run_quiet(
        "Delete failed Function App",
        [
            "az",
            "functionapp",
            "delete",
            "--name",
            function_name,
            "--resource-group",
            rg,
        ],
    ):
        return False

    for _ in range(60):
        if not az_query(
            [
                "az",
                "functionapp",
                "show",
                "--name",
                function_name,
                "--resource-group",
                rg,
                "--query",
                "name",
                "-o",
                "tsv",
            ]
        ):
            return True
        time.sleep(5)

    print(f"Error: Function App '{function_name}' was not deleted within 5 minutes.")
    return False


def _start_function_app(function_name: str) -> bool:
    if not run_quiet(
        "Start Function App",
        [
            "az",
            "functionapp",
            "start",
            "--name",
            function_name,
            "--resource-group",
            rg,
        ],
    ):
        return False
    print(f"Function App started: {function_name}")
    return True


def _ensure_function_app(
    names: dict[str, str],
    identity_id: str,
    client_id: str,
) -> bool:
    state = az_query(
        [
            "az",
            "functionapp",
            "show",
            "--name",
            names["function"],
            "--resource-group",
            rg,
            "--query",
            "state",
            "-o",
            "tsv",
        ]
    )
    if state == "Running":
        print(f"Function App already exists: {names['function']}")
    elif state == "Stopped":
        if not _start_function_app(names["function"]):
            return False
    elif state in {"Failed", "Canceled"}:
        if not _delete_failed_function_app(names["function"]):
            return False
        state = ""
    elif state:
        print(
            f"Error: Function App '{names['function']}' is still provisioning "
            f"(current state: {state})."
        )
        return False

    if not state:
        print("Creating the Flex Consumption Function App...")
        if not run_quiet(
            "Create Function App",
            [
                "az",
                "functionapp",
                "create",
                "--name",
                names["function"],
                "--resource-group",
                rg,
                "--storage-account",
                names["storage"],
                "--flexconsumption-location",
                location,
                "--runtime",
                "python",
                "--runtime-version",
                "3.12",
                "--app-insights",
                names["insights"],
                "--assign-identity",
                identity_id,
                "--deployment-storage-auth-type",
                "UserAssignedIdentity",
                "--deployment-storage-auth-value",
                identity_id,
            ],
        ):
            print()
            print(
                "The selected region may not support Flex Consumption or may "
                "have limited capacity."
            )
            print("Change the location at the top of this script, then run option 1 again.")
            return False
        print(f"Function App created: {names['function']}")

    if not run_quiet(
        "Configure Function App settings",
        [
            "az",
            "functionapp",
            "config",
            "appsettings",
            "set",
            "--name",
            names["function"],
            "--resource-group",
            rg,
            "--settings",
            f"AZURE_CLIENT_ID={client_id}",
            f"AzureWebJobsStorage__accountName={names['storage']}",
            "AzureWebJobsStorage__credential=managedidentity",
            f"AzureWebJobsStorage__clientId={client_id}",
            f"STORAGE_ACCOUNT_NAME={names['storage']}",
        ],
    ):
        return False

    if not run_quiet(
        "Remove the storage connection string setting",
        [
            "az",
            "functionapp",
            "config",
            "appsettings",
            "delete",
            "--name",
            names["function"],
            "--resource-group",
            rg,
            "--setting-names",
            "AzureWebJobsStorage",
        ],
    ):
        return False
    print("Function App configured for managed identity storage access.")
    return True


def create_azure_resources(names: dict[str, str]) -> bool:
    supported_locations = az_query(
        [
            "az",
            "functionapp",
            "list-flexconsumption-locations",
            "--query",
            "[].name",
            "-o",
            "tsv",
        ]
    ).splitlines()
    if location not in supported_locations:
        print(f"Error: Flex Consumption is not available in '{location}'.")
        print(
            "Run 'az functionapp list-flexconsumption-locations -o table', "
            "then change the location at the top of this script."
        )
        return False

    if not create_resource_group():
        return False

    storage_id = _ensure_storage_account(names["storage"])
    if not storage_id:
        return False

    identity_id, principal_id, client_id = _ensure_identity(names["identity"])
    if not identity_id or not principal_id or not client_id:
        return False
    if not _assign_storage_roles(principal_id, storage_id):
        return False
    if not _ensure_application_insights(names["insights"]):
        return False
    return _ensure_function_app(names, identity_id, client_id)


def _create_deployment_package(package_path: Path) -> None:
    project_files = [
        Path("function_app.py"),
        Path("host.json"),
        Path("requirements.txt"),
    ]
    with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as package:
        for project_file in project_files:
            if not project_file.is_file():
                raise FileNotFoundError(project_file)
            package.write(project_file, project_file.as_posix())


def deploy_function_app(names: dict[str, str]) -> bool:
    state = az_query(
        [
            "az",
            "functionapp",
            "show",
            "--name",
            names["function"],
            "--resource-group",
            rg,
            "--query",
            "state",
            "-o",
            "tsv",
        ]
    )
    if state == "Stopped":
        if not _start_function_app(names["function"]):
            return False
    elif state != "Running":
        print(f"Error: Function App '{names['function']}' is not ready.")
        print("Please run option 1 first, then try again.")
        return False

    print("Creating the deployment package...")
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            package_path = Path(temp_dir) / "durable-functions.zip"
            _create_deployment_package(package_path)
            if not run_quiet(
                "Deploy Function App",
                [
                    "az",
                    "functionapp",
                    "deployment",
                    "source",
                    "config-zip",
                    "--name",
                    names["function"],
                    "--resource-group",
                    rg,
                    "--src",
                    str(package_path),
                    "--build-remote",
                    "true",
                    "--timeout",
                    "600",
                ],
            ):
                return False
    except (FileNotFoundError, OSError, zipfile.BadZipFile) as exc:
        print(f"Error: Could not create the deployment package: {exc}")
        return False

    print(f"Function App deployed: {names['function']}")
    return True


def check_deployment_status(names: dict[str, str]) -> bool:
    print("Deployment Status")
    print("===========================================================")
    print(f"Resource group: {rg}")

    storage_state = az_query(
        [
            "az",
            "storage",
            "account",
            "show",
            "--name",
            names["storage"],
            "--resource-group",
            rg,
            "--query",
            "provisioningState",
            "-o",
            "tsv",
        ]
    )
    print(f"Storage account: {storage_state or 'Not created'}")

    function_state = az_query(
        [
            "az",
            "functionapp",
            "show",
            "--name",
            names["function"],
            "--resource-group",
            rg,
            "--query",
            "state",
            "-o",
            "tsv",
        ]
    )
    print(f"Function App: {function_state or 'Not created'}")

    host_name = az_query(
        [
            "az",
            "functionapp",
            "show",
            "--name",
            names["function"],
            "--resource-group",
            rg,
            "--query",
            "defaultHostName",
            "-o",
            "tsv",
        ]
    )
    if host_name:
        print(f"Workflow endpoint: https://{host_name}/api/workflows")

    function_key = az_query(
        [
            "az",
            "functionapp",
            "keys",
            "list",
            "--resource-group",
            rg,
            "--name",
            names["function"],
            "--query",
            "functionKeys.default",
            "-o",
            "tsv",
        ]
    )
    if not host_name or not function_key:
        print("Error: Could not retrieve the Function App endpoint and key.")
        return False

    write_env_files(
        {
            "FUNCTION_APP_URL": f"https://{host_name}",
            "FUNCTION_KEY": function_key,
        }
    )
    print("Environment files created: .env and .env.ps1")
    return bool(function_state)


def show_menu(names: dict[str, str]) -> None:
    clear_screen()
    print("=====================================================================")
    print("    Durable Functions Exercise - Deployment Script")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"Function App: {names['function']}")
    print("=====================================================================")
    print("1. Create Azure resources")
    print("2. Deploy the Function App")
    print("3. Check deployment status")
    print("4. Exit")
    print("=====================================================================")


def _preflight() -> None:
    script_dir = Path(__file__).resolve().parent
    if not (script_dir / "function_app.py").is_file():
        print(
            "Error: 'function_app.py' is missing next to azdeploy.py. "
            "Make sure you kept the exercise folder intact."
        )
        sys.exit(1)
    os.chdir(script_dir)


def main() -> None:
    _preflight()
    user_object_id = require_az_login()
    names = _derived_names(user_object_id)

    while True:
        show_menu(names)
        choice = input("Please select an option (1-4): ").strip()
        if choice in {"1", "2", "3", "4"}:
            clear_screen()

        if choice == "1":
            print()
            create_azure_resources(names)
            print()
            pause()
        elif choice == "2":
            print()
            deploy_function_app(names)
            print()
            pause()
        elif choice == "3":
            print()
            check_deployment_status(names)
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
