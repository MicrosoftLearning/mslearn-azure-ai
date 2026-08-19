import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

API_VERSION = "2025-04-01"
SPEC_PATH = Path(__file__).with_name("sitecontainers-spec.json")


def resolve_az() -> str:
    az = shutil.which("az")
    if not az:
        print("Error: 'az' not found on PATH. Install Azure CLI and retry.")
        sys.exit(1)
    return az


def run_az(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [resolve_az(), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def require_environment() -> tuple[str, str, str]:
    subscription_id = run_az(
        ["account", "show", "--query", "id", "--output", "tsv"]
    )
    if subscription_id.returncode != 0 or not subscription_id.stdout.strip():
        print("Error: Not authenticated with Azure. Please run: az login")
        sys.exit(1)

    resource_group = os.getenv("RESOURCE_GROUP", "").strip()
    app_name = os.getenv("APP_NAME", "").strip()
    if not resource_group or not app_name:
        print(
            "Error: RESOURCE_GROUP and APP_NAME are not set. "
            "Source .env or dot-source .env.ps1 and retry."
        )
        sys.exit(1)
    return subscription_id.stdout.strip(), resource_group, app_name


def sitecontainers_uri(
    subscription_id: str,
    resource_group: str,
    app_name: str,
    container_name: str | None = None,
) -> str:
    uri = (
        "https://management.azure.com/subscriptions/"
        f"{quote(subscription_id, safe='')}/resourceGroups/"
        f"{quote(resource_group, safe='')}/providers/Microsoft.Web/sites/"
        f"{quote(app_name, safe='')}/sitecontainers"
    )
    if container_name:
        uri += f"/{quote(container_name, safe='')}"
    return f"{uri}?api-version={API_VERSION}"


def load_specification() -> list[dict]:
    if not SPEC_PATH.is_file():
        print(
            "Error: sitecontainers-spec.json was not found. "
            "Run azdeploy.py option 2 and retry."
        )
        sys.exit(1)
    try:
        specification = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: Could not read sitecontainers-spec.json: {exc}")
        sys.exit(1)

    if not isinstance(specification, list) or not specification:
        print("Error: sitecontainers-spec.json must contain a non-empty JSON array.")
        sys.exit(1)
    return specification


def apply_specification() -> None:
    subscription_id, resource_group, app_name = require_environment()
    specification = load_specification()

    for container in specification:
        name = container.get("name")
        properties = container.get("properties")
        if not isinstance(name, str) or not isinstance(properties, dict):
            print("Error: Each container requires a name and properties object.")
            sys.exit(1)

        print(f"Applying site container '{name}'...")
        result = run_az(
            [
                "rest",
                "--method", "put",
                "--uri", sitecontainers_uri(
                    subscription_id,
                    resource_group,
                    app_name,
                    name,
                ),
                "--body", json.dumps({"properties": properties}),
                "--output", "none",
            ]
        )
        if result.returncode != 0:
            print(f"Error: Failed to apply site container '{name}'.")
            output = (result.stdout or "") + (result.stderr or "")
            if output.strip():
                print(output.rstrip())
            sys.exit(result.returncode)
        print(f"Site container applied: {name}")


def list_sitecontainers() -> None:
    subscription_id, resource_group, app_name = require_environment()
    result = run_az(
        [
            "rest",
            "--method", "get",
            "--uri", sitecontainers_uri(
                subscription_id,
                resource_group,
                app_name,
            ),
            "--output", "json",
        ]
    )
    if result.returncode != 0:
        print("Error: Failed to retrieve site containers.")
        output = (result.stdout or "") + (result.stderr or "")
        if output.strip():
            print(output.rstrip())
        sys.exit(result.returncode)

    response = json.loads(result.stdout)
    containers = response.get("value", [])
    if not containers:
        print("No site containers are configured.")
        return

    print(f"{'NAME':<20} {'ROLE':<10} {'PORT':<8} IMAGE")
    for container in containers:
        properties = container.get("properties", {})
        role = "Main" if properties.get("isMain") else "Sidecar"
        print(
            f"{container.get('name', ''):<20} "
            f"{role:<10} "
            f"{str(properties.get('targetPort', '')):<8} "
            f"{properties.get('image', '')}"
        )


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"apply", "list"}:
        print("Usage: python sitecontainers.py <apply|list>")
        sys.exit(2)
    if sys.argv[1] == "apply":
        apply_specification()
    else:
        list_sitecontainers()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
