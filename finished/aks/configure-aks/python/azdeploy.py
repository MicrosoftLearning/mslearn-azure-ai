# =============================================================================
# Change the values of these variables as needed.
# =============================================================================

# rg = "<your-resource-group-name>"  # Resource Group name
# location = "<your-azure-region>"   # Azure region for the resources

rg = "rg-exercises"          # Resource Group name
location = "canadacentral"   # Azure region for the resources

# If the Standard_D2s_v7 SKU is not available in your region, try using Standard_D2s_v5, or Standard_D2s_v6 instead.
# AKS_VM_SIZE = "Standard_D2s_v7" # Keeping for production
AKS_VM_SIZE = "Standard_D2s_v5"

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

API_IMAGE_NAME = "aks-config-api"

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


def _derived_names(user_object_id: str) -> tuple[str, str]:
    user_hash = hashlib.sha1(user_object_id.encode("utf-8")).hexdigest()[:8]
    return f"acr{user_hash}", f"aks-{user_hash}"


def show_menu(acr_name: str, aks_cluster: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    AKS Configuration Exercise - Deployment Script")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"ACR Name: {acr_name}")
    print(f"AKS Cluster: {aks_cluster}")
    print("=====================================================================")
    print("1. Create Azure Container Registry (ACR)")
    print("2. Build and push API image to ACR")
    print("3. Create AKS cluster")
    print("4. Get AKS credentials for kubectl")
    print("5. Check deployment status")
    print("6. Delete failed AKS deployment")
    print("7. Exit")
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
    print(f"ACR endpoint: {acr_name}.azurecr.io")
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
    print("Correct the reported issue, then use option 6 to delete any failed deployment.")


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
        print("Review the Azure error, correct the underlying issue, then use option 6")
        print("to delete the failed deployment before running option 3 again.")
        return False
    if aks_state and aks_state != "":
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

    print("Configuring storage permissions for Azure Files...")
    kubelet_id = az_query(
        ["az", "aks", "show", "--resource-group", rg, "--name", aks_cluster,
         "--query", "identityProfile.kubeletidentity.clientId", "-o", "tsv"]
    )
    node_rg = az_query(
        ["az", "aks", "show", "--resource-group", rg, "--name", aks_cluster,
         "--query", "nodeResourceGroup", "-o", "tsv"]
    )
    subscription_id = az_query(["az", "account", "show", "--query", "id", "-o", "tsv"])

    if not kubelet_id or not node_rg or not subscription_id:
        print("Error: Could not retrieve the AKS identity or node resource group.")
        return False

    scope = f"/subscriptions/{subscription_id}/resourceGroups/{node_rg}"
    if not run_quiet(
        "Configure storage permissions",
        [
            "az", "role", "assignment", "create",
            "--role", "Storage Account Contributor",
            "--assignee", kubelet_id,
            "--scope", scope,
        ],
    ):
        return False

    print("Storage permissions configured")
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


def get_aks_credentials(aks_cluster: str) -> bool:
    print("Getting AKS credentials for kubectl...")
    print()

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
    print("You can now use kubectl to interact with your AKS cluster.")
    print()
    print("Example commands:")
    print("  kubectl get nodes")
    print("  kubectl get pods -n default")
    print("  kubectl apply -f k8s/configmap.yaml")
    print("  kubectl apply -f k8s/secrets.yaml")
    print("  kubectl apply -f k8s/pvc.yaml")
    return True


def _kubectl_available() -> bool:
    kubectl = shutil.which("kubectl")
    if not kubectl:
        return False
    result = subprocess.run(
        [kubectl, "cluster-info"], capture_output=True, text=True, check=False
    )
    return result.returncode == 0


def check_deployment_status(acr_name: str, aks_cluster: str) -> bool:
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

    if not _kubectl_available():
        return True

    print()
    print("Kubernetes Resources:")

    configmap = az_query(
        ["kubectl", "get", "configmap", "api-config", "-n", "default",
         "-o", "jsonpath={.metadata.name}"]
    )
    print(f"  ConfigMap: {'Created' if configmap else 'Not created'}")

    secret = az_query(
        ["kubectl", "get", "secret", "api-secrets", "-n", "default",
         "-o", "jsonpath={.metadata.name}"]
    )
    print(f"  Secrets: {'Created' if secret else 'Not created'}")

    pvc = az_query(
        ["kubectl", "get", "pvc", "api-logs-pvc", "-n", "default",
         "-o", "jsonpath={.status.phase}"]
    )
    print(f"  PVC: {pvc if pvc else 'Not created'}")

    deployment = az_query(
        ["kubectl", "get", "deployment", "aks-config-api", "-n", "default",
         "-o", 'jsonpath={.status.conditions[?(@.type=="Available")].status}']
    )
    print(f"  Deployment: {'Available' if deployment == 'True' else 'Not available'}")

    service_ip = az_query(
        ["kubectl", "get", "svc", "aks-config-api-service", "-n", "default",
         "-o", "jsonpath={.status.loadBalancer.ingress[0].ip}"]
    )
    if service_ip:
        print(f"  Service: Exposed at {service_ip}")
    else:
        print("  Service: LoadBalancer IP pending or not created")
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
    acr_name, aks_cluster = _derived_names(user_object_id)

    while True:
        show_menu(acr_name, aks_cluster)
        choice = input("Please select an option (1-7): ").strip()

        if choice in {"1", "2", "3", "4", "5", "6", "7"}:
            clear_screen()

        if choice == "1":
            print()
            if create_resource_group():
                print()
                create_acr(acr_name)
            print()
            pause()
        elif choice == "2":
            print()
            build_and_push_image(acr_name)
            print()
            pause()
        elif choice == "3":
            print()
            create_aks_cluster(acr_name, aks_cluster)
            print()
            pause()
        elif choice == "4":
            print()
            get_aks_credentials(aks_cluster)
            print()
            pause()
        elif choice == "5":
            print()
            check_deployment_status(acr_name, aks_cluster)
            print()
            pause()
        elif choice == "6":
            print()
            delete_failed_aks_deployment(aks_cluster)
            print()
            pause()
        elif choice == "7":
            print("Exiting...")
            clear_screen()
            sys.exit(0)
        else:
            print("Invalid option. Please select 1-7.")
            pause()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
