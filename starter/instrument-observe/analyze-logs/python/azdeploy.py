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

OTEL_SERVICE_NAME = "document-pipeline-app"

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
    return f"appi-exercise-{user_hash}"


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


def create_application_insights(appinsights_name: str) -> bool:
    if not create_resource_group():
        return False
    print()
    print(f"Creating Application Insights '{appinsights_name}'...")

    existing = az_query(
        ["az", "monitor", "app-insights", "component", "show",
         "--resource-group", rg, "--app", appinsights_name,
         "--query", "name", "-o", "tsv"]
    )
    if existing:
        print(f"Application Insights already exists: {appinsights_name}")
    else:
        if not run_quiet(
            "Create Application Insights",
            [
                "az", "monitor", "app-insights", "component", "create",
                "--resource-group", rg,
                "--app", appinsights_name,
                "--location", location,
            ],
        ):
            return False
        print(f"Application Insights created: {appinsights_name}")

    print()
    print("Use option 2 to assign the role.")
    return True


def assign_role(appinsights_name: str, user_object_id: str) -> bool:
    print("Assigning Monitoring Metrics Publisher role...")

    existing = az_query(
        ["az", "monitor", "app-insights", "component", "show",
         "--resource-group", rg, "--app", appinsights_name,
         "--query", "name", "-o", "tsv"]
    )
    if not existing:
        print(f"Error: Application Insights '{appinsights_name}' not found.")
        print("Please run option 1 to create the resource, then try again.")
        return False

    user_upn = az_query(
        ["az", "ad", "signed-in-user", "show",
         "--query", "userPrincipalName", "-o", "tsv"]
    )
    if not user_upn:
        print("Error: Unable to retrieve signed-in user information.")
        print("Please ensure you are logged in with 'az login'.")
        return False

    appi_id = az_query(
        ["az", "monitor", "app-insights", "component", "show",
         "--resource-group", rg, "--app", appinsights_name,
         "--query", "id", "-o", "tsv"]
    )
    if not appi_id:
        print("Error: Unable to retrieve Application Insights resource ID.")
        return False

    role_exists = az_query(
        ["az", "role", "assignment", "list",
         "--assignee", user_object_id,
         "--scope", appi_id,
         "--role", "Monitoring Metrics Publisher",
         "--query", "[0].id", "-o", "tsv"]
    )
    if role_exists:
        print("Monitoring Metrics Publisher role already assigned")
    else:
        if not run_quiet(
            "Assign Monitoring Metrics Publisher role",
            [
                "az", "role", "assignment", "create",
                "--role", "Monitoring Metrics Publisher",
                "--assignee", user_object_id,
                "--scope", appi_id,
            ],
        ):
            return False
        print("Monitoring Metrics Publisher role assigned")

    print()
    print(f"Role configured for: {user_upn}")
    print("  - Monitoring Metrics Publisher: publish telemetry using Entra authentication")
    return True


def check_deployment_status(appinsights_name: str, user_object_id: str) -> bool:
    print("Checking deployment status...")
    print()

    print(f"Application Insights ({appinsights_name}):")
    appi_status = az_query(
        ["az", "monitor", "app-insights", "component", "show",
         "--resource-group", rg, "--app", appinsights_name,
         "--query", "provisioningState", "-o", "tsv"]
    )
    if not appi_status:
        print("  Status: Not created")
    else:
        print(f"  Status: {appi_status}")
        if appi_status == "Succeeded":
            print("  Application Insights is ready")
            conn = az_query(
                ["az", "monitor", "app-insights", "component", "show",
                 "--resource-group", rg, "--app", appinsights_name,
                 "--query", "connectionString", "-o", "tsv"]
            )
            if conn:
                print(f"  Connection string: {conn[:60]}...")
        else:
            print("  WARNING: Application Insights is still provisioning. Please wait and try again.")

    print()
    print("Role Assignment:")
    user_upn = az_query(
        ["az", "ad", "signed-in-user", "show",
         "--query", "userPrincipalName", "-o", "tsv"]
    )
    appi_id = az_query(
        ["az", "monitor", "app-insights", "component", "show",
         "--resource-group", rg, "--app", appinsights_name,
         "--query", "id", "-o", "tsv"]
    )
    if appi_id:
        role_exists = az_query(
            ["az", "role", "assignment", "list",
             "--assignee", user_object_id,
             "--scope", appi_id,
             "--role", "Monitoring Metrics Publisher",
             "--query", "[0].id", "-o", "tsv"]
        )
        if role_exists:
            print(f"  Role assigned: {user_upn} (Monitoring Metrics Publisher)")
        else:
            print("  WARNING: Role not assigned")
    else:
        print("  WARNING: Application Insights not created yet")
    return True


