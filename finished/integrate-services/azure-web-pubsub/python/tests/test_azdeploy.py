import contextlib
import importlib.util
import io
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("webpubsub_azdeploy", ROOT / "azdeploy.py")
deploy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = deploy
spec.loader.exec_module(deploy)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.subscription_id = "subscription"
        self.user_object_id = "object-id"
        self.pubsub_name, self.storage_name = deploy._derived_names(self.user_object_id)
        self.resources = (self.subscription_id, self.pubsub_name, self.storage_name)
        self.verification_args = (*self.resources, self.user_object_id)
        self.pubsub = {"properties": {
            "provisioningState": "Succeeded", "disableLocalAuth": True,
            "hostName": "example.webpubsub.azure.com",
        }}
        self.storage = {"properties": {
            "provisioningState": "Succeeded", "allowSharedKeyAccess": False,
            "allowBlobPublicAccess": False, "supportsHttpsTrafficOnly": True,
            "minimumTlsVersion": "TLS1_2",
            "primaryEndpoints": {"blob": "https://example.blob.core.windows.net/"},
        }}
        deploy._EXE_CACHE.clear()
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.responses = {
            "webpubsub_role": "1", "storage_role": "1", "token": '{"token":"test-only"}',
            "container": "true", "blobs": "[]",
        }

    def ready_query(self, argv, **kwargs):
        if argv[:4] == ["az", "role", "assignment", "list"]:
            role = argv[argv.index("--role") + 1]
            key = "webpubsub_role" if role == deploy.WEBPUBSUB_ROLE else "storage_role"
        elif argv[:2] == ["az", "rest"]:
            key = "token"
        elif argv[:4] == ["az", "storage", "container", "exists"]:
            key = "container"
        elif argv[:4] == ["az", "storage", "blob", "list"]:
            key = "blobs"
        else:
            self.fail(f"Unexpected verification command: {argv}")
        result = self.responses[key]
        if isinstance(result, Exception):
            raise result
        return result

    def test_names_and_resource_scopes(self):
        self.assertRegex(self.pubsub_name, r"^wps-investigation-[a-f0-9]{8}$")
        self.assertRegex(self.storage_name, r"^stinvestigation[a-f0-9]{8}$")
        self.assertEqual(self.pubsub_name[-8:], self.storage_name[-8:])
        scope = deploy._resource_id(
            self.subscription_id, "Microsoft.Storage/storageAccounts", self.storage_name,
        )
        self.assertEqual(
            scope,
            f"/subscriptions/subscription/resourceGroups/{deploy.rg}"
            f"/providers/Microsoft.Storage/storageAccounts/{self.storage_name}",
        )

    def test_script_is_ascii_and_syntax_is_valid(self):
        source = (ROOT / "azdeploy.py").read_bytes()
        self.assertTrue(source.isascii())
        compile(source, str(ROOT / "azdeploy.py"), "exec")
        self.assertFalse(source.startswith(b"#!"))
        self.assertNotIn(b"dataclass", source)
        self.assertNotIn(b"class Context", source)

    def test_missing_cli_is_actionable(self):
        with patch("shutil.which", return_value=None):
            with self.assertRaises(SystemExit) as exited:
                deploy.az_query(["az", "account", "show"])
        self.assertEqual(exited.exception.code, 1)

    def test_executable_resolution_and_explicit_subprocess_check(self):
        result = subprocess.CompletedProcess([], 0, "test\n", "")
        with patch("shutil.which", return_value="/resolved/az.cmd"):
            with patch("subprocess.run", return_value=result) as run:
                self.assertEqual(
                    deploy.az_query(["az", "account", "show", "--query", "id", "-o", "tsv"]),
                    "test",
                )
        self.assertEqual(run.call_args.args[0][0], "/resolved/az.cmd")
        self.assertIs(run.call_args.kwargs["check"], False)
        self.assertNotIn("--only-show-errors", run.call_args.args[0])

    def test_run_quiet_returns_success_and_reports_failures(self):
        with patch("shutil.which", return_value="/az"):
            result = subprocess.CompletedProcess([], 0, "hidden output", "")
            with patch("subprocess.run", return_value=result) as run:
                self.assertTrue(deploy.run_quiet("Create resource", ["az", "resource", "create"]))
                self.assertIs(run.call_args.kwargs["check"], False)
            result = subprocess.CompletedProcess([], 2, "details\n", "permission denied\n")
            with patch("subprocess.run", return_value=result):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertFalse(deploy.run_quiet("Create resource", ["az", "resource", "create"]))
        self.assertIn("Error: Create resource failed (exit code 2).", output.getvalue())
        self.assertIn("permission denied", output.getvalue())
        self.assertIn("details", output.getvalue())

    def test_only_not_found_is_treated_as_absence(self):
        with patch("shutil.which", return_value="/az"):
            for error in ("(AuthorizationFailed)", "network timeout", "Forbidden"):
                result = subprocess.CompletedProcess([], 1, "", error)
                with patch("subprocess.run", return_value=result):
                    with self.assertRaises(RuntimeError):
                        deploy.az_query(["az", "resource", "show"], missing_ok=True)
            result = subprocess.CompletedProcess([], 1, "", "(ResourceNotFound)")
            with patch("subprocess.run", return_value=result):
                self.assertEqual(deploy.az_query(["az", "resource", "show"], missing_ok=True), "")

    def test_resource_query_parses_json_and_reports_invalid_json(self):
        with patch.object(deploy, "az_query", return_value='{"properties":{"provisioningState":"Succeeded"}}'):
            resource = deploy.show_resource(
                self.subscription_id, "Microsoft.SignalRService/WebPubSub", self.pubsub_name,
            )
        self.assertEqual(resource["properties"]["provisioningState"], "Succeeded")
        with patch.object(deploy, "az_query", return_value="not json"):
            with self.assertRaisesRegex(RuntimeError, "invalid resource JSON"):
                deploy.show_resource(
                    self.subscription_id, "Microsoft.SignalRService/WebPubSub", self.pubsub_name,
                )

    def test_preflight_switches_from_wrong_cwd(self):
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            deploy._preflight()
            self.assertEqual(Path.cwd(), ROOT)

    def test_missing_anchor_has_friendly_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(deploy, "__file__", str(Path(directory) / "azdeploy.py")):
                with self.assertRaises(SystemExit) as exited:
                    deploy._preflight()
        self.assertEqual(exited.exception.code, 1)

    def test_preflight_without_login(self):
        with patch.object(deploy, "az_query", side_effect=RuntimeError("Please run 'az login'")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(SystemExit) as exited:
                    deploy.require_az_login()
        self.assertEqual(exited.exception.code, 1)
        self.assertIn("Error: Not authenticated with Azure. Please run: az login", output.getvalue())

    def test_authentication_query_permission_failure_is_not_reported_as_logged_out(self):
        with patch.object(deploy, "az_query", side_effect=RuntimeError("Graph permission denied")):
            with self.assertRaisesRegex(RuntimeError, "Graph permission denied"):
                deploy.require_az_login()

    def test_entry_point_without_login_exits_one(self):
        response = subprocess.CompletedProcess([], 1, "", "Please run: az login")
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        with patch("shutil.which", return_value="/test/az"), patch("subprocess.run", return_value=response):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(SystemExit) as exited:
                    runpy.run_path(str(ROOT / "azdeploy.py"), run_name="__main__")
        self.assertEqual(exited.exception.code, 1)
        self.assertIn("Error: Not authenticated with Azure. Please run: az login", output.getvalue())

    def test_provisioning_is_blocking_and_disables_key_auth(self):
        with patch.object(deploy, "ready_for_create", return_value=True):
            with patch.object(deploy, "create_resource_group", return_value=True):
                with patch.object(
                    deploy, "az_query",
                    side_effect=lambda argv: "Registered" if argv[1:3] == ["provider", "show"] else "1",
                ):
                    with patch.object(deploy, "run_quiet", return_value=True) as action:
                        self.assertTrue(deploy.create_webpubsub(
                            self.subscription_id, self.pubsub_name, self.user_object_id,
                        ))
                        pubsub_commands = [call.args[1] for call in action.call_args_list]
                        self.assertFalse(any("storage" in command for command in pubsub_commands))
                        action.reset_mock()
                        self.assertTrue(deploy.create_storage(
                            self.subscription_id, self.storage_name, self.user_object_id,
                        ))
                        storage_commands = [call.args[1] for call in action.call_args_list]
                        self.assertFalse(any("webpubsub" in command for command in storage_commands))
        commands = pubsub_commands + storage_commands
        self.assertFalse(any("--no-wait" in command for command in commands))
        self.assertFalse(any(command[:3] == ["az", "provider", "register"] for command in commands))
        pubsub = next(command for command in commands if command[:3] == ["az", "webpubsub", "create"])
        self.assertIn("Standard_S1", pubsub)
        storage = next(command for command in commands if command[:4] == ["az", "storage", "account", "create"])
        self.assertEqual(storage[storage.index("--allow-shared-key-access") + 1], "false")
        self.assertTrue(any("properties.disableLocalAuth=true" in command for command in commands))

    def test_resource_creation_failure_is_isolated_and_has_its_own_retry_option(self):
        steps = (
            (deploy.create_webpubsub, self.pubsub_name, 1),
            (deploy.create_storage, self.storage_name, 2),
        )
        for function, name, option in steps:
            with self.subTest(option=option):
                with patch.object(deploy, "create_resource_group", return_value=True), patch.object(
                    deploy, "check_provider_registration", return_value=True,
                ):
                    with patch.object(deploy, "ready_for_create", return_value=True):
                        with patch.object(deploy, "run_quiet", return_value=False) as action:
                            with patch.object(deploy, "assign_role") as role:
                                with contextlib.redirect_stdout(io.StringIO()) as output:
                                    self.assertFalse(function(self.subscription_id, name, self.user_object_id))
                self.assertEqual(action.call_count, 1)
                self.assertIn(f"Retry option {option}", output.getvalue())
                role.assert_not_called()

    def test_role_retry_does_not_recreate_succeeded_resource(self):
        steps = (
            (deploy.create_webpubsub, self.pubsub_name, "Microsoft.SignalRService/WebPubSub", deploy.WEBPUBSUB_ROLE),
            (deploy.create_storage, self.storage_name, "Microsoft.Storage/storageAccounts", deploy.STORAGE_ROLE),
        )
        for function, name, resource_type, role_name in steps:
            with self.subTest(resource=name):
                with patch.object(deploy, "create_resource_group", return_value=True), patch.object(
                    deploy, "check_provider_registration", return_value=True,
                ):
                    with patch.object(deploy, "ready_for_create", return_value=False):
                        with patch.object(deploy, "run_quiet", return_value=True) as action:
                            with patch.object(deploy, "assign_role", side_effect=[False, True]) as role:
                                self.assertFalse(function(self.subscription_id, name, self.user_object_id))
                                self.assertTrue(function(self.subscription_id, name, self.user_object_id))
                role.assert_called_with(
                    self.subscription_id, resource_type, name, self.user_object_id, role_name,
                )
                self.assertFalse(any("create" in call.args[1] for call in action.call_args_list))

    def test_provider_check_reports_progress_before_query_and_never_registers(self):
        for namespace in ("Microsoft.SignalRService", "Microsoft.Storage"):
            with self.subTest(namespace=namespace):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    def registered(argv):
                        self.assertIn(f"Checking resource provider registration: {namespace}", output.getvalue())
                        return "Registered"

                    with patch.object(deploy, "az_query", side_effect=registered) as query:
                        with patch.object(deploy, "run_quiet") as action:
                            self.assertTrue(deploy.check_provider_registration(self.subscription_id, namespace))
                query.assert_called_once_with([
                    "az", "provider", "show", "--namespace", namespace,
                    "--subscription", self.subscription_id, "--query", "registrationState", "-o", "tsv",
                ])
                action.assert_not_called()
                self.assertIn(f"Resource provider registered: {namespace}", output.getvalue())

    def test_unregistered_or_pending_provider_stops_each_resource_step(self):
        for function, name, namespace in (
            (deploy.create_webpubsub, self.pubsub_name, "Microsoft.SignalRService"),
            (deploy.create_storage, self.storage_name, "Microsoft.Storage"),
        ):
            for state in ("NotRegistered", "Registering", "Unregistering", ""):
                with self.subTest(namespace=namespace, state=state):
                    with patch.object(deploy, "az_query", return_value=state) as query:
                        with patch.object(deploy, "run_quiet") as action:
                            with patch.object(deploy, "create_resource_group") as group, patch("time.sleep") as sleep:
                                with contextlib.redirect_stdout(io.StringIO()) as output:
                                    self.assertFalse(function(self.subscription_id, name, self.user_object_id))
                    query.assert_called_once()
                    self.assertEqual(query.call_args.args[0][:3], ["az", "provider", "show"])
                    action.assert_not_called()
                    group.assert_not_called()
                    sleep.assert_not_called()
                    self.assertIn(namespace, output.getvalue())
                    self.assertIn("Error:", output.getvalue())
                    if state:
                        self.assertIn(f"current state: {state}", output.getvalue())
                    if state == "Registering":
                        self.assertIn("Registration is in progress", output.getvalue())

    def test_provider_query_error_is_not_treated_as_missing_registration(self):
        with patch.object(deploy, "az_query", side_effect=RuntimeError("Provider query permission denied")):
            with patch.object(deploy, "run_quiet") as action:
                with self.assertRaisesRegex(RuntimeError, "Provider query permission denied"):
                    deploy.check_provider_registration(self.subscription_id, "Microsoft.Storage")
        action.assert_not_called()

    def test_extension_is_required_not_silently_installed(self):
        with patch.object(deploy, "az_query", return_value="other-extension") as query:
            with self.assertRaisesRegex(RuntimeError, "az extension add --name webpubsub"):
                deploy.require_webpubsub_extension()
        self.assertEqual(query.call_count, 1)
        with patch.object(deploy, "az_query", return_value="other\nwebpubsub\n"):
            deploy.require_webpubsub_extension()

    def test_creation_state_branches_and_deletion_wait(self):
        args = (self.subscription_id, "Microsoft.SignalRService/WebPubSub", self.pubsub_name)
        with patch.object(deploy, "show_resource", return_value=None):
            self.assertTrue(deploy.ready_for_create(*args))
        with patch.object(deploy, "show_resource", return_value={"properties": {"provisioningState": "Succeeded"}}):
            self.assertFalse(deploy.ready_for_create(*args))
        with patch.object(deploy, "show_resource", return_value={"properties": {"provisioningState": "Updating"}}):
            with self.assertRaisesRegex(RuntimeError, "not ready"):
                deploy.ready_for_create(*args)
        failed = {"properties": {"provisioningState": "Failed"}}
        deleting = {"properties": {"provisioningState": "Deleting"}}
        with patch.object(deploy, "show_resource", side_effect=[failed, deleting, None]):
            with patch.object(deploy, "run_quiet", return_value=True) as action, patch("time.sleep") as sleep:
                self.assertTrue(deploy.ready_for_create(*args))
        self.assertEqual(action.call_count, 1)
        self.assertIn("delete", action.call_args.args[1])
        sleep.assert_called_once_with(5)

    def test_failed_delete_does_not_fall_through_to_create(self):
        with patch.object(deploy, "show_resource", return_value={"properties": {"provisioningState": "Failed"}}):
            with patch.object(deploy, "run_quiet", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "could not be deleted"):
                    deploy.ready_for_create(
                        self.subscription_id, "Microsoft.Storage/storageAccounts", self.storage_name,
                    )

    def test_failed_storage_deletion_points_to_option_two(self):
        with patch.object(deploy, "show_resource", return_value={"properties": {"provisioningState": "Failed"}}):
            with patch.object(deploy, "run_quiet", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "retry option 2"):
                    deploy.ready_for_create(
                        self.subscription_id, "Microsoft.Storage/storageAccounts", self.storage_name,
                    )

    def test_failed_resource_group_create_stops_provisioning(self):
        with patch.object(deploy, "az_query", return_value="false"):
            with patch.object(deploy, "run_quiet", return_value=False):
                self.assertFalse(deploy.create_resource_group(self.subscription_id))

    def test_failed_security_configuration_stops_the_resource_step(self):
        for function, name in (
            (deploy.create_webpubsub, self.pubsub_name),
            (deploy.create_storage, self.storage_name),
        ):
            with self.subTest(resource=name):
                with patch.object(deploy, "create_resource_group", return_value=True), patch.object(
                    deploy, "check_provider_registration", return_value=True,
                ):
                    with patch.object(deploy, "ready_for_create", return_value=False):
                        with patch.object(deploy, "run_quiet", return_value=False):
                            with patch.object(deploy, "assign_role") as role:
                                self.assertFalse(function(self.subscription_id, name, self.user_object_id))
                role.assert_not_called()

    def test_role_assignment_failure_is_explicit(self):
        with patch.object(deploy, "az_query", return_value="0"):
            with patch.object(deploy, "run_quiet", return_value=False):
                self.assertFalse(deploy.assign_role(
                    self.subscription_id, "Microsoft.SignalRService/WebPubSub",
                    self.pubsub_name, self.user_object_id, deploy.WEBPUBSUB_ROLE,
                ))

    def test_role_assignment_query_failure_is_not_treated_as_missing(self):
        with patch.object(deploy, "az_query", side_effect=RuntimeError("Role query denied")):
            with patch.object(deploy, "run_quiet") as action:
                with self.assertRaisesRegex(RuntimeError, "Role query denied"):
                    deploy.assign_role(
                        self.subscription_id, "Microsoft.Storage/storageAccounts",
                        self.storage_name, self.user_object_id, deploy.STORAGE_ROLE,
                    )
        action.assert_not_called()

    def test_configuration_retries_only_expected_rbac_delay(self):
        with patch.object(deploy, "resource_details", return_value=(self.pubsub, self.storage)):
            with patch.object(deploy, "run_quiet") as action, patch("time.sleep"):
                with patch.object(deploy, "az_query", side_effect=[
                    RuntimeError("AuthorizationPermissionMismatch"), '{"created":true}',
                ]) as query, patch.object(deploy, "write_env_files") as writer:
                    self.assertTrue(deploy.create_container(*self.resources))
        action.assert_not_called()
        writer.assert_not_called()
        self.assertEqual(query.call_count, 2)
        self.assertTrue(all(
            call.args[0][:4] == ["az", "storage", "container", "create"]
            for call in query.call_args_list
        ))

    def test_configuration_failure_does_not_write_environment_files(self):
        for error, attempts, message in (
            ("AuthorizationPermissionMismatch", 12, "retry option 3"),
            ("Network failure", 1, "Network failure"),
        ):
            with self.subTest(error=error):
                with patch.object(deploy, "resource_details", return_value=(self.pubsub, self.storage)):
                    with patch.object(deploy, "az_query", side_effect=RuntimeError(error)) as query:
                        with patch("time.sleep"), patch.object(deploy, "write_env_files") as writer:
                            with self.assertRaisesRegex(RuntimeError, message):
                                deploy.create_container(*self.resources)
                self.assertEqual(query.call_count, attempts)
                writer.assert_not_called()

    def test_configuration_prerequisites_point_to_the_specific_resource_step(self):
        for pubsub, storage, option in (
            (None, None, 1), (self.pubsub, None, 2),
            ({"properties": {"provisioningState": "Failed"}}, self.storage, 1),
            (self.pubsub, {"properties": {"provisioningState": "Failed"}}, 2),
        ):
            with self.subTest(option=option, pubsub=pubsub, storage=storage):
                with patch.object(deploy, "show_resource", side_effect=[pubsub, storage]):
                    with patch.object(deploy, "write_env_files") as writer:
                        with self.assertRaisesRegex(RuntimeError, f"option {option}"):
                            deploy.create_container(*self.resources)
                writer.assert_not_called()

    def test_status_reports_both_missing_resources_without_data_plane_calls(self):
        with patch.object(deploy, "show_resource", return_value=None):
            with patch.object(deploy, "az_query") as query, patch.object(deploy, "write_env_files") as writer:
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertFalse(deploy.verify_deployment(*self.verification_args))
        query.assert_not_called()
        writer.assert_not_called()
        self.assertIn("Web PubSub: Not created", output.getvalue())
        self.assertIn("Storage: Not created", output.getvalue())
        self.assertIn("option 1", output.getvalue())
        self.assertIn("option 2", output.getvalue())

    def test_status_can_check_webpubsub_without_a_storage_account(self):
        with patch.object(deploy, "show_resource", side_effect=[self.pubsub, None]):
            with patch.object(deploy, "az_query", side_effect=self.ready_query) as query:
                with patch.object(deploy, "write_env_files") as writer:
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        self.assertFalse(deploy.verify_deployment(*self.verification_args))
        self.assertEqual(query.call_args.args[0][:2], ["az", "rest"])
        writer.assert_not_called()
        self.assertIn("Web PubSub client-token API: Ready", output.getvalue())
        self.assertIn("Storage: Not created", output.getvalue())

    def test_status_continues_storage_checks_after_webpubsub_access_failure(self):
        self.responses["token"] = RuntimeError("Forbidden")
        with patch.object(deploy, "show_resource", side_effect=[self.pubsub, self.storage]):
            with patch.object(deploy, "az_query", side_effect=self.ready_query):
                with patch.object(deploy, "write_env_files") as writer:
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        self.assertFalse(deploy.verify_deployment(*self.verification_args))
        writer.assert_not_called()
        self.assertIn("Web PubSub access check failed", output.getvalue())
        self.assertIn("Blob container and read access: Ready", output.getvalue())

    def test_missing_blob_container_points_to_option_three(self):
        self.responses["container"] = "false"
        with patch.object(deploy, "show_resource", side_effect=[self.pubsub, self.storage]):
            with patch.object(deploy, "az_query", side_effect=self.ready_query):
                with patch.object(deploy, "write_env_files") as writer:
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        self.assertFalse(deploy.verify_deployment(*self.verification_args))
        writer.assert_not_called()
        self.assertIn("was not found. Run option 3", output.getvalue())

    def test_fully_ready_status_checks_both_data_planes(self):
        checks_at_write = []
        with patch.object(deploy, "show_resource", side_effect=[self.pubsub, self.storage]):
            with patch.object(deploy, "az_query", side_effect=self.ready_query) as query:
                with patch.object(
                    deploy, "write_env_files",
                    side_effect=lambda *args: checks_at_write.append(query.call_count),
                ) as writer:
                    self.assertTrue(deploy.verify_deployment(*self.verification_args))
        self.assertEqual(query.call_count, 5)
        self.assertEqual(checks_at_write, [5])
        values, directory = writer.call_args.args
        self.assertEqual(directory, str(ROOT))
        self.assertEqual(values, {
            "RESOURCE_GROUP": deploy.rg, "WEBPUBSUB_NAME": self.pubsub_name,
            "WEBPUBSUB_ENDPOINT": "https://example.webpubsub.azure.com",
            "WEBPUBSUB_HUB": deploy.HUB, "STORAGE_ACCOUNT_NAME": self.storage_name,
            "BLOB_ACCOUNT_URL": "https://example.blob.core.windows.net",
            "BLOB_CONTAINER": deploy.CONTAINER,
        })
        role_queries = [call.args[0] for call in query.call_args_list if call.args[0][1] == "role"]
        self.assertEqual(len(role_queries), 2)
        for argv, resource_type, resource_name, role in (
            (role_queries[0], "Microsoft.SignalRService/WebPubSub", self.pubsub_name, deploy.WEBPUBSUB_ROLE),
            (role_queries[1], "Microsoft.Storage/storageAccounts", self.storage_name, deploy.STORAGE_ROLE),
        ):
            self.assertEqual(argv[argv.index("--assignee-object-id") + 1], self.user_object_id)
            self.assertEqual(argv[argv.index("--role") + 1], role)
            self.assertEqual(
                argv[argv.index("--scope") + 1],
                deploy._resource_id(self.subscription_id, resource_type, resource_name),
            )

    def test_any_missing_role_or_failed_access_blocks_environment_generation(self):
        failures = (
            ("webpubsub_role", "0", "Run option 1"),
            ("storage_role", "0", "Run option 2"),
            ("webpubsub_role", "invalid count", "Could not verify"),
            ("token", RuntimeError("RBAC propagation pending"), "Web PubSub access check failed"),
            ("token", "{}", "did not return a token"),
            ("token", '{"token":null}', "did not return a token"),
            ("token", '{"token":" "}', "did not return a token"),
            ("token", "invalid JSON", "Web PubSub access check failed"),
            ("container", "false", "Run option 3"),
            ("container", "unknown", "Could not verify"),
            ("blobs", RuntimeError("Storage permission denied"), "Blob Storage access check failed"),
            ("blobs", "{}", "did not return a valid listing"),
            ("blobs", "invalid JSON", "Blob Storage access check failed"),
        )
        for key, result, message in failures:
            with self.subTest(check=key, result=result):
                original = self.responses[key]
                self.responses[key] = result
                try:
                    with patch.object(deploy, "show_resource", side_effect=[self.pubsub, self.storage]):
                        with patch.object(deploy, "az_query", side_effect=self.ready_query):
                            with patch.object(deploy, "write_env_files") as writer:
                                with contextlib.redirect_stdout(io.StringIO()) as output:
                                    self.assertFalse(deploy.verify_deployment(*self.verification_args))
                    writer.assert_not_called()
                    self.assertIn(message, output.getvalue())
                    self.assertIn("Environment files were not created or updated", output.getvalue())
                finally:
                    self.responses[key] = original

    def test_incomplete_or_insecure_resources_block_environment_generation(self):
        cases = (
            ("pubsub", "provisioningState", "Updating"),
            ("storage", "provisioningState", "Failed"),
            ("pubsub", "disableLocalAuth", False),
            ("pubsub", "hostName", None),
            ("pubsub", "hostName", "invalid/name"),
            ("storage", "allowSharedKeyAccess", True),
            ("storage", "allowBlobPublicAccess", True),
            ("storage", "supportsHttpsTrafficOnly", False),
            ("storage", "minimumTlsVersion", "TLS1_0"),
            ("storage", "primaryEndpoints", None),
            ("storage", "primaryEndpoints", {"blob": "http://example.blob.core.windows.net"}),
        )
        for service, field, value in cases:
            with self.subTest(service=service, field=field):
                pubsub = json.loads(json.dumps(self.pubsub))
                storage = json.loads(json.dumps(self.storage))
                resource = pubsub if service == "pubsub" else storage
                resource["properties"][field] = value
                with patch.object(deploy, "show_resource", side_effect=[pubsub, storage]):
                    with patch.object(deploy, "az_query", side_effect=self.ready_query):
                        with patch.object(deploy, "write_env_files") as writer:
                            self.assertFalse(deploy.verify_deployment(*self.verification_args))
                writer.assert_not_called()

    def test_failed_azure_resource_query_never_writes_environment_files(self):
        with patch.object(deploy, "show_resource", side_effect=RuntimeError("Azure unavailable")):
            with patch.object(deploy, "write_env_files") as writer:
                with self.assertRaisesRegex(RuntimeError, "Azure unavailable"):
                    deploy.verify_deployment(*self.verification_args)
        writer.assert_not_called()

    def test_failed_verification_preserves_existing_generated_files(self):
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            deploy.write_env_files({"PREVIOUS_SETTING": "preserve this"})
            files = [Path(".env"), Path(".env.ps1")]
            before = [path.read_bytes() for path in files]
            for key, result in (
                ("webpubsub_role", "0"), ("storage_role", "0"),
                ("token", RuntimeError("Forbidden")), ("container", "false"),
                ("blobs", RuntimeError("Forbidden")),
            ):
                with self.subTest(check=key):
                    original = self.responses[key]
                    self.responses[key] = result
                    try:
                        with patch.object(deploy, "show_resource", side_effect=[self.pubsub, self.storage]):
                            with patch.object(deploy, "az_query", side_effect=self.ready_query):
                                with patch.object(deploy, "__file__", str(Path(directory, "azdeploy.py"))):
                                    self.assertFalse(deploy.verify_deployment(*self.verification_args))
                        self.assertEqual([path.read_bytes() for path in files], before)
                    finally:
                        self.responses[key] = original
            os.chdir(previous)

    def test_environment_files_are_created_only_after_successful_verification(self):
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        with tempfile.TemporaryDirectory() as directory:
            script_dir = Path(directory)
            elsewhere = script_dir / "elsewhere"
            elsewhere.mkdir()
            os.chdir(elsewhere)
            with patch.object(deploy, "__file__", str(script_dir / "azdeploy.py")):
                self.responses["container"] = "false"
                with patch.object(deploy, "show_resource", side_effect=[self.pubsub, self.storage]):
                    with patch.object(deploy, "az_query", side_effect=self.ready_query):
                        self.assertFalse(deploy.verify_deployment(*self.verification_args))
                self.assertFalse((script_dir / ".env").exists())
                self.assertFalse((script_dir / ".env.ps1").exists())
                self.responses["container"] = "true"

                def ready_before_files(argv, **kwargs):
                    self.assertFalse((script_dir / ".env").exists())
                    self.assertFalse((script_dir / ".env.ps1").exists())
                    return self.ready_query(argv, **kwargs)

                with patch.object(deploy, "show_resource", side_effect=[self.pubsub, self.storage]):
                    with patch.object(deploy, "az_query", side_effect=ready_before_files):
                        self.assertTrue(deploy.verify_deployment(*self.verification_args))
            self.assertFalse((script_dir / "client").exists())
            self.assertFalse((elsewhere / ".env").exists())
            self.assertFalse((elsewhere / ".env.ps1").exists())
            bash = (script_dir / ".env").read_text(encoding="utf-8")
            powershell = (script_dir / ".env.ps1").read_text(encoding="utf-8")
            self.assertIn('export WEBPUBSUB_ENDPOINT="https://example.webpubsub.azure.com"', bash)
            self.assertIn('$env:BLOB_CONTAINER = "investigations"', powershell)
            self.assertNotIn("test-only", bash + powershell)
            os.chdir(previous)

    def test_security_failures_point_to_the_owning_resource_step(self):
        for field, resource, option in (
            ("disableLocalAuth", self.pubsub, 1), ("allowSharedKeyAccess", self.storage, 2),
        ):
            with self.subTest(field=field):
                original = resource["properties"][field]
                resource["properties"][field] = not original
                try:
                    with patch.object(deploy, "show_resource", side_effect=[self.pubsub, self.storage]):
                        with self.assertRaisesRegex(RuntimeError, f"Run option {option}"):
                            deploy.resource_details(*self.resources)
                finally:
                    resource["properties"][field] = original

    def test_menu_describes_verification_as_the_environment_file_gate(self):
        with patch.object(deploy, "clear_screen"):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                deploy.show_menu(*self.resources)
        self.assertIn("3. Create the private Blob container", output.getvalue())
        self.assertIn("4. Verify deployment and create environment files", output.getvalue())

    def test_menu_dispatch_uses_plain_arguments(self):
        for choice in ("1", "2", "3", "4", "5", "invalid"):
            with self.subTest(choice=choice):
                with patch.object(deploy, "_preflight"), patch.object(
                    deploy, "require_az_login", return_value=self.user_object_id,
                ), patch.object(deploy, "require_webpubsub_extension"), patch.object(
                    deploy, "az_query", return_value=self.subscription_id,
                ), patch.object(deploy, "show_menu") as menu, patch.object(
                    deploy, "clear_screen",
                ), patch.object(deploy, "pause"), patch(
                    "builtins.input", side_effect=[choice, "5"],
                ), patch.object(deploy, "create_webpubsub", return_value=True) as pubsub, patch.object(
                    deploy, "create_storage", return_value=True,
                ) as storage, patch.object(
                    deploy, "create_container", return_value=True,
                ) as configure, patch.object(deploy, "verify_deployment", return_value=True) as status:
                    deploy.main()
                menu.assert_called_with(*self.resources)
                if choice == "1":
                    pubsub.assert_called_once_with(self.subscription_id, self.pubsub_name, self.user_object_id)
                elif choice == "2":
                    storage.assert_called_once_with(self.subscription_id, self.storage_name, self.user_object_id)
                elif choice == "3":
                    configure.assert_called_once_with(*self.resources)
                elif choice == "4":
                    status.assert_called_once_with(*self.verification_args)
                else:
                    pubsub.assert_not_called()
                    storage.assert_not_called()
                    configure.assert_not_called()
                    status.assert_not_called()

    def test_menu_failure_identifies_the_selected_retry_option(self):
        with patch.object(deploy, "_preflight"), patch.object(
            deploy, "require_az_login", return_value=self.user_object_id,
        ), patch.object(deploy, "require_webpubsub_extension"), patch.object(
            deploy, "az_query", return_value=self.subscription_id,
        ), patch.object(deploy, "show_menu"), patch.object(
            deploy, "clear_screen",
        ), patch.object(deploy, "pause"), patch(
            "builtins.input", side_effect=["2", "5"],
        ), patch.object(deploy, "create_storage", return_value=False):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                deploy.main()
        self.assertIn("Option 2 did not complete", output.getvalue())
        self.assertIn("retry option 2", output.getvalue())

    def test_env_files_encoding_escaping_and_actual_shell_consumption(self):
        value = 'quote" slash\\ dollar$ backtick` end'
        with tempfile.TemporaryDirectory() as directory:
            deploy.write_env_files({"TEST_VALUE": value}, directory)
            bash = Path(directory, ".env").read_bytes()
            powershell = Path(directory, ".env.ps1").read_bytes()
            for raw in (bash, powershell):
                self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
                self.assertNotIn(b"\r", raw)
                self.assertTrue(raw.endswith(b"\n"))
            self.assertIn(b'\\"', bash)
            self.assertIn(b"\\$", bash)
            self.assertIn(b"\\`", bash)
            self.assertIn(b"\\\\", bash)
            self.assertIn(b'`"', powershell)
            self.assertIn(b"`$", powershell)
            self.assertIn(b"``", powershell)
            if shutil.which("bash"):
                result = subprocess.run(
                    [shutil.which("bash"), "-c", 'source "$1"; printf "%s" "$TEST_VALUE"',
                     "test", str(Path(directory, ".env"))],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, value)
            if shutil.which("pwsh"):
                result = subprocess.run(
                    [shutil.which("pwsh"), "-NoProfile", "-Command",
                     f". '{directory}/.env.ps1'; [Console]::Write($env:TEST_VALUE)"],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, value)


if __name__ == "__main__":
    unittest.main()
