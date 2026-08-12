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

TOPIC_NAME = "moderation-events"
SUB_FLAGGED = "sub-flagged"
SUB_APPROVED = "sub-approved"
SUB_ALL = "sub-all-events"

DELIVERY_CONFIG = (
    "{deliveryMode:Queue,queue:{receiveLockDurationInSeconds:60,"
    "maxDeliveryCount:10,eventTimeToLive:P1D}}"
)
FLAGGED_FILTER = "{includedEventTypes:['com.contoso.ai.ContentFlagged']}"
APPROVED_FILTER = "{includedEventTypes:['com.contoso.ai.ContentApproved']}"

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
    return f"egns-exercise-{user_hash}"


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


def create_namespace_and_topic(namespace_name: str) -> bool:
    if not create_resource_group():
        return False
    print()
    print(f"Creating Event Grid namespace '{namespace_name}'...")

    existing = az_query(
        ["az", "eventgrid", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "name", "-o", "tsv"]
    )
    if existing:
        print(f"Event Grid namespace already exists: {namespace_name}")
    else:
        if not run_quiet(
            "Create Event Grid namespace",
            [
                "az", "eventgrid", "namespace", "create",
                "--name", namespace_name,
                "--resource-group", rg,
                "--location", location,
                "--sku", "{name:standard,capacity:1}",
            ],
        ):
            return False
        print(f"Event Grid namespace created: {namespace_name}")

    print()
    print(f"Creating namespace topic '{TOPIC_NAME}'...")
    topic_exists = az_query(
        ["az", "eventgrid", "namespace", "topic", "show",
         "--resource-group", rg, "--namespace-name", namespace_name,
         "--name", TOPIC_NAME, "--query", "name", "-o", "tsv"]
    )
    if topic_exists:
        print(f"Namespace topic already exists: {TOPIC_NAME}")
    else:
        if not run_quiet(
            "Create namespace topic",
            [
                "az", "eventgrid", "namespace", "topic", "create",
                "--name", TOPIC_NAME,
                "--namespace-name", namespace_name,
                "--resource-group", rg,
                "--event-retention-in-days", "1",
                "--publisher-type", "Custom",
                "--input-schema", "CloudEventSchemaV1_0",
            ],
        ):
            return False
        print(f"Namespace topic created: {TOPIC_NAME}")
    return True


def _create_subscription(
    namespace_name: str, name: str, filter_config: str | None, description: str
) -> bool:
    exists = az_query(
        ["az", "eventgrid", "namespace", "topic", "event-subscription", "show",
         "--resource-group", rg,
         "--namespace-name", namespace_name,
         "--topic-name", TOPIC_NAME,
         "--name", name, "--query", "name", "-o", "tsv"]
    )
    if exists:
        print(f"Subscription already exists: {name}")
        return True

    argv = [
        "az", "eventgrid", "namespace", "topic", "event-subscription", "create",
        "--name", name,
        "--namespace-name", namespace_name,
        "--resource-group", rg,
        "--topic-name", TOPIC_NAME,
        "--delivery-configuration", DELIVERY_CONFIG,
        "--event-delivery-schema", "CloudEventSchemaV1_0",
    ]
    if filter_config:
        argv += ["--filters-configuration", filter_config]

    if not run_quiet(f"Create subscription {name}", argv):
        return False
    print(f"Subscription created: {name} ({description})")
    return True


def create_event_subscriptions(namespace_name: str) -> bool:
    print("Creating event subscriptions...")

    ns_status = az_query(
        ["az", "eventgrid", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "provisioningState", "-o", "tsv"]
    )
    if ns_status != "Succeeded":
        print(f"Error: Event Grid namespace '{namespace_name}' not found or not ready.")
        print("Please run option 1 first, then try again.")
        return False

    topic_status = az_query(
        ["az", "eventgrid", "namespace", "topic", "show",
         "--resource-group", rg, "--namespace-name", namespace_name,
         "--name", TOPIC_NAME, "--query", "provisioningState", "-o", "tsv"]
    )
    if topic_status != "Succeeded":
        print(f"Error: Namespace topic '{TOPIC_NAME}' not found or not ready.")
        print("Please run option 1 first, then try again.")
        return False

    if not _create_subscription(
        namespace_name, SUB_FLAGGED, FLAGGED_FILTER, "ContentFlagged events only"
    ):
        return False
    if not _create_subscription(
        namespace_name, SUB_APPROVED, APPROVED_FILTER, "ContentApproved events only"
    ):
        return False
    if not _create_subscription(
        namespace_name, SUB_ALL, None, "all events - audit log"
    ):
        return False
    return True


