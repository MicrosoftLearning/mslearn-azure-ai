# =============================================================================
# Change the values of these variables as needed.
# =============================================================================

# rg = "<your-resource-group-name>"  # Resource Group name
# location = "<your-azure-region>"   # Azure region for the resources

rg = "rg-exercises"          # Resource Group name
location = "eastus2"         # Azure region for the resources

# If the Standard_D2s_v7 SKU is not available in your region, try using Standard_D2s_v5, or Standard_D2s_v6 instead.
# AKS_VM_SIZE = "Standard_D2s_v7" # Keeping for production
AKS_VM_SIZE = "Standard_D2s_v6"

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

API_IMAGE_NAME = "aks-api"
FOUNDRY_MODEL_NAME = "gpt-5-mini"
FOUNDRY_MODEL_VERSION = "2025-08-07"

# Suppress Azure CLI preview / deprecation WARNINGs from every subprocess call.
os.environ.setdefault("AZURE_CORE_ONLY_SHOW_ERRORS", "true")

_EXE_CACHE: dict[str, str] = {}


def _resolve_exe(name: str) -> str:
    """Locate an executable on PATH (handles az.cmd / kubectl.exe on Windows)."""
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
        f"foundry-resource-{user_hash}",
        f"acr{user_hash}",
        f"aks-{user_hash}",
    )


def show_menu(foundry_resource: str, acr_name: str, aks_cluster: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    AKS Deployment with Foundry Model Integration")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"Foundry Resource: {foundry_resource}")
    print(f"ACR Name: {acr_name}")
    print(f"AKS Cluster: {aks_cluster}")
    print("=====================================================================")
    print("1. Provision gpt-5-mini model in Microsoft Foundry")
    print("2. Create Azure Container Registry (ACR)")
    print("3. Build and push API image to ACR")
    print("4. Create AKS cluster")
    print("5. Check deployment status")
    print("6. Deploy to AKS")
    print("7. Delete/Purge Foundry deployment")
    print("8. Delete failed AKS deployment")
    print("9. Exit")
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


def provision_foundry_resources(foundry_resource: str) -> bool:
    print("Provisioning Microsoft Foundry project with gpt-5-mini model...")
    print()

    if not create_resource_group():
        return False

    print()
    print(f"Checking for existing Microsoft Foundry resource: {foundry_resource}")
    existing = az_query(
        ["az", "cognitiveservices", "account", "show",
         "--name", foundry_resource, "--resource-group", rg,
         "--query", "name", "-o", "tsv"]
    )
    if not existing:
        print(f"Creating Microsoft Foundry resource: {foundry_resource}")
        if not run_quiet(
            "Create Microsoft Foundry resource",
            [
                "az", "cognitiveservices", "account", "create",
                "--name", foundry_resource,
                "--resource-group", rg,
                "--location", location,
                "--custom-domain", foundry_resource,
                "--kind", "AIServices",
                "--sku", "s0",
                "--yes",
            ],
        ):
            return False
        print("Foundry resource created")
    else:
        print("Foundry resource already exists")

    print()
    print("Retrieving Foundry endpoint...")
    endpoint = az_query(
        ["az", "cognitiveservices", "account", "show",
         "--name", foundry_resource, "--resource-group", rg,
         "--query", "properties.endpoint", "-o", "tsv"]
    )
    if not endpoint:
        print("Error: Failed to retrieve endpoint.")
        return False
    print("Endpoint retrieved successfully")

    print()
    print(f"Checking for existing {FOUNDRY_MODEL_NAME} deployment...")
    deployment = az_query(
        ["az", "cognitiveservices", "account", "deployment", "show",
         "--name", foundry_resource, "--resource-group", rg,
         "--deployment-name", FOUNDRY_MODEL_NAME,
         "--query", "name", "-o", "tsv"]
    )
    if not deployment:
        print(f"Deploying {FOUNDRY_MODEL_NAME} model (this may take a few minutes)...")
        if not run_quiet(
            f"Deploy {FOUNDRY_MODEL_NAME} model",
            [
                "az", "cognitiveservices", "account", "deployment", "create",
                "--name", foundry_resource,
                "--resource-group", rg,
                "--deployment-name", FOUNDRY_MODEL_NAME,
                "--model-name", FOUNDRY_MODEL_NAME,
                "--model-version", FOUNDRY_MODEL_VERSION,
                "--model-format", "OpenAI",
                "--sku-capacity", "1",
                "--sku-name", "GlobalStandard",
            ],
        ):
            return False
        print("Model deployed successfully")
    else:
        print(f"{FOUNDRY_MODEL_NAME} deployment already exists")

    print()
    print("Foundry provisioning complete")
    print()
    print("Foundry Resource Details:")
    print(f"  Resource: {foundry_resource}")
    print(f"  Endpoint: {endpoint}")
    return True


def create_acr(acr_name: str) -> bool:
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
                "--admin-enabled", "true",
            ],
        ):
            return False
        print(f"ACR created: {acr_name}")
    else:
        print(f"ACR already exists: {acr_name}")
    return True


