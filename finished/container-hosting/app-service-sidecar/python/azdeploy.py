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

APP_SERVICE_SKU = "P2mv3"
CHAT_API_IMAGE = "chat-api:v1"
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


def write_sitecontainers_spec(acr_name: str, identity_client_id: str) -> None:
    """Resolve the immutable template without deploying the containers."""
    template_path = Path("sitecontainers-spec.template.json")
    template = template_path.read_text(encoding="utf-8")
    resolved = template.replace("<registry-name>", acr_name)
    resolved = resolved.replace("<managed-identity-client-id>", identity_client_id)
    if "<registry-name>" in resolved or "<managed-identity-client-id>" in resolved:
        raise ValueError("Container specification placeholders were not fully resolved.")

    spec = json.loads(resolved)
    Path("sitecontainers-spec.json").write_text(
        json.dumps(spec, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _derived_names(user_object_id: str) -> tuple[str, str, str, str]:
    user_hash = hashlib.sha1(user_object_id.encode("utf-8")).hexdigest()[:8]
    return (
        f"acrsidecar{user_hash}",
        f"plan-ai-sidecar-{user_hash}",
        f"app-ai-sidecar-{user_hash}",
        f"id-sidecar-{user_hash}",
    )


def show_menu(acr_name: str, app_plan: str, app_name: str, identity_name: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    App Service AI Sidecar Exercise - Deployment Script")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"ACR Name: {acr_name}")
    print(f"Managed Identity: {identity_name}")
    print(f"App Service Plan: {app_plan} ({APP_SERVICE_SKU})")
    print(f"Web App: {app_name}")
    print("=====================================================================")
    print("1. Create container registry, managed identity, and build images")
    print("2. Create App Service resources and attach the managed identity")
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


def _verify_acr_arm_authentication(acr_name: str) -> bool:
    status = az_query(
        [
            "az", "acr", "config", "authentication-as-arm", "show",
            "--registry", acr_name,
            "--resource-group", rg,
            "--query", "status",
            "-o", "tsv",
        ]
    )
    if not status:
        print(
            "Error: Could not verify the registry's authentication-as-arm policy. "
            "Update Azure CLI and run this option again."
        )
        return False
    if status.lower() != "enabled":
        print(
            "Error: The registry's authentication-as-arm policy must be enabled "
            "for App Service managed-identity image pulls."
        )
        print(
            "Run: az acr config authentication-as-arm update "
            f"--registry {acr_name} --resource-group {rg} --status enabled"
        )
        return False
    print("ACR authentication-as-arm policy is enabled.")
    return True


def create_acr_and_build_images(acr_name: str, identity_name: str) -> bool:
    if not _prepare_acr(acr_name):
        return False
    if not _verify_acr_arm_authentication(acr_name):
        return False

    print()
    identity = _prepare_identity(identity_name)
    if identity is None:
        return False
    _, principal_id, _ = identity
    print()
    if not _assign_acr_pull(acr_name, principal_id):
        return False

    print()
    print(f"Building and pushing {CHAT_API_IMAGE}...")
    if not run_quiet(
        "Build and push the chat API image",
        [
            "az", "acr", "build",
            "--resource-group", rg,
            "--registry", acr_name,
            "--image", CHAT_API_IMAGE,
            "--file", "api/Dockerfile",
            "--no-logs",
            "api/",
        ],
    ):
        return False
    print(f"Image built and pushed: {acr_name}.azurecr.io/{CHAT_API_IMAGE}")

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
    print(f"  SKU: {APP_SERVICE_SKU}")
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
    identity_name: str,
) -> bool:
    identity = _prepare_identity(identity_name)
    if identity is None:
        print(
            "Error: The user-assigned managed identity was not found. "
            "Run option 1 first."
        )
        return False
    identity_resource_id, _, identity_client_id = identity

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
            "WEBSITE_WARMUP_PATH=/health/ready",
            "WEBSITE_WARMUP_STATUSES=200",
            "MODEL_ENDPOINT=http://localhost:11434",
            "MODEL_NAME=microsoft/Phi-3-mini-4k-instruct-onnx",
        ],
    ):
        return False
    print()
    if not _attach_identity_to_webapp(app_name, identity_resource_id):
        return False
    write_sitecontainers_spec(acr_name, identity_client_id)
    print("Resolved container specification saved to: sitecontainers-spec.json")
    write_env_files(
        {
            "RESOURCE_GROUP": rg,
            "LOCATION": location,
            "ACR_NAME": acr_name,
            "APP_PLAN": app_plan,
            "APP_NAME": app_name,
            "IDENTITY_NAME": identity_name,
            "CHAT_API_IMAGE": f"{acr_name}.azurecr.io/{CHAT_API_IMAGE}",
            "SIDECAR_IMAGE": f"{acr_name}.azurecr.io/{SIDECAR_IMAGE}",
            "CHAT_API_URL": f"https://{app_name}.azurewebsites.net",
            "CHAT_API_TIMEOUT": "300",
        }
    )
    print("Environment variables saved to: .env and .env.ps1")
    return True


