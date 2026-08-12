# =============================================================================
# Change the values of these variables as needed.
# =============================================================================

# rg = "<your-resource-group-name>"  # Resource Group name
# location = "<your-azure-region>"   # Azure region for the resources

rg = "rg-exercises"  # Resource Group name
location = "eastus2"  # Azure region for the resources

# =============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# =============================================================================

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

QUEUE_NAME = "inference-requests"
TOPIC_NAME = "inference-results"
NOTIFICATIONS_SUBSCRIPTION = "notifications"
HIGH_PRIORITY_SUBSCRIPTION = "high-priority"
HIGH_PRIORITY_RULE = "high-priority-filter"
HIGH_PRIORITY_FILTER = "priority = 'high'"

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
    return f"sbns-exercise-{user_hash}"


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


def create_servicebus_namespace(namespace_name: str) -> bool:
    if not create_resource_group():
        return False
    print()
    print(f"Creating Service Bus namespace '{namespace_name}'...")

    existing = az_query(
        ["az", "servicebus", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "name", "-o", "tsv"]
    )
    if existing:
        print(f"Service Bus namespace already exists: {namespace_name}")
    else:
        if not run_quiet(
            "Create Service Bus namespace",
            [
                "az", "servicebus", "namespace", "create",
                "--name", namespace_name,
                "--resource-group", rg,
                "--location", location,
                "--sku", "Standard",
            ],
        ):
            return False
        print(f"Service Bus namespace created: {namespace_name}")

    print()
    print("Use option 2 to create messaging entities.")
    return True


def create_messaging_entities(namespace_name: str) -> bool:
    print("Creating messaging entities...")

    status = az_query(
        ["az", "servicebus", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "provisioningState", "-o", "tsv"]
    )
    if not status:
        print(f"Error: Service Bus namespace '{namespace_name}' not found.")
        print("Please run option 1 to create the namespace, then try again.")
        return False
    if status != "Succeeded":
        print(f"Error: Service Bus namespace is not ready (current state: {status}).")
        print("Please wait for deployment to complete. Use option 4 to check status.")
        return False

    queue_exists = az_query(
        ["az", "servicebus", "queue", "show",
         "--name", QUEUE_NAME, "--namespace-name", namespace_name,
         "--resource-group", rg, "--query", "name", "-o", "tsv"]
    )
    if queue_exists:
        print(f"Queue already exists: {QUEUE_NAME}")
    else:
        if not run_quiet(
            "Create queue",
            [
                "az", "servicebus", "queue", "create",
                "--name", QUEUE_NAME,
                "--namespace-name", namespace_name,
                "--resource-group", rg,
                "--max-delivery-count", "5",
                "--enable-dead-lettering-on-message-expiration", "true",
            ],
        ):
            return False
        print(f"Queue created: {QUEUE_NAME}")

    topic_exists = az_query(
        ["az", "servicebus", "topic", "show",
         "--name", TOPIC_NAME, "--namespace-name", namespace_name,
         "--resource-group", rg, "--query", "name", "-o", "tsv"]
    )
    if topic_exists:
        print(f"Topic already exists: {TOPIC_NAME}")
    else:
        if not run_quiet(
            "Create topic",
            [
                "az", "servicebus", "topic", "create",
                "--name", TOPIC_NAME,
                "--namespace-name", namespace_name,
                "--resource-group", rg,
            ],
        ):
            return False
        print(f"Topic created: {TOPIC_NAME}")

    notif_exists = az_query(
        ["az", "servicebus", "topic", "subscription", "show",
         "--name", NOTIFICATIONS_SUBSCRIPTION,
         "--topic-name", TOPIC_NAME,
         "--namespace-name", namespace_name,
         "--resource-group", rg, "--query", "name", "-o", "tsv"]
    )
    if notif_exists:
        print(f"Subscription already exists: {NOTIFICATIONS_SUBSCRIPTION}")
    else:
        if not run_quiet(
            "Create notifications subscription",
            [
                "az", "servicebus", "topic", "subscription", "create",
                "--name", NOTIFICATIONS_SUBSCRIPTION,
                "--topic-name", TOPIC_NAME,
                "--namespace-name", namespace_name,
                "--resource-group", rg,
            ],
        ):
            return False
        print(f"Subscription created: {NOTIFICATIONS_SUBSCRIPTION}")

    hp_exists = az_query(
        ["az", "servicebus", "topic", "subscription", "show",
         "--name", HIGH_PRIORITY_SUBSCRIPTION,
         "--topic-name", TOPIC_NAME,
         "--namespace-name", namespace_name,
         "--resource-group", rg, "--query", "name", "-o", "tsv"]
    )
    if hp_exists:
        print(f"Subscription already exists: {HIGH_PRIORITY_SUBSCRIPTION}")
    else:
        if not run_quiet(
            "Create high-priority subscription",
            [
                "az", "servicebus", "topic", "subscription", "create",
                "--name", HIGH_PRIORITY_SUBSCRIPTION,
                "--topic-name", TOPIC_NAME,
                "--namespace-name", namespace_name,
                "--resource-group", rg,
            ],
        ):
            return False
        print(f"Subscription created: {HIGH_PRIORITY_SUBSCRIPTION}")

    filter_exists = az_query(
        ["az", "servicebus", "topic", "subscription", "rule", "show",
         "--name", HIGH_PRIORITY_RULE,
         "--subscription-name", HIGH_PRIORITY_SUBSCRIPTION,
         "--topic-name", TOPIC_NAME,
         "--namespace-name", namespace_name,
         "--resource-group", rg, "--query", "name", "-o", "tsv"]
    )
    if filter_exists:
        print(f"SQL filter already exists: {HIGH_PRIORITY_RULE}")
    else:
        # Delete the default $Default rule so the SQL filter is the only match.
        # The rule may not exist if the subscription was pre-created, so allow this to fail quietly.
        subprocess.run(
            [
                _resolve_exe("az"), "servicebus", "topic", "subscription", "rule", "delete",
                "--name", "$Default",
                "--subscription-name", HIGH_PRIORITY_SUBSCRIPTION,
                "--topic-name", TOPIC_NAME,
                "--namespace-name", namespace_name,
                "--resource-group", rg,
            ],
            capture_output=True, text=True, check=False,
        )

        if not run_quiet(
            "Create SQL filter",
            [
                "az", "servicebus", "topic", "subscription", "rule", "create",
                "--name", HIGH_PRIORITY_RULE,
                "--subscription-name", HIGH_PRIORITY_SUBSCRIPTION,
                "--topic-name", TOPIC_NAME,
                "--namespace-name", namespace_name,
                "--resource-group", rg,
                "--filter-sql-expression", HIGH_PRIORITY_FILTER,
            ],
        ):
            return False
        print(f"SQL filter created: {HIGH_PRIORITY_RULE} ({HIGH_PRIORITY_FILTER})")

    print()
    print("Use option 3 to assign the data plane role.")
    return True