def build_and_push_image(acr_name: str) -> bool:
    print("Building and pushing API image to ACR...")
    acr_server = az_query(
        ["az", "acr", "show", "--resource-group", rg, "--name", acr_name,
         "--query", "loginServer", "-o", "tsv"]
    )
    if not acr_server:
        print("Error: Could not retrieve ACR login server.")
        return False

    if not run_quiet(
        "Build and push API image",
        [
            "az", "acr", "build",
            "--resource-group", rg,
            "--registry", acr_name,
            "--image", f"{API_IMAGE_NAME}:latest",
            "--file", "api/Dockerfile",
            "--no-logs",
            "api/",
        ],
    ):
        return False

    print(f"Image built and pushed: {acr_server}/{API_IMAGE_NAME}:latest")
    return True


def _print_aks_failure_hint() -> None:
    print()
    print("The AKS deployment failed. Review the Azure error details above.")
    print("Quota checks can fail before a cluster is created, while later failures")
    print("can leave a cluster in a Failed state. Use option 5 to check the status.")
    print("For regional capacity or SKU availability errors, change the 'location'")
    print("variable near the top of this script. For quota errors, use a region with")
    print("available quota or request a quota increase.")
    print("Correct the reported issue, then use option 8 to delete any failed deployment.")


def create_aks_cluster(acr_name: str, aks_cluster: str) -> bool:
    aks_state = az_query(
        ["az", "aks", "show", "--resource-group", rg, "--name", aks_cluster,
         "--query", "provisioningState", "-o", "tsv"]
    )
    if aks_state == "Succeeded":
        print(f"AKS cluster already exists: {aks_cluster} (State: {aks_state})")
        return True
    if aks_state in ("Failed", "Canceled"):
        print(f"Error: AKS cluster '{aks_cluster}' is in a {aks_state} state.")
        print("Review the Azure error, correct the underlying issue, then use option 8")
        print("to delete the failed deployment before running option 4 again.")
        return False
    if aks_state:
        print(f"AKS cluster '{aks_cluster}' is still provisioning (State: {aks_state}).")
        print("Please wait for it to finish, then check the deployment status from the menu.")
        return True

    print(f"Creating AKS cluster '{aks_cluster}' with one {AKS_VM_SIZE} node...")
    print("This may take 5-10 minutes to complete. Please wait...")
    print()
    start = time.monotonic()

    if not run_quiet(
        "Create AKS cluster",
        [
            "az", "aks", "create",
            "--resource-group", rg,
            "--location", location,
            "--name", aks_cluster,
            "--node-count", "1",
            "--node-vm-size", AKS_VM_SIZE,
            "--tier", "free",
            "--vm-set-type", "VirtualMachineScaleSets",
            "--load-balancer-sku", "standard",
            "--enable-managed-identity",
            "--network-plugin", "azure",
            "--no-ssh-key",
            "--attach-acr", acr_name,
        ],
    ):
        _print_aks_failure_hint()
        return False

    elapsed = int(time.monotonic() - start)
    minutes, seconds = divmod(elapsed, 60)
    print(f"AKS cluster creation completed: {aks_cluster}")
    print(f"  Deployment time: {minutes}m {seconds}s")
    return True


def delete_failed_aks_deployment(aks_cluster: str) -> bool:
    aks_state = az_query(
        ["az", "aks", "show", "--resource-group", rg, "--name", aks_cluster,
         "--query", "provisioningState", "-o", "tsv"]
    )

    if not aks_state:
        print(f"No AKS deployment was found: {aks_cluster}")
        return True

    if aks_state not in ("Failed", "Canceled"):
        print(f"Error: Refusing to delete AKS cluster '{aks_cluster}' (State: {aks_state}).")
        print("This option only deletes deployments in a Failed or Canceled state.")
        return False

    print(f"WARNING: This permanently deletes AKS cluster '{aks_cluster}' and its")
    print("AKS-managed resources. This action cannot be undone.")
    confirm = input("Are you sure you want to delete the failed deployment? (yes/no): ")

    if confirm != "yes":
        print("Deletion canceled.")
        return True

    if not run_quiet(
        "Delete failed AKS deployment",
        [
            "az", "aks", "delete",
            "--resource-group", rg,
            "--name", aks_cluster,
            "--yes",
        ],
    ):
        return False

    print(f"Failed AKS deployment deleted: {aks_cluster}")
    return True