def _prepare_identity(identity_name: str) -> tuple[str, str, str] | None:
    """Create or verify the user-assigned managed identity.

    Returns (resource_id, principal_id, client_id) on success.
    """
    existing = az_query(
        [
            "az", "identity", "show",
            "--resource-group", rg,
            "--name", identity_name,
            "--query", "id",
            "-o", "tsv",
        ]
    )
    if not existing:
        print(f"Creating user-assigned managed identity '{identity_name}'...")
        if not run_quiet(
            "Create user-assigned managed identity",
            [
                "az", "identity", "create",
                "--resource-group", rg,
                "--name", identity_name,
                "--location", location,
            ],
        ):
            return None
        print(f"User-assigned managed identity created: {identity_name}")
    else:
        print(f"User-assigned managed identity already exists: {identity_name}")

    resource_id = az_query(
        [
            "az", "identity", "show",
            "--resource-group", rg,
            "--name", identity_name,
            "--query", "id",
            "-o", "tsv",
        ]
    )
    principal_id = az_query(
        [
            "az", "identity", "show",
            "--resource-group", rg,
            "--name", identity_name,
            "--query", "principalId",
            "-o", "tsv",
        ]
    )
    client_id = az_query(
        [
            "az", "identity", "show",
            "--resource-group", rg,
            "--name", identity_name,
            "--query", "clientId",
            "-o", "tsv",
        ]
    )
    if not (resource_id and principal_id and client_id):
        print("Error: Could not retrieve managed identity properties.")
        return None
    return (resource_id, principal_id, client_id)


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
            "--query",
            f"[?roleDefinitionName=='AcrPull' && principalId=='{principal_id}'].id | [0]",
            "-o", "tsv",
        ]
    )
    if assignment:
        print("AcrPull role assignment already exists for the managed identity.")
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


def _attach_identity_to_webapp(app_name: str, identity_resource_id: str) -> bool:
    attached = az_query(
        [
            "az", "webapp", "identity", "show",
            "--resource-group", rg,
            "--name", app_name,
            "--query", "userAssignedIdentities",
            "-o", "json",
        ]
    )
    if attached and identity_resource_id in attached:
        print("User-assigned managed identity is already attached to the web app.")
        return True

    print("Attaching the user-assigned managed identity to the web app...")
    if not run_quiet(
        "Attach user-assigned managed identity",
        [
            "az", "webapp", "identity", "assign",
            "--resource-group", rg,
            "--name", app_name,
            "--identities", identity_resource_id,
        ],
    ):
        return False
    print("User-assigned managed identity attached.")
    return True


def check_deployment_status(
    acr_name: str,
    app_plan: str,
    app_name: str,
    identity_name: str,
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
        for image in (CHAT_API_IMAGE.split(":")[0], SIDECAR_IMAGE.split(":")[0]):
            state = "Available" if image in repositories.splitlines() else "Not found"
            print(f"  {image}: {state}")

    print()
    identity_client_id = az_query(
        [
            "az", "identity", "show",
            "--resource-group", rg,
            "--name", identity_name,
            "--query", "clientId",
            "-o", "tsv",
        ]
    )
    print(f"User-Assigned Managed Identity ({identity_name}):")
    if not identity_client_id:
        print("  Status: Not created")
    else:
        print("  Status: Created")
        print(f"  Client ID: {identity_client_id}")
        identity_principal_id = az_query(
            [
                "az", "identity", "show",
                "--resource-group", rg,
                "--name", identity_name,
                "--query", "principalId",
                "-o", "tsv",
            ]
        )
        acr_id = az_query(
            [
                "az", "acr", "show",
                "--resource-group", rg,
                "--name", acr_name,
                "--query", "id",
                "-o", "tsv",
            ]
        )
        if identity_principal_id and acr_id:
            role = az_query(
                [
                    "az", "role", "assignment", "list",
                    "--assignee", identity_principal_id,
                    "--scope", acr_id,
                    "--query",
                    f"[?roleDefinitionName=='AcrPull' && principalId=='{identity_principal_id}'].id | [0]",
                    "-o", "tsv",
                ]
            )
            print(f"  AcrPull on registry: {'Assigned' if role else 'Not assigned'}")

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
        attached = az_query(
            [
                "az", "webapp", "identity", "show",
                "--resource-group", rg,
                "--name", app_name,
                "--query", "userAssignedIdentities",
                "-o", "json",
            ]
        )
        identity_resource_id = az_query(
            [
                "az", "identity", "show",
                "--resource-group", rg,
                "--name", identity_name,
                "--query", "id",
                "-o", "tsv",
            ]
        )
        is_attached = (
            bool(identity_resource_id)
            and bool(attached)
            and identity_resource_id in attached
        )
        print(f"  Managed identity attached: {'Yes' if is_attached else 'No'}")
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
    acr_name, app_plan, app_name, identity_name = _derived_names(user_object_id)

    while True:
        show_menu(acr_name, app_plan, app_name, identity_name)
        choice = input("Please select an option (1-4): ").strip()

        if choice in {"1", "2", "3", "4"}:
            clear_screen()

        if choice == "1":
            print()
            if create_resource_group():
                print()
                create_acr_and_build_images(acr_name, identity_name)
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
                    identity_name,
                )
            print()
            pause()
        elif choice == "3":
            print()
            check_deployment_status(acr_name, app_plan, app_name, identity_name)
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
