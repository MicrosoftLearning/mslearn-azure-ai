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

CONTAINER_APP_NAME = "ai-api"
CONTAINER_IMAGE = "ai-api:v1"
TARGET_PORT = "8000"
MODEL_NAME = "gpt-4o-mini"
EMBEDDINGS_API_KEY = "demo-key-12345"

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
    return f"acr{user_hash}", f"aca-env-{user_hash}"


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


def create_acr_and_build_image(acr_name: str) -> bool:
    if not create_resource_group():
        return False
    print()
    print(f"Creating Azure Container Registry '{acr_name}'...")

    existing = az_query(
        ["az", "acr", "show", "--resource-group", rg, "--name", acr_name,
         "--query", "name", "-o", "tsv"]
    )
    if existing:
        print(f"ACR already exists: {acr_name}")
    else:
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


def create_containerapps_environment(aca_env: str) -> bool:
    if not create_resource_group():
        return False
    print()
    print(f"Creating Container Apps environment '{aca_env}' (if needed)...")
    print("This may take a few minutes...")

    existing = az_query(
        ["az", "containerapp", "env", "show",
         "--name", aca_env, "--resource-group", rg,
         "--query", "name", "-o", "tsv"]
    )
    if existing:
        print(f"Container Apps environment already exists: {aca_env}")
    else:
        if not run_quiet(
            "Create Container Apps environment",
            [
                "az", "containerapp", "env", "create",
                "--name", aca_env,
                "--resource-group", rg,
                "--location", location,
            ],
        ):
            return False
        print(f"Container Apps environment created: {aca_env}")
    return True


def deploy_container_app_and_configure_secrets(acr_name: str, aca_env: str) -> bool:
    print(f"Deploying Container App '{CONTAINER_APP_NAME}' and configuring secrets...")
    print()

    acr_exists = az_query(
        ["az", "acr", "show", "--resource-group", rg, "--name", acr_name,
         "--query", "name", "-o", "tsv"]
    )
    if not acr_exists:
        print(f"Error: ACR '{acr_name}' not found. Run option 1 first.")
        return False

    env_exists = az_query(
        ["az", "containerapp", "env", "show",
         "--name", aca_env, "--resource-group", rg,
         "--query", "name", "-o", "tsv"]
    )
    if not env_exists:
        print(f"Error: Container Apps environment '{aca_env}' not found. Run option 2 first.")
        return False

    image_exists = az_query(
        ["az", "acr", "repository", "show",
         "--name", acr_name, "--image", CONTAINER_IMAGE,
         "--query", "name", "-o", "tsv"]
    )
    if not image_exists:
        print(f"Error: Container image '{CONTAINER_IMAGE}' not found in ACR. Run option 1 first.")
        return False

    app_exists = az_query(
        ["az", "containerapp", "show",
         "--name", CONTAINER_APP_NAME, "--resource-group", rg,
         "--query", "name", "-o", "tsv"]
    )
    if not app_exists:
        print(f"Creating Container App '{CONTAINER_APP_NAME}'...")
        if not run_quiet(
            "Create Container App",
            [
                "az", "containerapp", "create",
                "--name", CONTAINER_APP_NAME,
                "--resource-group", rg,
                "--environment", aca_env,
                "--image", f"{acr_name}.azurecr.io/{CONTAINER_IMAGE}",
                "--ingress", "external",
                "--target-port", TARGET_PORT,
                "--env-vars", f"MODEL_NAME={MODEL_NAME}",
                "--registry-server", f"{acr_name}.azurecr.io",
                "--registry-identity", "system",
            ],
        ):
            return False
        print(f"Container App created: {CONTAINER_APP_NAME}")
    else:
        print(f"Container App already exists: {CONTAINER_APP_NAME}")

    print("Setting Container App secret...")
    if not run_quiet(
        "Set Container App secret",
        [
            "az", "containerapp", "secret", "set",
            "--name", CONTAINER_APP_NAME,
            "--resource-group", rg,
            "--secrets", f"embeddings-api-key={EMBEDDINGS_API_KEY}",
        ],
    ):
        return False

    print("Configuring environment variable to reference secret...")
    if not run_quiet(
        "Update Container App environment variables",
        [
            "az", "containerapp", "update",
            "--name", CONTAINER_APP_NAME,
            "--resource-group", rg,
            "--set-env-vars", "EMBEDDINGS_API_KEY=secretref:embeddings-api-key",
        ],
    ):
        return False
    print("Container App updated with secret reference")

    write_env_files({
        "RESOURCE_GROUP": rg,
        "ACR_NAME": acr_name,
        "ACR_SERVER": f"{acr_name}.azurecr.io",
        "ACA_ENVIRONMENT": aca_env,
        "CONTAINER_APP_NAME": CONTAINER_APP_NAME,
        "CONTAINER_IMAGE": CONTAINER_IMAGE,
        "TARGET_PORT": TARGET_PORT,
        "MODEL_NAME": MODEL_NAME,
        "EMBEDDINGS_API_KEY": EMBEDDINGS_API_KEY,
        "LOCATION": location,
    })
    print()
    print("Environment variables saved to .env and .env.ps1")
    print("Run 'source .env' (Bash) or '. .\\.env.ps1' (PowerShell) to load them.")
    return True