def assign_roles(namespace_name: str, user_object_id: str) -> bool:
    print("Assigning roles...")

    ns_status = az_query(
        ["az", "eventgrid", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "provisioningState", "-o", "tsv"]
    )
    if ns_status != "Succeeded":
        print(f"Error: Event Grid namespace '{namespace_name}' not found or not ready.")
        print("Please run option 1 first, then try again.")
        return False

    user_upn = az_query(
        ["az", "ad", "signed-in-user", "show",
         "--query", "userPrincipalName", "-o", "tsv"]
    )
    if not user_upn:
        print("Error: Unable to retrieve signed-in user information.")
        print("Please ensure you are logged in with 'az login'.")
        return False

    ns_id = az_query(
        ["az", "eventgrid", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "id", "-o", "tsv"]
    )
    if not ns_id:
        print("Error: Unable to retrieve Event Grid namespace ID.")
        return False

    for role in ("EventGrid Data Sender", "EventGrid Data Receiver"):
        exists = az_query(
            ["az", "role", "assignment", "list",
             "--assignee", user_object_id,
             "--scope", ns_id,
             "--role", role,
             "--query", "[0].id", "-o", "tsv"]
        )
        if exists:
            print(f"{role} role already assigned")
        else:
            if not run_quiet(
                f"Assign {role} role",
                [
                    "az", "role", "assignment", "create",
                    "--role", role,
                    "--assignee", user_object_id,
                    "--scope", ns_id,
                ],
            ):
                return False
            print(f"{role} role assigned")

    print()
    print(f"Roles configured for: {user_upn}")
    print("  - EventGrid Data Sender: publish events to the namespace topic")
    print("  - EventGrid Data Receiver: receive events from subscriptions")
    return True


def check_deployment_status(namespace_name: str, user_object_id: str) -> bool:
    print("Checking deployment status...")
    print()

    print(f"Event Grid Namespace ({namespace_name}):")
    ns_status = az_query(
        ["az", "eventgrid", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "provisioningState", "-o", "tsv"]
    )
    if not ns_status:
        print("  Status: Not created")
        return True

    print(f"  Status: {ns_status}")
    if ns_status != "Succeeded":
        print("  WARNING: Namespace is still provisioning. Please wait and try again.")
        return True

    print("  Namespace is ready")
    ns_sku = az_query(
        ["az", "eventgrid", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "sku.name", "-o", "tsv"]
    )
    if ns_sku:
        print(f"  SKU: {ns_sku}")

    topic_status = az_query(
        ["az", "eventgrid", "namespace", "topic", "show",
         "--resource-group", rg, "--namespace-name", namespace_name,
         "--name", TOPIC_NAME, "--query", "provisioningState", "-o", "tsv"]
    )
    if topic_status:
        print(f"  Topic {TOPIC_NAME}: {topic_status}")
    else:
        print(f"  WARNING: Topic not created: {TOPIC_NAME}")

    ns_id = az_query(
        ["az", "eventgrid", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "id", "-o", "tsv"]
    )
    user_upn = az_query(
        ["az", "ad", "signed-in-user", "show",
         "--query", "userPrincipalName", "-o", "tsv"]
    )

    for role in ("EventGrid Data Sender", "EventGrid Data Receiver"):
        exists = az_query(
            ["az", "role", "assignment", "list",
             "--assignee", user_object_id,
             "--scope", ns_id,
             "--role", role,
             "--query", "[0].id", "-o", "tsv"]
        )
        if exists:
            print(f"  Role assigned: {user_upn} ({role})")
        else:
            print(f"  WARNING: {role} role not assigned")

    print()
    print("Event Subscriptions:")
    for sub in (SUB_FLAGGED, SUB_APPROVED, SUB_ALL):
        status = az_query(
            ["az", "eventgrid", "namespace", "topic", "event-subscription", "show",
             "--resource-group", rg,
             "--namespace-name", namespace_name,
             "--topic-name", TOPIC_NAME,
             "--name", sub, "--query", "provisioningState", "-o", "tsv"]
        )
        print(f"  {sub}: {status if status else 'Not created'}")
    return True


