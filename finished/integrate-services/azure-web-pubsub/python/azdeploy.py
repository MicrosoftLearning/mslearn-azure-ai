# =============================================================================
# Change the values of these variables as needed.
# =============================================================================

# rg = "<your-resource-group-name>"  # Resource Group name
# location = "<your-azure-region>"   # Azure region for the resources

rg = "rg-exercises"
location = "westus2"

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
from urllib.parse import urlsplit

os.environ.setdefault("AZURE_CORE_ONLY_SHOW_ERRORS", "true")
_EXE_CACHE: dict[str, str] = {}
webpubsub_sku = "Standard_S1"
webpubsub_units = 1
CONTAINER = "investigations"
HUB = "investigations"
WEBPUBSUB_ROLE = "Web PubSub Service Owner"
STORAGE_ROLE = "Storage Blob Data Contributor"


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
    result = subprocess.run(
        argv, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"Error: {description} failed (exit code {result.returncode}).")
        combined = (result.stdout or "") + (result.stderr or "")
        if combined.strip():
            print(combined.rstrip())
        return False
    return True


def az_query(argv: list[str], *, missing_ok: bool = False) -> str:
    argv = [_resolve_exe(argv[0]), *argv[1:]]
    result = subprocess.run(
        argv, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        output = (result.stdout or "") + (result.stderr or "")
        missing_codes = ("(ResourceNotFound)", "(ResourceGroupNotFound)", "(StorageAccountNotFound)")
        if missing_ok and any(code in output for code in missing_codes):
            return ""
        raise RuntimeError(f"Azure CLI failed (exit code {result.returncode}):\n{output.strip()}")
    return (result.stdout or "").strip()


def clear_screen() -> None:
    if os.system("cls" if os.name == "nt" else "clear") != 0:
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
    try:
        user_object_id = az_query(
            ["az", "ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"]
        )
    except RuntimeError as exc:
        if "az login" not in str(exc).lower():
            raise
        user_object_id = ""
    if not user_object_id:
        print("Error: Not authenticated with Azure. Please run: az login")
        sys.exit(1)
    return user_object_id


def require_webpubsub_extension() -> None:
    extensions = az_query(["az", "extension", "list", "--query", "[].name", "-o", "tsv"])
    if "webpubsub" not in extensions.splitlines():
        raise RuntimeError("Install the Web PubSub CLI extension: az extension add --name webpubsub")


def _derived_names(user_object_id: str) -> tuple[str, str]:
    user_hash = hashlib.sha1(user_object_id.encode("utf-8")).hexdigest()[:8]
    return f"wps-investigation-{user_hash}", f"stinvestigation{user_hash}"


def _resource_id(subscription_id: str, resource_type: str, resource_name: str) -> str:
    return (
        f"/subscriptions/{subscription_id}/resourceGroups/{rg}"
        f"/providers/{resource_type}/{resource_name}"
    )


def show_resource(subscription_id: str, resource_type: str, resource_name: str):
    output = az_query([
        "az", "resource", "show",
        "--ids", _resource_id(subscription_id, resource_type, resource_name), "-o", "json",
    ], missing_ok=True)
    if not output:
        return None
    try:
        resource = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Azure CLI returned invalid resource JSON.") from exc
    if not isinstance(resource, dict) or not isinstance(resource.get("properties"), dict):
        raise RuntimeError("Azure CLI returned invalid resource details.")
    return resource


def ready_for_create(subscription_id: str, resource_type: str, resource_name: str) -> bool:
    retry_option = 1 if resource_type == "Microsoft.SignalRService/WebPubSub" else 2
    resource = show_resource(subscription_id, resource_type, resource_name)
    if resource is None:
        return True
    state = resource["properties"].get("provisioningState")
    if state == "Succeeded":
        print(f"Resource already exists: {resource_name}")
        return False
    if state in ("Failed", "Canceled"):
        print(f"Removing failed resource before retrying: {resource_name}")
        if resource_type == "Microsoft.SignalRService/WebPubSub":
            deleted = run_quiet("Delete failed Web PubSub resource", [
                "az", "webpubsub", "delete", "--name", resource_name,
                "--resource-group", rg, "--subscription", subscription_id,
            ])
        else:
            deleted = run_quiet("Delete failed storage account", [
                "az", "storage", "account", "delete", "--name", resource_name,
                "--resource-group", rg, "--subscription", subscription_id, "--yes",
            ])
        if not deleted:
            raise RuntimeError(
                f"Failed resource could not be deleted. Resolve the error and retry option {retry_option}."
            )
        for _ in range(60):
            if show_resource(subscription_id, resource_type, resource_name) is None:
                return True
            time.sleep(5)
        raise RuntimeError(
            f"Timed out waiting for failed resource deletion. Wait, then retry option {retry_option}."
        )
    raise RuntimeError(f"{resource_name} is not ready (state: {state}). Wait, then check option 4.")


def create_resource_group(subscription_id: str) -> bool:
    print(f"Checking resource group '{rg}'...")
    exists = az_query([
        "az", "group", "exists", "--name", rg, "--subscription", subscription_id, "-o", "tsv",
    ])
    if exists == "false":
        if not run_quiet("Create resource group", [
            "az", "group", "create", "--name", rg, "--location", location,
            "--subscription", subscription_id,
        ]):
            return False
        print(f"Resource group created: {rg}")
    elif exists == "true":
        print(f"Resource group already exists: {rg}")
    else:
        raise RuntimeError("Could not verify the resource group.")
    return True


def has_role_assignment(
    subscription_id: str, resource_type: str, resource_name: str,
    user_object_id: str, role: str,
) -> bool:
    scope = _resource_id(subscription_id, resource_type, resource_name)
    assignments = az_query([
        "az", "role", "assignment", "list", "--assignee-object-id", user_object_id,
        "--scope", scope, "--role", role, "--fill-principal-name", "false",
        "--subscription", subscription_id, "--query", "length(@)", "-o", "tsv",
    ])
    if not assignments.isdigit():
        raise RuntimeError(f"Could not verify the {role} role assignment.")
    return int(assignments) > 0


def assign_role(
    subscription_id: str, resource_type: str, resource_name: str,
    user_object_id: str, role: str,
) -> bool:
    scope = _resource_id(subscription_id, resource_type, resource_name)
    if not has_role_assignment(subscription_id, resource_type, resource_name, user_object_id, role):
        if not run_quiet(f"Assign {role}", [
            "az", "role", "assignment", "create", "--assignee-object-id", user_object_id,
            "--assignee-principal-type", "User", "--role", role,
            "--scope", scope, "--subscription", subscription_id,
        ]):
            return False
    print(f"Assigned or already present: {role}")
    return True


def check_provider_registration(subscription_id: str, namespace: str) -> bool:
    print(f"Checking resource provider registration: {namespace}...", flush=True)
    state = az_query([
        "az", "provider", "show", "--namespace", namespace,
        "--subscription", subscription_id, "--query", "registrationState", "-o", "tsv",
    ])
    if state == "Registered":
        print(f"Resource provider registered: {namespace}", flush=True)
        return True
    if not state:
        print(f"Error: Could not determine the registration state for '{namespace}'.")
    else:
        print(f"Error: Resource provider '{namespace}' must be Registered (current state: {state}).")
        if state == "Registering":
            print("Registration is in progress. Wait for it to finish, then retry this option.")
        else:
            print("Register this provider in your subscription, then retry this option.")
    return False


def create_webpubsub(subscription_id: str, pubsub_name: str, user_object_id: str) -> bool:
    if not check_provider_registration(subscription_id, "Microsoft.SignalRService"):
        return False
    if not create_resource_group(subscription_id):
        return False
    if ready_for_create(subscription_id, "Microsoft.SignalRService/WebPubSub", pubsub_name):
        print(f"Creating Web PubSub {pubsub_name} in {location}. Please wait...")
        if not run_quiet("Create Web PubSub resource", [
            "az", "webpubsub", "create", "--name", pubsub_name, "--resource-group", rg,
            "--location", location, "--sku", webpubsub_sku,
            "--unit-count", str(webpubsub_units), "--subscription", subscription_id,
        ]):
            print("Check Web PubSub permissions, SKU availability, capacity, and quota.")
            print("If needed, change location or webpubsub_sku near the top of the script.")
            print("An existing resource cannot move regions; remove it before changing regions.")
            print("Retry option 1. Failed Web PubSub resources are removed before another create attempt.")
            return False
    if not run_quiet("Disable Web PubSub key authentication", [
        "az", "resource", "update",
        "--ids", _resource_id(subscription_id, "Microsoft.SignalRService/WebPubSub", pubsub_name),
        "--set", "properties.disableLocalAuth=true",
    ]):
        return False
    if not assign_role(
        subscription_id, "Microsoft.SignalRService/WebPubSub", pubsub_name,
        user_object_id, WEBPUBSUB_ROLE,
    ):
        return False
    print("Web PubSub is provisioned with Entra access. Next, choose option 2.")
    return True


def create_storage(subscription_id: str, storage_name: str, user_object_id: str) -> bool:
    if not check_provider_registration(subscription_id, "Microsoft.Storage"):
        return False
    if not create_resource_group(subscription_id):
        return False
    if ready_for_create(subscription_id, "Microsoft.Storage/storageAccounts", storage_name):
        print(f"Creating Blob Storage account {storage_name}. Please wait...")
        if not run_quiet("Create storage account", [
            "az", "storage", "account", "create", "--name", storage_name,
            "--resource-group", rg, "--location", location,
            "--kind", "StorageV2", "--sku", "Standard_LRS", "--https-only", "true",
            "--allow-shared-key-access", "false", "--allow-blob-public-access", "false",
            "--min-tls-version", "TLS1_2", "--subscription", subscription_id,
        ]):
            print("Check storage permissions, regional availability, and quota.")
            print("An existing resource cannot move regions; remove it before changing regions.")
            print("Retry option 2. Failed storage accounts are removed before another create attempt.")
            return False
    if not run_quiet("Secure storage account", [
        "az", "storage", "account", "update", "--name", storage_name,
        "--resource-group", rg, "--subscription", subscription_id,
        "--allow-shared-key-access", "false", "--allow-blob-public-access", "false",
        "--https-only", "true", "--min-tls-version", "TLS1_2",
    ]):
        return False
    if not assign_role(
        subscription_id, "Microsoft.Storage/storageAccounts", storage_name,
        user_object_id, STORAGE_ROLE,
    ):
        return False
    print("Storage is provisioned with Entra access. Next, choose option 3.")
    return True


def resource_details(subscription_id: str, pubsub_name: str, storage_name: str):
    pubsub = show_resource(subscription_id, "Microsoft.SignalRService/WebPubSub", pubsub_name)
    storage = show_resource(subscription_id, "Microsoft.Storage/storageAccounts", storage_name)
    for name, resource, option in (("Web PubSub", pubsub, 1), ("Storage", storage, 2)):
        if not resource:
            raise RuntimeError(f"{name} was not found. Run option {option} first.")
        if resource["properties"].get("provisioningState") != "Succeeded":
            raise RuntimeError(f"{name} is not ready. Check option 4, then retry option {option}.")
    if pubsub["properties"].get("disableLocalAuth") is not True:
        raise RuntimeError("Web PubSub key authentication is enabled. Run option 1.")
    if (
        storage["properties"].get("allowSharedKeyAccess") is not False
        or storage["properties"].get("allowBlobPublicAccess") is not False
    ):
        raise RuntimeError("Storage key or public access is enabled. Run option 2.")
    return pubsub, storage


def create_container(
    subscription_id: str, pubsub_name: str, storage_name: str,
) -> bool:
    resource_details(subscription_id, pubsub_name, storage_name)
    print("Creating the private Blob container. New storage role assignments may take several minutes.")
    for attempt in range(12):
        try:
            az_query([
                "az", "storage", "container", "create", "--account-name", storage_name,
                "--name", CONTAINER, "--auth-mode", "login", "--public-access", "off",
                "--subscription", subscription_id, "-o", "json",
            ])
            break
        except RuntimeError as exc:
            if not any(code in str(exc) for code in ("AuthorizationPermissionMismatch", "AuthorizationFailure")):
                raise
            if attempt == 11:
                raise RuntimeError(
                    "Storage access is not ready. Check the role assignment in option 2, "
                    "allow RBAC propagation, then retry option 3."
                ) from exc
            time.sleep(10)
    print(f"Private Blob container created or already present: {CONTAINER}")
    print("Next, choose option 4 to verify deployment and create environment files.")
    return True


def verify_deployment(
    subscription_id: str, pubsub_name: str, storage_name: str, user_object_id: str,
) -> bool:
    pubsub = show_resource(subscription_id, "Microsoft.SignalRService/WebPubSub", pubsub_name)
    storage = show_resource(subscription_id, "Microsoft.Storage/storageAccounts", storage_name)
    ready = True
    for name, resource, option in (("Web PubSub", pubsub, 1), ("Storage", storage, 2)):
        state = resource["properties"].get("provisioningState") if resource else "Not created"
        print(f"{name}: {state}")
        if state != "Succeeded":
            print(f"Error: {name} is not ready. Run option {option}.")
            ready = False

    if pubsub and pubsub["properties"].get("provisioningState") == "Succeeded":
        if pubsub["properties"].get("disableLocalAuth") is not True:
            print("Error: Web PubSub key authentication is enabled. Run option 1.")
            ready = False
        else:
            try:
                if not has_role_assignment(
                    subscription_id, "Microsoft.SignalRService/WebPubSub", pubsub_name,
                    user_object_id, WEBPUBSUB_ROLE,
                ):
                    raise RuntimeError(f"Required role '{WEBPUBSUB_ROLE}' is missing. Run option 1.")
                print(f"Web PubSub Entra role: {WEBPUBSUB_ROLE}")
                hostname = pubsub["properties"].get("hostName")
                if not isinstance(hostname, str) or not hostname or any(
                    character in hostname for character in "/?#@: \t\r\n"
                ):
                    raise RuntimeError("Web PubSub did not return a valid hostname. Run option 1.")
                endpoint = f"https://{hostname}"
                token_response = json.loads(az_query([
                    "az", "rest", "--method", "post",
                    "--url", (
                        f"{endpoint}/api/hubs/{HUB}/:generateToken"
                        "?api-version=2024-12-01&userId=readiness-probe&minutesToExpire=1"
                    ),
                    "--resource", "https://webpubsub.azure.com", "-o", "json",
                ]))
                if (
                    not isinstance(token_response, dict)
                    or not isinstance(token_response.get("token"), str)
                    or not token_response["token"].strip()
                ):
                    raise RuntimeError("The Web PubSub client-token API did not return a token.")
                print("Web PubSub client-token API: Ready")
            except (RuntimeError, ValueError) as exc:
                print(f"Error: Web PubSub access check failed: {exc}")
                print("Check the role assignment in option 1, allow RBAC propagation, then retry option 4.")
                ready = False

    if storage and storage["properties"].get("provisioningState") == "Succeeded":
        if (
            storage["properties"].get("allowSharedKeyAccess") is not False
            or storage["properties"].get("allowBlobPublicAccess") is not False
        ):
            print("Error: Storage key or public access is enabled. Run option 2.")
            ready = False
        else:
            try:
                if (
                    storage["properties"].get("supportsHttpsTrafficOnly") is not True
                    or storage["properties"].get("minimumTlsVersion") not in {"TLS1_2", "TLS1_3"}
                ):
                    raise RuntimeError("Storage must require HTTPS and TLS 1.2 or later. Run option 2.")
                if not has_role_assignment(
                    subscription_id, "Microsoft.Storage/storageAccounts", storage_name,
                    user_object_id, STORAGE_ROLE,
                ):
                    raise RuntimeError(f"Required role '{STORAGE_ROLE}' is missing. Run option 2.")
                print(f"Storage Entra role: {STORAGE_ROLE}")
                endpoints = storage["properties"].get("primaryEndpoints")
                blob_url = endpoints.get("blob") if isinstance(endpoints, dict) else None
                if not isinstance(blob_url, str):
                    raise RuntimeError("Storage did not return a Blob endpoint. Run option 2.")
                parsed_url = urlsplit(blob_url)
                if (
                    parsed_url.scheme != "https" or not parsed_url.hostname
                    or parsed_url.username or parsed_url.password
                    or parsed_url.query or parsed_url.fragment
                ):
                    raise RuntimeError("Storage did not return a valid HTTPS Blob endpoint. Run option 2.")
                exists = az_query([
                    "az", "storage", "container", "exists", "--account-name", storage_name,
                    "--name", CONTAINER, "--auth-mode", "login", "--subscription", subscription_id,
                    "--query", "exists", "-o", "tsv",
                ])
                if exists == "false":
                    print(f"Error: Blob container '{CONTAINER}' was not found. Run option 3.")
                    ready = False
                elif exists == "true":
                    blobs = json.loads(az_query([
                        "az", "storage", "blob", "list", "--account-name", storage_name,
                        "--container-name", CONTAINER, "--auth-mode", "login", "--num-results", "1",
                        "--subscription", subscription_id, "-o", "json",
                    ]))
                    if not isinstance(blobs, list):
                        raise RuntimeError("Blob Storage did not return a valid listing.")
                    print("Blob container and read access: Ready")
                else:
                    raise RuntimeError("Could not verify whether the Blob container exists.")
            except (RuntimeError, ValueError) as exc:
                print(f"Error: Blob Storage access check failed: {exc}")
                print("Check the role assignment in option 2, allow RBAC propagation, then retry option 4.")
                ready = False
    if not ready:
        print("Verification failed. Environment files were not created or updated.")
        return False

    write_env_files({
        "RESOURCE_GROUP": rg,
        "WEBPUBSUB_NAME": pubsub_name,
        "WEBPUBSUB_ENDPOINT": f"https://{pubsub['properties']['hostName']}",
        "WEBPUBSUB_HUB": HUB,
        "STORAGE_ACCOUNT_NAME": storage_name,
        "BLOB_ACCOUNT_URL": storage["properties"]["primaryEndpoints"]["blob"].rstrip("/"),
        "BLOB_CONTAINER": CONTAINER,
    }, str(Path(__file__).resolve().parent))
    print("Deployment verified. Generated .env and .env.ps1 alongside azdeploy.py.")
    return True


def show_menu(subscription_id: str, pubsub_name: str, storage_name: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    Azure Web PubSub Deployment Menu")
    print("=====================================================================")
    print(f"Subscription: {subscription_id}")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"Web PubSub: {pubsub_name}")
    print(f"Storage Account: {storage_name}")
    print("=====================================================================")
    print("1. Create Azure Web PubSub and assign its Entra role")
    print("2. Create storage account and assign its Entra role")
    print("3. Create the private Blob container")
    print("4. Verify deployment and create environment files")
    print("5. Exit")
    print("=====================================================================")


def _preflight() -> None:
    script_dir = Path(__file__).resolve().parent
    if not (script_dir / "client" / "app.py").is_file():
        print(
            "Error: 'client/app.py' is missing next to azdeploy.py. "
            "Make sure you kept the exercise folder intact."
        )
        sys.exit(1)
    os.chdir(script_dir)


def main() -> None:
    _preflight()
    user_object_id = require_az_login()
    require_webpubsub_extension()
    subscription_id = az_query(["az", "account", "show", "--query", "id", "-o", "tsv"])
    if not subscription_id:
        raise RuntimeError("Could not determine the selected Azure subscription.")
    pubsub_name, storage_name = _derived_names(user_object_id)

    while True:
        show_menu(subscription_id, pubsub_name, storage_name)
        choice = input("Please select an option (1-5): ").strip()
        if choice in {"1", "2", "3", "4", "5"}:
            clear_screen()
        try:
            if choice == "1":
                print()
                completed = create_webpubsub(subscription_id, pubsub_name, user_object_id)
            elif choice == "2":
                print()
                completed = create_storage(subscription_id, storage_name, user_object_id)
            elif choice == "3":
                print()
                completed = create_container(subscription_id, pubsub_name, storage_name)
            elif choice == "4":
                print()
                completed = verify_deployment(subscription_id, pubsub_name, storage_name, user_object_id)
            elif choice == "5":
                print("Exiting...")
                clear_screen()
                return
            else:
                print()
                print("Invalid option. Please select 1-5.")
                pause()
                continue
            if not completed:
                print(f"Error: Option {choice} did not complete. Resolve the error above, then retry option {choice}.")
        except (RuntimeError, OSError) as exc:
            print(f"Error: {exc}")
            print(f"Resolve the error above, then retry option {choice}.")
        print()
        pause()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError) as error:
        print(f"Error: {error}")
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        sys.exit(130)