def check_deployment_status(acr_name: str, aca_env: str) -> bool:
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
                ["az", "acr", "repository", "show",
                 "--name", acr_name, "--image", CONTAINER_IMAGE,
                 "--query", "name", "-o", "tsv"]
            )
            if image_exists:
                print(f"  Container image: {CONTAINER_IMAGE}")
            else:
                print("  Container image not found")
    else:
        print("  Status: Not created")

    print()
    print(f"Container Apps Environment ({aca_env}):")
    env_status = az_query(
        ["az", "containerapp", "env", "show",
         "--resource-group", rg, "--name", aca_env,
         "--query", "properties.provisioningState", "-o", "tsv"]
    )
    if env_status:
        print(f"  Status: {env_status}")
        if env_status == "Succeeded":
            print("  Container Apps environment is ready")
    else:
        print("  Status: Not created")

    print()
    print(f"Container App ({CONTAINER_APP_NAME}):")
    app_status = az_query(
        ["az", "containerapp", "show",
         "--resource-group", rg, "--name", CONTAINER_APP_NAME,
         "--query", "properties.provisioningState", "-o", "tsv"]
    )
    if app_status:
        print(f"  Status: {app_status}")
        if app_status == "Succeeded":
            print("  Container App is deployed")
    else:
        print("  Status: Not created")
    return True


def show_menu(acr_name: str, aca_env: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    Azure Container Apps Exercise - Deployment Script")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"Container Apps Environment: {aca_env}")
    print(f"ACR Name: {acr_name}")
    print("=====================================================================")
    print("1. Create Azure Container Registry and build container image")
    print("2. Create Container Apps environment")
    print("3. Deploy the container app and configure secrets")
    print("4. Check deployment status")
    print("5. Exit")
    print("=====================================================================")


def _preflight() -> None:
    script_dir = Path(__file__).resolve().parent
    if not (script_dir / "api" / "Dockerfile").is_file():
        print(
            "Error: 'api/Dockerfile' is missing next to azdeploy.py. "
            "Make sure you kept the exercise folder intact."
        )
        sys.exit(1)
    os.chdir(script_dir)


def main() -> None:
    _preflight()
    user_object_id = require_az_login()
    acr_name, aca_env = _derived_names(user_object_id)

    while True:
        show_menu(acr_name, aca_env)
        choice = input("Please select an option (1-5): ").strip()
        if choice in {"1", "2", "3", "4", "5"}:
            clear_screen()

        if choice == "1":
            print()
            create_acr_and_build_image(acr_name)
            print()
            pause()
        elif choice == "2":
            print()
            create_containerapps_environment(aca_env)
            print()
            pause()
        elif choice == "3":
            print()
            deploy_container_app_and_configure_secrets(acr_name, aca_env)
            print()
            pause()
        elif choice == "4":
            print()
            check_deployment_status(acr_name, aca_env)
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