def _kubectl_apply_from_stdin(description: str, yaml_text: str, namespace: str = "default") -> bool:
    """Pipe YAML text to `kubectl apply -f -` in the given namespace."""
    kubectl = _resolve_exe("kubectl")
    result = subprocess.run(
        [kubectl, "apply", "-f", "-", "-n", namespace],
        input=yaml_text, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"Error: {description} failed (exit code {result.returncode}).")
        combined = (result.stdout or "") + (result.stderr or "")
        if combined.strip():
            print(combined.rstrip())
        return False
    return True


def deploy_to_aks(foundry_resource: str, acr_name: str, aks_cluster: str) -> bool:
    print("Deploying application to AKS...")
    print()

    print("Getting AKS credentials...")
    if not run_quiet(
        "Get AKS credentials",
        [
            "az", "aks", "get-credentials",
            "--resource-group", rg,
            "--name", aks_cluster,
            "--overwrite-existing",
        ],
    ):
        return False
    print("AKS credentials configured")
    print()

    print("Retrieving Foundry endpoint...")
    endpoint = az_query(
        ["az", "cognitiveservices", "account", "show",
         "--name", foundry_resource, "--resource-group", rg,
         "--query", "properties.endpoint", "-o", "tsv"]
    )
    if not endpoint:
        print("Error: Could not retrieve Foundry endpoint.")
        return False
    print("Foundry endpoint retrieved")
    print()

    print("Assigning Cognitive Services OpenAI User role to AKS identity...")
    kubelet_identity = az_query(
        ["az", "aks", "show", "--name", aks_cluster, "--resource-group", rg,
         "--query", "identityProfile.kubeletidentity.objectId", "-o", "tsv"]
    )
    foundry_resource_id = az_query(
        ["az", "cognitiveservices", "account", "show",
         "--name", foundry_resource, "--resource-group", rg,
         "--query", "id", "-o", "tsv"]
    )
    if not kubelet_identity or not foundry_resource_id:
        print("Error: Could not retrieve AKS identity or Foundry resource ID.")
        return False

    if not run_quiet(
        "Assign Cognitive Services OpenAI User role",
        [
            "az", "role", "assignment", "create",
            "--assignee-object-id", kubelet_identity,
            "--assignee-principal-type", "ServicePrincipal",
            "--role", "Cognitive Services OpenAI User",
            "--scope", foundry_resource_id,
        ],
    ):
        return False
    print("Role assigned to AKS kubelet identity (may take 1-2 minutes to propagate)")
    print()

    print("Deploying Kubernetes manifests...")
    deployment_yaml = Path("k8s/deployment.yaml").read_text(encoding="utf-8")
    deployment_yaml = deployment_yaml.replace("ACR_ENDPOINT", f"{acr_name}.azurecr.io")
    deployment_yaml = deployment_yaml.replace("FOUNDRY_ENDPOINT", endpoint)
    if not _kubectl_apply_from_stdin("Apply deployment manifest", deployment_yaml):
        return False
    print(f"Deployment manifest updated with ACR endpoint: {acr_name}.azurecr.io and Foundry endpoint")

    service_yaml = Path("k8s/service.yaml").read_text(encoding="utf-8")
    if not _kubectl_apply_from_stdin("Apply service manifest", service_yaml):
        return False
    print("Service manifest applied")
    print()

    print("Waiting for LoadBalancer external IP (this may take a few minutes)...")
    kubectl = _resolve_exe("kubectl")
    external_ip = ""
    for _ in range(60):
        result = subprocess.run(
            [kubectl, "get", "svc", "aks-api-service",
             "-o", "jsonpath={.status.loadBalancer.ingress[0].ip}",
             "-n", "default"],
            capture_output=True, text=True, check=False,
        )
        candidate = (result.stdout or "").strip()
        if candidate and not candidate.startswith("10."):
            external_ip = candidate
            break
        time.sleep(2)

    if not external_ip:
        print("Error: Could not obtain external IP for the service.")
        print("You can check the service status manually with: kubectl get svc aks-api-service")
        return False
    print(f"External IP obtained: {external_ip}")
    print()

    print("Updating client/.env and client/.env.ps1 with API endpoint...")
    write_env_files({"API_ENDPOINT": f"http://{external_ip}"}, directory="client")
    print("client/.env and client/.env.ps1 updated")
    print()
    print("==========================================")
    print("Deployment completed successfully!")
    print("==========================================")
    print(f"API Endpoint: http://{external_ip}")
    print()
    print("Next steps:")
    print("1. Run the client to test the API:")
    print("   python client/main.py")
    print("==========================================")
    return True