def retrieve_connection_info(namespace_name: str, user_object_id: str) -> bool:
    print("Retrieving connection information...")

    ns_status = az_query(
        ["az", "eventgrid", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "provisioningState", "-o", "tsv"]
    )
    if ns_status != "Succeeded":
        print(f"Error: Event Grid namespace '{namespace_name}' not found or not ready.")
        print("Please run option 1 first, then try again.")
        return False

    ns_id = az_query(
        ["az", "eventgrid", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "id", "-o", "tsv"]
    )
    sender_role = az_query(
        ["az", "role", "assignment", "list",
         "--assignee", user_object_id,
         "--scope", ns_id,
         "--role", "EventGrid Data Sender",
         "--query", "[0].id", "-o", "tsv"]
    )
    receiver_role = az_query(
        ["az", "role", "assignment", "list",
         "--assignee", user_object_id,
         "--scope", ns_id,
         "--role", "EventGrid Data Receiver",
         "--query", "[0].id", "-o", "tsv"]
    )
    if not sender_role or not receiver_role:
        print("Error: Required roles not assigned.")
        print("Please run option 3 to assign roles, then try again.")
        return False

    ns_hostname = az_query(
        ["az", "eventgrid", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "topicsConfiguration.hostname", "-o", "tsv"]
    )
    if not ns_hostname:
        ns_hostname = f"{namespace_name}.{location}-1.eventgrid.azure.net"

    write_env_files({
        "RESOURCE_GROUP": rg,
        "NAMESPACE_NAME": namespace_name,
        "EVENTGRID_TOPIC_NAME": TOPIC_NAME,
        "EVENTGRID_ENDPOINT": f"https://{ns_hostname}",
    })
    print()
    print("Event Grid Connection Information")
    print("===========================================================")
    print(f"Namespace endpoint: https://{ns_hostname}")
    print(f"Topic name: {TOPIC_NAME}")
    print("Authentication: Microsoft Entra ID (DefaultAzureCredential)")
    print()
    print("Environment variables saved to .env and .env.ps1")
    return True


def show_menu(namespace_name: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    Event Grid Exercise - Deployment Script")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"Namespace: {namespace_name}")
    print(f"Topic: {TOPIC_NAME}")
    print("=====================================================================")
    print("1. Create Event Grid namespace and topic")
    print("2. Create event subscriptions")
    print("3. Assign user roles")
    print("4. Retrieve connection info")
    print("5. Check deployment status")
    print("6. Exit")
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
    namespace_name = _derived_names(user_object_id)

    while True:
        show_menu(namespace_name)
        choice = input("Please select an option (1-6): ").strip()
        if choice in {"1", "2", "3", "4", "5", "6"}:
            clear_screen()

        if choice == "1":
            print()
            create_namespace_and_topic(namespace_name)
            print()
            pause()
        elif choice == "2":
            print()
            create_event_subscriptions(namespace_name)
            print()
            pause()
        elif choice == "3":
            print()
            assign_roles(namespace_name, user_object_id)
            print()
            pause()
        elif choice == "4":
            print()
            retrieve_connection_info(namespace_name, user_object_id)
            print()
            pause()
        elif choice == "5":
            print()
            check_deployment_status(namespace_name, user_object_id)
            print()
            pause()
        elif choice == "6":
            print("Exiting...")
            clear_screen()
            sys.exit(0)
        else:
            print()
            print("Invalid option. Please select 1-6.")
            print()
            pause()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
