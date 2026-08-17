# =============================================================================
# Change the values of these variables as needed.
# =============================================================================

# rg = "<your-resource-group-name>"  # Resource Group name
# location = "<your-azure-region>"   # Azure region for the resources

rg = "rg-exercises"          # Resource Group name
location = "eastus"          # Azure region for the resources

# =============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# =============================================================================

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

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


def _derived_names(user_object_id: str) -> str:
    user_hash = hashlib.sha1(user_object_id.encode("utf-8")).hexdigest()[:8]
    return f"acr{user_hash}"


def print_banner(acr_name: str) -> None:
    print("=====================================================================")
    print("    Azure Container Registry Exercise - Deployment Script")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"ACR Name: {acr_name}")
    print("=====================================================================")
    print()


def create_resource_group() -> bool:
    print(f"Creating resource group '{rg}'...")
    exists = az_query(["az", "group", "exists", "--name", rg])
    if exists == "true":
        print(f"Resource group already exists: {rg}")
    else:
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
    return True


def create_acr(acr_name: str) -> bool:
    print(f"Creating Azure Container Registry '{acr_name}'...")
    if not run_quiet(
        "Create Azure Container Registry",
        [
            "az", "acr", "create",
            "--resource-group", rg,
            "--name", acr_name,
            "--sku", "Basic",
        ],
    ):
        return False
    print(f"ACR created: {acr_name}")
    print(f"  Login server: {acr_name}.azurecr.io")
    return True


def _preflight() -> None:
    """Anchor cwd to the script folder so env files land next to the script."""
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
    acr_name = _derived_names(user_object_id)

    print_banner(acr_name)

    if not create_resource_group():
        sys.exit(1)
    print()

    if not create_acr(acr_name):
        sys.exit(1)
    print()

    write_env_files({
        "RESOURCE_GROUP": rg,
        "ACR_NAME": acr_name,
        "LOCATION": location,
    })

    print("=====================================================================")
    print("  Deployment Complete!")
    print("=====================================================================")
    print()
    print("Environment variables have been saved to: .env and .env.ps1")
    print()
    print(f"  RESOURCE_GROUP={rg}")
    print(f"  ACR_NAME={acr_name}")
    print(f"  LOCATION={location}")
    print()
    print("=====================================================================")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
