# =============================================================================
# Change the values of these variables as needed.
# =============================================================================

# rg = "<your-resource-group-name>"  # Resource Group name
# location = "<your-azure-region>"   # Azure region for the resources

rg = "rg-exercises"          # Resource Group name
location = "canadacentral"         # Azure region for the resources

# =============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# =============================================================================

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

CONTAINER_IMAGE = "docprocessor:v1"

# Suppress Azure CLI preview / deprecation WARNINGs from every subprocess call.
os.environ.setdefault("AZURE_CORE_ONLY_SHOW_ERRORS", "true")

_EXE_CACHE: dict[str, str] = {}


def _resolve_exe(name: str) -> str:
    """Locate an executable on PATH (handles az.cmd on Windows)."""
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
    """Run a command, print an error on failure, return success as bool."""
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
    """Run an `az ... -o tsv` probe and return stripped stdout (or empty)."""
    argv = [_resolve_exe(argv[0]), *argv[1:]]
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def clear_screen() -> None:
    """Clear the terminal across bash, zsh, PowerShell, cmd, and Git Bash."""
    cmd = "cls" if os.name == "nt" else "clear"
    if os.system(cmd) != 0:
        sys.stdout.write("\x1b[2J\x1b[3J\x1b[H")
        sys.stdout.flush()


def pause(prompt: str = "Press Enter to continue...") -> None:
    try:
        input(prompt)
    except EOFError:
        print()


def require_az_login() -> str:
    """Return the signed-in user's object id, or exit if not logged in."""
    user_object_id = az_query(
        ["az", "ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"]
    )
    if not user_object_id:
        print("Error: Not authenticated with Azure. Please run: az login")
        sys.exit(1)
    return user_object_id


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


def _derived_names(user_object_id: str) -> tuple[str, str, str]:
    user_hash = hashlib.sha1(user_object_id.encode("utf-8")).hexdigest()[:8]
    return (
        f"acr{user_hash}",
        f"plan-docprocessor-{user_hash}",
        f"app-docprocessor-{user_hash}",
    )


