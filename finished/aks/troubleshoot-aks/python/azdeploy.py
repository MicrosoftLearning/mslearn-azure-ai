# =============================================================================
# Change the values of these variables as needed.
# =============================================================================

# rg = "<your-resource-group-name>"  # Resource Group name
# location = "<your-azure-region>"   # Azure region for the resources

rg = "rg-exercises"          # Resource Group name
location = "eastus2"         # Azure region for the resources

# If the Standard_D2s_v7 SKU is not available in your region, try using Standard_D2s_v5, or Standard_D2s_v6 instead.
AKS_VM_SIZE = "Standard_D2s_v7"

# =============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# =============================================================================

import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

API_IMAGE_NAME = "aks-troubleshoot-api"
NAMESPACE = "aks-troubleshoot"

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
    print("    AKS Troubleshooting Exercise - Deployment Script")
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
    print("5. Deploy application to AKS")
    print("6. Check deployment status")
    print("7. Delete failed AKS deployment")
    print("8. Exit")
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


def _update_deployment_yaml_images(acr_name: str) -> None:
    """Rewrite the `image:` line in every k8s/*-deployment.yaml to point at ACR."""
    image_url = f"{acr_name}.azurecr.io/{API_IMAGE_NAME}:latest"
    pattern = re.compile(r"^\s*image:.*$", re.MULTILINE)
    for yaml_path in Path("k8s").glob("*-deployment.yaml"):
        text = yaml_path.read_text(encoding="utf-8")
        # Preserve leading whitespace on each matched line.
        new_text = re.sub(
            r"(?m)^(\s*)image:.*$",
            lambda m: f"{m.group(1)}image: {image_url}",
            text,
        )
        yaml_path.write_text(new_text, encoding="utf-8", newline="\n")


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

    print("Updating deployment YAML files with the ACR image reference...")
    _update_deployment_yaml_images(acr_name)
    print("Deployment YAML files updated")
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
    print("can leave a cluster in a Failed state. Use option 6 to check the status.")
    print("For regional capacity or SKU availability errors, change the 'location'")
    print("variable near the top of this script. For quota errors, use a region with")
    print("available quota or request a quota increase.")
    print("Correct the reported issue, then use option 7 to delete any failed deployment.")


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
        print("Review the Azure error, correct the underlying issue, then use option 7")
        print("to delete the failed deployment before running option 3 again.")
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
    print("  kubectl get pods --all-namespaces")
    return True


def _kubectl_apply_from_stdin(description: str, yaml_text: str, namespace: str) -> bool:
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


def deploy_to_aks() -> bool:
    print("Deploying application to AKS...")
    print()

    print(f"Creating namespace '{NAMESPACE}'...")
    kubectl = _resolve_exe("kubectl")
    ns_yaml = subprocess.run(
        [kubectl, "create", "namespace", NAMESPACE,
         "--dry-run=client", "-o", "yaml"],
        capture_output=True, text=True, check=False,
    )
    if ns_yaml.returncode != 0:
        print("Error: Could not render namespace manifest.")
        if ns_yaml.stderr:
            print(ns_yaml.stderr.rstrip())
        return False
    if not _kubectl_apply_from_stdin("Apply namespace", ns_yaml.stdout, namespace="default"):
        return False

    print("Deploying API...")
    if not run_quiet(
        "Apply API deployment",
        ["kubectl", "apply", "-f", "k8s/api-deployment.yaml", "-n", NAMESPACE],
    ):
        return False

    print("Creating Service...")
    if not run_quiet(
        "Apply API service",
        ["kubectl", "apply", "-f", "k8s/api-service.yaml", "-n", NAMESPACE],
    ):
        return False

    print()
    print("Waiting for deployment to be ready...")
    if not run_quiet(
        "Wait for deployment rollout",
        ["kubectl", "rollout", "status", "deployment/api-deployment",
         "-n", NAMESPACE, "--timeout=120s"],
    ):
        return False

    print()
    print("Application deployed successfully")
    print()
    print("To test the application:")
    print(f"  kubectl port-forward service/api-service 8080:80 -n {NAMESPACE}")
    print("  curl http://localhost:8080/healthz")
    return True


def _kubectl_available() -> bool:
    kubectl = shutil.which("kubectl")
    if not kubectl:
        return False
    result = subprocess.run(
        [kubectl, "cluster-info"], capture_output=True, text=True, check=False
    )
    return result.returncode == 0


def _kubectl_run(argv: list[str]) -> str:
    kubectl = _resolve_exe("kubectl")
    result = subprocess.run(
        [kubectl, *argv], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return ""
    return (result.stdout or "").rstrip()


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
            print("  AKS cluster is ready")
    else:
        print("  Status: Not found or not ready")

    if not _kubectl_available():
        return True

    print()
    print(f"Kubernetes Resources ({NAMESPACE} namespace):")

    ns_status = _kubectl_run(
        ["get", "namespace", NAMESPACE, "-o", "jsonpath={.status.phase}"]
    )
    print(f"  Namespace: {ns_status if ns_status else 'Not created'}")

    ready = _kubectl_run(
        ["get", "deployment", "api-deployment", "-n", NAMESPACE,
         "-o", "jsonpath={.status.readyReplicas}"]
    )
    desired = _kubectl_run(
        ["get", "deployment", "api-deployment", "-n", NAMESPACE,
         "-o", "jsonpath={.spec.replicas}"]
    )
    if ready or desired:
        print(f"  Deployment: {ready or 0}/{desired or 0} replicas ready")
    else:
        print("  Deployment: Not created")

    print()
    print("  Pods:")
    pods = _kubectl_run(
        ["get", "pods", "-n", NAMESPACE, "-o",
         "custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[0].ready,STATUS:.status.phase"]
    )
    if pods:
        for line in pods.splitlines():
            print(f"    {line}")
    else:
        print("    No pods found")

    print()
    print("  Service:")
    svc = _kubectl_run(
        ["get", "svc", "-n", NAMESPACE, "-o",
         "custom-columns=NAME:.metadata.name,TYPE:.spec.type,CLUSTER-IP:.spec.clusterIP,EXTERNAL-IP:.status.loadBalancer.ingress[0].ip,PORT:.spec.ports[0].port"]
    )
    if svc:
        for line in svc.splitlines():
            print(f"    {line}")
    else:
        print("    No services found")

    print()
    print("  EndpointSlices:")
    eps = _kubectl_run(
        ["get", "endpointslices", "-n", NAMESPACE, "-o",
         "custom-columns=NAME:.metadata.name,ENDPOINTS:.endpoints[0].addresses[0]"]
    )
    if eps:
        for line in eps.splitlines():
            print(f"    {line}")
    else:
        print("    No endpoint slices found")
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
        choice = input("Please select an option (1-8): ").strip()

        if choice in {"1", "2", "3", "4", "5", "6", "7", "8"}:
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
            deploy_to_aks()
            print()
            pause()
        elif choice == "6":
            print()
            check_deployment_status(acr_name, aks_cluster)
            print()
            pause()
        elif choice == "7":
            print()
            delete_failed_aks_deployment(aks_cluster)
            print()
            pause()
        elif choice == "8":
            print("Exiting...")
            clear_screen()
            sys.exit(0)
        else:
            print("Invalid option. Please select 1-8.")
            pause()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