def delete_foundry_resource(foundry_resource: str) -> bool:
    print(f"Deleting and purging Foundry resource: {foundry_resource}")
    print()
    confirm = input("Are you sure you want to delete the Foundry resources? (yes/no): ")

    if confirm != "yes":
        print("Cancelled. Foundry resource was not deleted.")
        return True

    print()
    exists = az_query(
        ["az", "cognitiveservices", "account", "show",
         "--name", foundry_resource, "--resource-group", rg,
         "--query", "name", "-o", "tsv"]
    )
    if not exists:
        print(f"Foundry resource does not exist: {foundry_resource}")
        return True

    print("Deleting Foundry resource...")
    if not run_quiet(
        "Delete Foundry resource",
        [
            "az", "cognitiveservices", "account", "delete",
            "--name", foundry_resource,
            "--resource-group", rg,
        ],
    ):
        return False
    print("Resource deleted")
    print()

    print("Purging resource to free up the name...")
    if not run_quiet(
        "Purge Foundry resource",
        [
            "az", "cognitiveservices", "account", "purge",
            "--name", foundry_resource,
            "--resource-group", rg,
            "--location", location,
        ],
    ):
        return False
    print("Resource purged")
    print("The Foundry resource has been deleted and purged.")
    return True


def check_deployment_status(foundry_resource: str, acr_name: str, aks_cluster: str) -> bool:
    print("Checking deployment status...")
    print()

    print(f"Foundry Model Deployment ({FOUNDRY_MODEL_NAME}):")
    foundry_status = az_query(
        ["az", "cognitiveservices", "account", "deployment", "show",
         "--name", foundry_resource, "--resource-group", rg,
         "--deployment-name", FOUNDRY_MODEL_NAME,
         "--query", "properties.provisioningState", "-o", "tsv"]
    )
    if foundry_status:
        print(f"  Status: {foundry_status}")
        if foundry_status == "Succeeded":
            print("  Model deployed and ready")
    else:
        print("  Status: Not found or not deployed")

    print()
    print(f"Azure Container Registry ({acr_name}):")
    acr_status = az_query(
        ["az", "acr", "show", "--resource-group", rg, "--name", acr_name,
         "--query", "provisioningState", "-o", "tsv"]
    )
    if acr_status:
        print(f"  Status: {acr_status}")
    else:
        print("  Status: Not found or not ready")

    print()
    print(f"AKS Cluster ({aks_cluster}):")
    aks_status = az_query(
        ["az", "aks", "show", "--resource-group", rg, "--name", aks_cluster,
         "--query", "provisioningState", "-o", "tsv"]
    )
    if aks_status:
        print(f"  Status: {aks_status}")
        if aks_status == "Succeeded":
            print("  AKS cluster is ready for deployment")
    else:
        print("  Status: Not found or not ready")
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
    foundry_resource, acr_name, aks_cluster = _derived_names(user_object_id)

    while True:
        show_menu(foundry_resource, acr_name, aks_cluster)
        choice = input("Please select an option (1-9): ").strip()

        if choice in {"1", "2", "3", "4", "5", "6", "7", "8", "9"}:
            clear_screen()

        if choice == "1":
            print()
            provision_foundry_resources(foundry_resource)
            print()
            pause()
        elif choice == "2":
            print()
            if create_resource_group():
                print()
                create_acr(acr_name)
            print()
            pause()
        elif choice == "3":
            print()
            build_and_push_image(acr_name)
            print()
            pause()
        elif choice == "4":
            print()
            create_aks_cluster(acr_name, aks_cluster)
            print()
            pause()
        elif choice == "5":
            print()
            check_deployment_status(foundry_resource, acr_name, aks_cluster)
            print()
            pause()
        elif choice == "6":
            print()
            deploy_to_aks(foundry_resource, acr_name, aks_cluster)
            print()
            pause()
        elif choice == "7":
            print()
            delete_foundry_resource(foundry_resource)
            print()
            pause()
        elif choice == "8":
            print()
            delete_failed_aks_deployment(aks_cluster)
            print()
            pause()
        elif choice == "9":
            print("Exiting...")
            clear_screen()
            sys.exit(0)
        else:
            print("Invalid option. Please select 1-9.")
            pause()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
