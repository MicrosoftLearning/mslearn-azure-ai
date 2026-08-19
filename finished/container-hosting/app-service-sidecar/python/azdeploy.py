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
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

APP_SERVICE_SKU = "P1V3"
MAIN_IMAGE = "chat-api:v1"
SIDECAR_IMAGE = "model-server:v1"

os.environ.setdefault("AZURE_CORE_ONLY_SHOW_ERRORS", "true")

_EXE_CACHE: dict[str, str] = {}


def _resolve_exe(name: str) -> str:
    """Locate an executable on PATH, including Windows command wrappers."""
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
    """Run a command quietly and surface its output only when it fails."""
    command = [_resolve_exe(argv[0]), *argv[1:]]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"Error: {description} failed (exit code {result.returncode}).")
        combined = (result.stdout or "") + (result.stderr or "")
        if combined.strip():
            print(combined.rstrip())
        return False
    return True


def az_query(argv: list[str]) -> str:
    """Run an Azure CLI probe and return stripped output or an empty string."""
    command = [_resolve_exe(argv[0]), *argv[1:]]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def clear_screen() -> None:
    """Clear the terminal across supported operating systems and shells."""
    command = "cls" if os.name == "nt" else "clear"
    if os.system(command) != 0:
        sys.stdout.write("\x1b[2J\x1b[3J\x1b[H")
        sys.stdout.flush()


def pause(prompt: str = "Press Enter to continue...") -> None:
    try:
        input(prompt)
    except EOFError:
        print()


def require_az_login() -> str:
    """Return the signed-in user's object ID or exit when not authenticated."""
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