def show_menu(acr_name: str, app_plan: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    App Service Container Exercise - Deployment Script")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"ACR Name: {acr_name}")
    print(f"App Service Plan: {app_plan}")
    print("=====================================================================")
    print("1. Create Azure Container Registry and build container image")
    print("2. Create App Service Plan")
    print("3. Check deployment status")
    print("4. Exit")
    print("=====================================================================")


def create_resource_group() -> bool:
    print(f"Checking/creating resource group '{rg}'...")
    exists = az_query(["az", "group", "exists", "--name", rg])
    if exists == "false":
        if not run_quiet(
            "Create resource group",
            [
                "az", "group", "create",
                "--name", rg,
                "--location", location,
            ],
        ):
            return False
        print(f"Resource group created: {rg}")
    else:
        print(f"Resource group already exists: {rg}")
    return True


def create_acr_and_build_image(acr_name: str) -> bool:
    print(f"Creating Azure Container Registry '{acr_name}'...")
    existing = az_query(
        ["az", "acr", "show", "--resource-group", rg, "--name", acr_name,
         "--query", "name", "-o", "tsv"]
    )
    if not existing:
        if not run_quiet(
            "Create Azure Container Registry",
            [
                "az", "acr", "create",
                "--resource-group", rg,
                "--name", acr_name,
                "--sku", "Basic",
                "--admin-enabled", "false",
            ],
        ):
            return False
        print(f"ACR created: {acr_name}")
    else:
        print(f"ACR already exists: {acr_name}")
    print(f"  Login server: {acr_name}.azurecr.io")

    print()
    print("Building and pushing container image to ACR...")
    print("This may take a few minutes...")

    if not run_quiet(
        "Build and push container image",
        [
            "az", "acr", "build",
            "--resource-group", rg,
            "--registry", acr_name,
            "--image", CONTAINER_IMAGE,
            "--file", "api/Dockerfile",
            "--no-logs",
            "api/",
        ],
    ):
        return False
    print(f"Image built and pushed: {acr_name}.azurecr.io/{CONTAINER_IMAGE}")
    return True


def create_app_service_plan(acr_name: str, app_plan: str, app_name: str) -> bool:
    print(f"Creating App Service Plan '{app_plan}'...")
    existing = az_query(
        ["az", "appservice", "plan", "show", "--resource-group", rg,
         "--name", app_plan, "--query", "name", "-o", "tsv"]
    )
    if not existing:
        if not run_quiet(
            "Create App Service Plan",
            [
                "az", "appservice", "plan", "create",
                "--resource-group", rg,
                "--name", app_plan,
                "--location", location,
                "--sku", "P0v3",
                "--is-linux",
            ],
        ):
            return False
        print(f"App Service Plan created: {app_plan}")
        print("  SKU: P0v3 (Premium v3 tier)")
    else:
        print(f"App Service Plan already exists: {app_plan}")

    write_env_files({
        "RESOURCE_GROUP": rg,
        "ACR_NAME": acr_name,
        "APP_PLAN": app_plan,
        "APP_NAME": app_name,
        "LOCATION": location,
    })
    print()
    print("Environment variables saved to: .env and .env.ps1")
    print("Run 'source .env' (Bash) or '. .\\.env.ps1' (PowerShell) to load them.")
    return True


def check_deployment_status(acr_name: str, app_plan: str, app_name: str) -> bool:
    print("Checking deployment status...")
    print()

    print(f"Azure Container Registry ({acr_name}):")
    acr_status = az_query(
        ["az", "acr", "show", "--resource-group", rg, "--name", acr_name,
         "--query", "provisioningState", "-o", "tsv"]
    )
    if acr_status:
        print(f"  Status: {acr_status}")
        if acr_status == "Succeeded":
            print("  ACR is ready")
            image_exists = az_query(
                ["az", "acr", "repository", "show", "--name", acr_name,
                 "--image", CONTAINER_IMAGE, "--query", "name", "-o", "tsv"]
            )
            if image_exists:
                print(f"  Container image: {CONTAINER_IMAGE}")
            else:
                print("  Container image not found")
    else:
        print("  Status: Not created")

    print()
    print(f"App Service Plan ({app_plan}):")
    plan_status = az_query(
        ["az", "appservice", "plan", "show", "--resource-group", rg,
         "--name", app_plan, "--query", "provisioningState", "-o", "tsv"]
    )
    if plan_status:
        print(f"  Status: {plan_status}")
        plan_sku = az_query(
            ["az", "appservice", "plan", "show", "--resource-group", rg,
             "--name", app_plan, "--query", "sku.name", "-o", "tsv"]
        )
        if plan_sku:
            print(f"  SKU: {plan_sku}")
        if plan_status == "Succeeded":
            print("  App Service Plan is ready")
    else:
        print("  Status: Not created")

    print()
    print(f"Web App ({app_name}):")
    app_state = az_query(
        ["az", "webapp", "show", "--resource-group", rg, "--name", app_name,
         "--query", "state", "-o", "tsv"]
    )
    if app_state:
        print(f"  State: {app_state}")
        print(f"  URL: https://{app_name}.azurewebsites.net")

        principal_id = az_query(
            ["az", "webapp", "identity", "show", "--resource-group", rg,
             "--name", app_name, "--query", "principalId", "-o", "tsv"]
        )
        if principal_id:
            print("  Managed identity configured")
        else:
            print("  Managed identity: Not configured")
    else:
        print("  Status: Not created (student task)")

    print()
    print("=====================================================================")
    print("Environment Variables (.env and .env.ps1 files):")
    print(f"  RESOURCE_GROUP={rg}")
    print(f"  ACR_NAME={acr_name}")
    print(f"  APP_PLAN={app_plan}")
    print(f"  APP_NAME={app_name}")
    print(f"  LOCATION={location}")
    print("=====================================================================")
    return True


def _preflight() -> None:
    """Anchor cwd to the script folder so `az acr build ... api/` always resolves."""
    script_dir = Path(__file__).resolve().parent
    dockerfile = script_dir / "api" / "Dockerfile"
    if not dockerfile.is_file():
        print("Error: 'api/Dockerfile' is missing next to azdeploy.py. "
              "Make sure you kept the exercise folder intact.")
        sys.exit(1)
    os.chdir(script_dir)


def main() -> None:
    _preflight()
    user_object_id = require_az_login()
    acr_name, app_plan, app_name = _derived_names(user_object_id)

    while True:
        show_menu(acr_name, app_plan)
        choice = input("Please select an option (1-4): ").strip()

        if choice in {"1", "2", "3", "4"}:
            clear_screen()

        if choice == "1":
            print()
            if create_resource_group():
                print()
                create_acr_and_build_image(acr_name)
            print()
            pause()
        elif choice == "2":
            print()
            if create_resource_group():
                print()
                create_app_service_plan(acr_name, app_plan, app_name)
            print()
            pause()
        elif choice == "3":
            print()
            check_deployment_status(acr_name, app_plan, app_name)
            print()
            pause()
        elif choice == "4":
            print("Exiting...")
            clear_screen()
            sys.exit(0)
        else:
            print("Invalid option. Please select 1-4.")
            pause()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