def assign_role(namespace_name: str, user_object_id: str) -> bool:
    print("Assigning Azure Service Bus Data Owner role...")

    status = az_query(
        ["az", "servicebus", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "provisioningState", "-o", "tsv"]
    )
    if not status:
        print(f"Error: Service Bus namespace '{namespace_name}' not found.")
        print("Please run option 1 to create the namespace, then try again.")
        return False
    if status != "Succeeded":
        print(f"Error: Service Bus namespace is not ready (current state: {status}).")
        print("Please wait for deployment to complete. Use option 4 to check status.")
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
        ["az", "servicebus", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "id", "-o", "tsv"]
    )
    if not ns_id:
        print("Error: Unable to retrieve Service Bus namespace ID.")
        return False

    role_exists = az_query(
        ["az", "role", "assignment", "list",
         "--assignee", user_object_id,
         "--scope", ns_id,
         "--role", "Azure Service Bus Data Owner",
         "--query", "[0].id", "-o", "tsv"]
    )
    if role_exists:
        print("Azure Service Bus Data Owner role already assigned")
    else:
        if not run_quiet(
            "Assign Azure Service Bus Data Owner role",
            [
                "az", "role", "assignment", "create",
                "--role", "Azure Service Bus Data Owner",
                "--assignee", user_object_id,
                "--scope", ns_id,
            ],
        ):
            return False
        print("Azure Service Bus Data Owner role assigned")

    print()
    print(f"Role configured for: {user_upn}")
    print("  - Azure Service Bus Data Owner: send, receive, and manage entities")
    return True