def retrieve_connection_info(appinsights_name: str, user_object_id: str) -> bool:
    print("Retrieving connection information...")

    existing = az_query(
        ["az", "monitor", "app-insights", "component", "show",
         "--resource-group", rg, "--app", appinsights_name,
         "--query", "name", "-o", "tsv"]
    )
    if not existing:
        print(f"Error: Application Insights '{appinsights_name}' not found.")
        print("Please run option 1 to create the resource, then try again.")
        return False

    appi_id = az_query(
        ["az", "monitor", "app-insights", "component", "show",
         "--resource-group", rg, "--app", appinsights_name,
         "--query", "id", "-o", "tsv"]
    )
    role_exists = az_query(
        ["az", "role", "assignment", "list",
         "--assignee", user_object_id,
         "--scope", appi_id,
         "--role", "Monitoring Metrics Publisher",
         "--query", "[0].id", "-o", "tsv"]
    )
    if not role_exists:
        print("Error: Monitoring Metrics Publisher role not assigned.")
        print("Please run option 2 to assign the role, then try again.")
        return False

    conn = az_query(
        ["az", "monitor", "app-insights", "component", "show",
         "--resource-group", rg, "--app", appinsights_name,
         "--query", "connectionString", "-o", "tsv"]
    )
    if not conn:
        print("Error: Unable to retrieve the Application Insights connection string.")
        return False

    alert_email = az_query(["az", "account", "show", "--query", "user.name", "-o", "tsv"])

    write_env_files({
        "APPLICATIONINSIGHTS_CONNECTION_STRING": conn,
        "OTEL_SERVICE_NAME": OTEL_SERVICE_NAME,
        "RESOURCE_GROUP": rg,
        "APPINSIGHTS_NAME": appinsights_name,
        "APPINSIGHTS_RESOURCE_ID": appi_id,
        "ALERT_EMAIL": alert_email,
    })
    print()
    print("Application Insights Connection Information")
    print("===========================================================")
    print(f"Connection string: {conn[:60]}...")
    print("Authentication: Microsoft Entra ID (DefaultAzureCredential)")
    print()
    print("Environment variables saved to .env and .env.ps1")
    return True


def show_menu(appinsights_name: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    Analyze Logs Exercise - Deployment Script")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"App Insights: {appinsights_name}")
    print("=====================================================================")
    print("1. Create Application Insights")
    print("2. Assign role")
    print("3. Check deployment status")
    print("4. Retrieve connection info")
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
    appinsights_name = _derived_names(user_object_id)

    while True:
        show_menu(appinsights_name)
        choice = input("Please select an option (1-5): ").strip()
        if choice in {"1", "2", "3", "4", "5"}:
            clear_screen()

        if choice == "1":
            print()
            create_application_insights(appinsights_name)
            print()
            pause()
        elif choice == "2":
            print()
            assign_role(appinsights_name, user_object_id)
            print()
            pause()
        elif choice == "3":
            print()
            check_deployment_status(appinsights_name, user_object_id)
            print()
            pause()
        elif choice == "4":
            print()
            retrieve_connection_info(appinsights_name, user_object_id)
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