def write_sitecontainers_spec(acr_name: str) -> None:
    """Resolve the immutable template without deploying the containers."""
    template_path = Path("sitecontainers-spec.template.json")
    template = template_path.read_text(encoding="utf-8")
    resolved = template.replace("<registry-name>", acr_name)
    if "<registry-name>" in resolved:
        raise ValueError("Container specification placeholders were not fully resolved.")

    spec = json.loads(resolved)
    Path("sitecontainers-spec.json").write_text(
        json.dumps(spec, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _derived_names(user_object_id: str) -> tuple[str, str, str]:
    user_hash = hashlib.sha1(user_object_id.encode("utf-8")).hexdigest()[:8]
    return (
        f"acrsidecar{user_hash}",
        f"plan-ai-sidecar-{user_hash}",
        f"app-ai-sidecar-{user_hash}",
    )


def show_menu(acr_name: str, app_plan: str, app_name: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    App Service AI Sidecar Exercise - Deployment Script")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"ACR Name: {acr_name}")
    print(f"App Service Plan: {app_plan} ({APP_SERVICE_SKU})")
    print(f"Web App: {app_name}")
    print("=====================================================================")
    print("1. Create Azure Container Registry and build both images")
    print("2. Create App Service resources and configure system identity")
    print("3. Check deployment status")
    print("4. Exit")
    print("=====================================================================")


def create_resource_group() -> bool:
    print(f"Checking/creating resource group '{rg}'...")
    exists = az_query(["az", "group", "exists", "--name", rg])
    if exists == "true":
        print(f"Resource group already exists: {rg}")
        return True
    if not run_quiet(
        "Create resource group",
        ["az", "group", "create", "--name", rg, "--location", location],
    ):
        return False
    print(f"Resource group created: {rg}")
    return True


def _wait_until_absent(description: str, show_command: list[str]) -> bool:
    for _ in range(60):
        if not az_query(show_command):
            return True
        time.sleep(5)
    print(f"Error: Timed out waiting for {description} to be deleted.")
    return False


def _prepare_acr(acr_name: str) -> bool:
    state = az_query(
        [
            "az", "acr", "show",
            "--resource-group", rg,
            "--name", acr_name,
            "--query", "provisioningState",
            "-o", "tsv",
        ]
    )
    if state == "Succeeded":
        print(f"Azure Container Registry already exists: {acr_name}")
        return True
    if state in {"Failed", "Canceled"}:
        print(f"Removing Azure Container Registry in terminal state '{state}'...")
        if not run_quiet(
            "Delete failed Azure Container Registry",
            ["az", "acr", "delete", "--resource-group", rg, "--name", acr_name, "--yes"],
        ):
            return False
        if not _wait_until_absent(
            "Azure Container Registry",
            [
                "az", "acr", "show",
                "--resource-group", rg,
                "--name", acr_name,
                "--query", "name",
                "-o", "tsv",
            ],
        ):
            return False
    elif state:
        print(f"Azure Container Registry is still provisioning (status: {state}).")
        return False

    print(f"Creating Azure Container Registry '{acr_name}'...")
    if not run_quiet(
        "Create Azure Container Registry",
        [
            "az", "acr", "create",
            "--resource-group", rg,
            "--name", acr_name,
            "--location", location,
            "--sku", "Basic",
            "--admin-enabled", "false",
        ],
    ):
        return False
    print(f"Azure Container Registry created: {acr_name}")
    return True


def create_acr_and_build_images(acr_name: str) -> bool:
    if not _prepare_acr(acr_name):
        return False

    print()
    print(f"Building and pushing {MAIN_IMAGE}...")
    if not run_quiet(
        "Build and push the chat API image",
        [
            "az", "acr", "build",
            "--resource-group", rg,
            "--registry", acr_name,
            "--image", MAIN_IMAGE,
            "--file", "api/Dockerfile",
            "--no-logs",
            "api/",
        ],
    ):
        return False
    print(f"Image built and pushed: {acr_name}.azurecr.io/{MAIN_IMAGE}")

    print()
    print(f"Building and pushing {SIDECAR_IMAGE}...")
    print("The first build downloads the 2.7 GB Phi-3 CPU INT4 model.")
    print("This build can take 5-10 minutes. Keep this terminal open.")
    build_started = time.monotonic()
    build_succeeded = run_quiet(
        "Build and push the Phi-3 model server image",
        [
            "az", "acr", "build",
            "--resource-group", rg,
            "--registry", acr_name,
            "--image", SIDECAR_IMAGE,
            "--file", "model-server/Dockerfile",
            "--no-logs",
            "model-server/",
        ],
    )
    elapsed_seconds = round(time.monotonic() - build_started)
    elapsed_minutes, remaining_seconds = divmod(elapsed_seconds, 60)
    print(
        "Phi-3 model server build duration: "
        f"{elapsed_minutes}m {remaining_seconds:02d}s"
    )
    if not build_succeeded:
        return False
    print(f"Image built and pushed: {acr_name}.azurecr.io/{SIDECAR_IMAGE}")
    return True


def _prepare_app_service_plan(app_plan: str) -> bool:
    existing = az_query(
        [
            "az", "appservice", "plan", "show",
            "--resource-group", rg,
            "--name", app_plan,
            "--query", "name",
            "-o", "tsv",
        ]
    )
    if existing:
        state = az_query(
            [
                "az", "appservice", "plan", "show",
                "--resource-group", rg,
                "--name", app_plan,
                "--query", "provisioningState",
                "-o", "tsv",
            ]
        )
        if not state:
            state = az_query(
                [
                    "az", "appservice", "plan", "show",
                    "--resource-group", rg,
                    "--name", app_plan,
                    "--query", "status",
                    "-o", "tsv",
                ]
            )
        if state in {"Failed", "Canceled"}:
            print(f"Removing App Service plan in terminal state '{state}'...")
            if not run_quiet(
                "Delete failed App Service plan",
                [
                    "az", "appservice", "plan", "delete",
                    "--resource-group", rg,
                    "--name", app_plan,
                    "--yes",
                ],
            ):
                return False
            if not _wait_until_absent(
                "App Service plan",
                [
                    "az", "appservice", "plan", "show",
                    "--resource-group", rg,
                    "--name", app_plan,
                    "--query", "name",
                    "-o", "tsv",
                ],
            ):
                return False
        elif state and state not in {"Succeeded", "Ready"}:
            print(f"App Service plan is still provisioning (status: {state}).")
            return False
        else:
            print(f"App Service plan already exists: {app_plan}")
            return True

    print(f"Creating App Service plan '{app_plan}'...")
    if not run_quiet(
        "Create App Service plan",
        [
            "az", "appservice", "plan", "create",
            "--resource-group", rg,
            "--name", app_plan,
            "--location", location,
            "--sku", APP_SERVICE_SKU,
            "--is-linux",
        ],
    ):
        print(
            f"Try a different region if the {APP_SERVICE_SKU} SKU is unavailable, "
            "then run this option again."
        )
        return False
    print(f"App Service plan created: {app_plan}")
    print(f"  SKU: {APP_SERVICE_SKU} (2 vCPU, 8 GB memory)")
    return True


def _prepare_web_app(app_plan: str, app_name: str) -> bool:
    state = az_query(
        [
            "az", "webapp", "show",
            "--resource-group", rg,
            "--name", app_name,
            "--query", "provisioningState",
            "-o", "tsv",
        ]
    )
    if state == "Succeeded":
        print(f"Sidecar-enabled web app already exists: {app_name}")
        return True
    if state in {"Failed", "Canceled"}:
        print(f"Removing web app in terminal state '{state}'...")
        if not run_quiet(
            "Delete failed web app",
            [
                "az", "webapp", "delete",
                "--resource-group", rg,
                "--name", app_name,
            ],
        ):
            return False
        if not _wait_until_absent(
            "web app",
            [
                "az", "webapp", "show",
                "--resource-group", rg,
                "--name", app_name,
                "--query", "name",
                "-o", "tsv",
            ],
        ):
            return False
    elif state:
        print(f"Web app is still provisioning (status: {state}).")
        return False

    print(f"Creating sidecar-enabled web app '{app_name}'...")
    if not run_quiet(
        "Create sidecar-enabled web app",
        [
            "az", "webapp", "create",
            "--resource-group", rg,
            "--name", app_name,
            "--plan", app_plan,
            "--sitecontainers-app",
        ],
    ):
        return False
    print(f"Sidecar-enabled web app created: {app_name}")
    return True


def create_app_service_resources(
    acr_name: str,
    app_plan: str,
    app_name: str,
) -> bool:
    if not _prepare_app_service_plan(app_plan):
        return False
    print()
    if not _prepare_web_app(app_plan, app_name):
        return False
    if not run_quiet(
        "Configure the extended container startup time",
        [
            "az", "webapp", "config", "appsettings", "set",
            "--resource-group", rg,
            "--name", app_name,
            "--settings",
            "WEBSITES_CONTAINER_START_TIME_LIMIT=1800",
            "MODEL_ENDPOINT=http://localhost:11434",
            "MODEL_NAME=microsoft/Phi-3-mini-4k-instruct-onnx",
        ],
    ):
        return False
    print()
    if not configure_system_identity(acr_name, app_name):
        return False
    write_sitecontainers_spec(acr_name)
    print("Resolved container specification saved to: sitecontainers-spec.json")
    write_env_files(
        {
            "RESOURCE_GROUP": rg,
            "LOCATION": location,
            "ACR_NAME": acr_name,
            "APP_PLAN": app_plan,
            "APP_NAME": app_name,
            "MAIN_IMAGE": f"{acr_name}.azurecr.io/{MAIN_IMAGE}",
            "SIDECAR_IMAGE": f"{acr_name}.azurecr.io/{SIDECAR_IMAGE}",
            "CHAT_API_URL": f"https://{app_name}.azurewebsites.net",
            "CHAT_API_TIMEOUT": "300",
        }
    )
    print("Environment variables saved to: .env and .env.ps1")
    return True


def _assign_acr_pull(acr_name: str, principal_id: str) -> bool:
    acr_id = az_query(
        [
            "az", "acr", "show",
            "--resource-group", rg,
            "--name", acr_name,
            "--query", "id",
            "-o", "tsv",
        ]
    )
    if not acr_id:
        print("Error: Azure Container Registry was not found. Complete option 1 first.")
        return False

    assignment = az_query(
        [
            "az", "role", "assignment", "list",
            "--assignee", principal_id,
            "--scope", acr_id,
            "--query", "[?roleDefinitionName=='AcrPull'].id | [0]",
            "-o", "tsv",
        ]
    )
    if assignment:
        print("AcrPull role assignment already exists.")
        return True

    print("Assigning the AcrPull role to the managed identity...")
    if not run_quiet(
        "Assign AcrPull role",
        [
            "az", "role", "assignment", "create",
            "--assignee-object-id", principal_id,
            "--assignee-principal-type", "ServicePrincipal",
            "--role", "AcrPull",
            "--scope", acr_id,
        ],
    ):
        return False
    print("AcrPull role assigned.")
    return True


def configure_system_identity(acr_name: str, app_name: str) -> bool:
    if not az_query(
        [
            "az", "webapp", "show",
            "--resource-group", rg,
            "--name", app_name,
            "--query", "name",
            "-o", "tsv",
        ]
    ):
        print("Error: The web app was not found. Complete option 2 first.")
        return False

    principal_id = az_query(
        [
            "az", "webapp", "identity", "show",
            "--resource-group", rg,
            "--name", app_name,
            "--query", "principalId",
            "-o", "tsv",
        ]
    )
    if not principal_id:
        print("Enabling the system-assigned managed identity...")
        if not run_quiet(
            "Enable system-assigned managed identity",
            [
                "az", "webapp", "identity", "assign",
                "--resource-group", rg,
                "--name", app_name,
            ],
        ):
            return False
        principal_id = az_query(
            [
                "az", "webapp", "identity", "show",
                "--resource-group", rg,
                "--name", app_name,
                "--query", "principalId",
                "-o", "tsv",
            ]
        )
        if not principal_id:
            print("Error: Could not retrieve the system-assigned identity principal ID.")
            return False
        print("System-assigned managed identity enabled.")
    else:
        print("System-assigned managed identity is already enabled.")

    if not _assign_acr_pull(acr_name, principal_id):
        return False

    return True


def check_deployment_status(
    acr_name: str,
    app_plan: str,
    app_name: str,
) -> bool:
    print("Checking deployment status...")
    print()

    acr_status = az_query(
        [
            "az", "acr", "show",
            "--resource-group", rg,
            "--name", acr_name,
            "--query", "provisioningState",
            "-o", "tsv",
        ]
    )
    print(f"Azure Container Registry ({acr_name}):")
    print(f"  Status: {acr_status or 'Not created'}")
    if acr_status:
        repositories = az_query(
            ["az", "acr", "repository", "list", "--name", acr_name, "-o", "tsv"]
        )
        for image in (MAIN_IMAGE.split(":")[0], SIDECAR_IMAGE.split(":")[0]):
            state = "Available" if image in repositories.splitlines() else "Not found"
            print(f"  {image}: {state}")

    print()
    plan_name = az_query(
        [
            "az", "appservice", "plan", "show",
            "--resource-group", rg,
            "--name", app_plan,
            "--query", "name",
            "-o", "tsv",
        ]
    )
    print(f"App Service Plan ({app_plan}):")
    if not plan_name:
        print("  Status: Not created")
    else:
        plan_status = az_query(
            [
                "az", "appservice", "plan", "show",
                "--resource-group", rg,
                "--name", app_plan,
                "--query", "provisioningState",
                "-o", "tsv",
            ]
        )
        if not plan_status:
            plan_status = az_query(
                [
                    "az", "appservice", "plan", "show",
                    "--resource-group", rg,
                    "--name", app_plan,
                    "--query", "status",
                    "-o", "tsv",
                ]
            )
        print(f"  Status: {plan_status or 'Exists'}")
        plan_sku = az_query(
            [
                "az", "appservice", "plan", "show",
                "--resource-group", rg,
                "--name", app_plan,
                "--query", "sku.name",
                "-o", "tsv",
            ]
        )
        print(f"  SKU: {plan_sku or APP_SERVICE_SKU}")

    print()
    app_state = az_query(
        [
            "az", "webapp", "show",
            "--resource-group", rg,
            "--name", app_name,
            "--query", "state",
            "-o", "tsv",
        ]
    )
    print(f"Web App ({app_name}):")
    print(f"  State: {app_state or 'Not created'}")
    if app_state:
        print(f"  URL: https://{app_name}.azurewebsites.net")

    print()
    principal_id = az_query(
        [
            "az", "webapp", "identity", "show",
            "--resource-group", rg,
            "--name", app_name,
            "--query", "principalId",
            "-o", "tsv",
        ]
    )
    print("System-assigned Managed Identity:")
    print(f"  Status: {'Configured' if principal_id else 'Not configured'}")
    if principal_id:
        print(f"  Principal ID: {principal_id}")
    return True


def _preflight() -> None:
    script_dir = Path(__file__).resolve().parent
    anchors = [
        script_dir / "api" / "Dockerfile",
        script_dir / "model-server" / "Dockerfile",
        script_dir / "client" / "app.py",
        script_dir / "sitecontainers-spec.template.json",
    ]
    if not all(anchor.is_file() for anchor in anchors):
        print(
            "Error: The API, model-server, or client files are missing next to "
            "azdeploy.py. Make sure you kept the exercise folder intact."
        )
        sys.exit(1)
    os.chdir(script_dir)


def main() -> None:
    _preflight()
    user_object_id = require_az_login()
    acr_name, app_plan, app_name = _derived_names(user_object_id)

    while True:
        show_menu(acr_name, app_plan, app_name)
        choice = input("Please select an option (1-4): ").strip()

        if choice in {"1", "2", "3", "4"}:
            clear_screen()

        if choice == "1":
            print()
            if create_resource_group():
                print()
                create_acr_and_build_images(acr_name)
            print()
            pause()
        elif choice == "2":
            print()
            if create_resource_group():
                print()
                create_app_service_resources(
                    acr_name,
                    app_plan,
                    app_name,
                )
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