def check_deployment_status(namespace_name: str, user_object_id: str) -> bool:
    print("Checking deployment status...")
    print()

    print(f"Service Bus Namespace ({namespace_name}):")
    ns_status = az_query(
        ["az", "servicebus", "namespace", "show",
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
        ["az", "servicebus", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "sku.name", "-o", "tsv"]
    )
    if ns_sku:
        print(f"  SKU: {ns_sku}")
    ns_endpoint = az_query(
        ["az", "servicebus", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "serviceBusEndpoint", "-o", "tsv"]
    )
    if ns_endpoint:
        print(f"  Endpoint: {ns_endpoint}")

    user_upn = az_query(
        ["az", "ad", "signed-in-user", "show",
         "--query", "userPrincipalName", "-o", "tsv"]
    )
    ns_id = az_query(
        ["az", "servicebus", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "id", "-o", "tsv"]
    )
    role_exists = az_query(
        ["az", "role", "assignment", "list",
         "--assignee", user_object_id,
         "--scope", ns_id,
         "--role", "Azure Service Bus Data Owner",
         "--query", "[0].id", "-o", "tsv"]
    )
    if role_exists:
        print(f"  Role assigned: {user_upn} (Azure Service Bus Data Owner)")
    else:
        print("  WARNING: Role not assigned")

    print()
    print("Messaging Entities:")

    queue = az_query(
        ["az", "servicebus", "queue", "show",
         "--name", QUEUE_NAME, "--namespace-name", namespace_name,
         "--resource-group", rg, "--query", "name", "-o", "tsv"]
    )
    print(f"  Queue {QUEUE_NAME}: {'Created' if queue else 'Not created'}")

    topic = az_query(
        ["az", "servicebus", "topic", "show",
         "--name", TOPIC_NAME, "--namespace-name", namespace_name,
         "--resource-group", rg, "--query", "name", "-o", "tsv"]
    )
    print(f"  Topic {TOPIC_NAME}: {'Created' if topic else 'Not created'}")

    if topic:
        notif = az_query(
            ["az", "servicebus", "topic", "subscription", "show",
             "--name", NOTIFICATIONS_SUBSCRIPTION,
             "--topic-name", TOPIC_NAME,
             "--namespace-name", namespace_name,
             "--resource-group", rg, "--query", "name", "-o", "tsv"]
        )
        print(f"  Subscription {NOTIFICATIONS_SUBSCRIPTION}: {'Created' if notif else 'Not created'}")

        hp = az_query(
            ["az", "servicebus", "topic", "subscription", "show",
             "--name", HIGH_PRIORITY_SUBSCRIPTION,
             "--topic-name", TOPIC_NAME,
             "--namespace-name", namespace_name,
             "--resource-group", rg, "--query", "name", "-o", "tsv"]
        )
        print(f"  Subscription {HIGH_PRIORITY_SUBSCRIPTION}: {'Created' if hp else 'Not created'}")

        if hp:
            filter_ = az_query(
                ["az", "servicebus", "topic", "subscription", "rule", "show",
                 "--name", HIGH_PRIORITY_RULE,
                 "--subscription-name", HIGH_PRIORITY_SUBSCRIPTION,
                 "--topic-name", TOPIC_NAME,
                 "--namespace-name", namespace_name,
                 "--resource-group", rg, "--query", "name", "-o", "tsv"]
            )
            print(f"  SQL filter {HIGH_PRIORITY_RULE}: {'Created' if filter_ else 'Not created'}")
    return True


def retrieve_connection_info(namespace_name: str, user_object_id: str) -> bool:
    print("Retrieving connection information...")

    existing = az_query(
        ["az", "servicebus", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "name", "-o", "tsv"]
    )
    if not existing:
        print(f"Error: Service Bus namespace '{namespace_name}' not found.")
        print("Please run option 1 to create the namespace, then try again.")
        return False

    ns_id = az_query(
        ["az", "servicebus", "namespace", "show",
         "--resource-group", rg, "--name", namespace_name,
         "--query", "id", "-o", "tsv"]
    )
    role_exists = az_query(
        ["az", "role", "assignment", "list",
         "--assignee", user_object_id,
         "--scope", ns_id,
         "--role", "Azure Service Bus Data Owner",
         "--query", "[0].id", "-o", "tsv"]
    )
    if not role_exists:
        print("Error: Azure Service Bus Data Owner role not assigned.")
        print("Please run option 3 to assign the role, then try again.")
        return False

    fqdn = f"{namespace_name}.servicebus.windows.net"

    write_env_files({"SERVICE_BUS_FQDN": fqdn})
    print()
    print("Service Bus Connection Information")
    print("===========================================================")
    print(f"FQDN: {fqdn}")
    print("Authentication: Microsoft Entra ID (DefaultAzureCredential)")
    print()
    print("Environment variables saved to .env and .env.ps1")
    return True


def show_menu(namespace_name: str) -> None:
    clear_screen()
    print("=====================================================================")
    print("    Service Bus Messaging Exercise - Deployment Script")
    print("=====================================================================")
    print(f"Resource Group: {rg}")
    print(f"Location: {location}")
    print(f"Namespace: {namespace_name}")
    print("=====================================================================")
    print("1. Create Service Bus namespace")
    print("2. Create messaging entities")
    print("3. Assign role")
    print("4. Check deployment status")
    print("5. Retrieve connection info")
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
            create_servicebus_namespace(namespace_name)
            print()
            pause()
        elif choice == "2":
            print()
            create_messaging_entities(namespace_name)
            print()
            pause()
        elif choice == "3":
            print()
            assign_role(namespace_name, user_object_id)
            print()
            pause()
        elif choice == "4":
            print()
            check_deployment_status(namespace_name, user_object_id)
            print()
            pause()
        elif choice == "5":
            print()
            retrieve_connection_info(namespace_name, user_object_id)
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
