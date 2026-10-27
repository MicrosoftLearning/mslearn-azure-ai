import re
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client"))

from azure.core.exceptions import AzureError, ResourceModifiedError

from app import create_app
from fakes import FakePubSub, MemoryContainer
from notifications import publish_event
from operation_access import authorize, connection_details, group_name
from operation_store import OperationStore
from simulator import EXPECTED_TEXT, FRAGMENT_COUNT, simulate
from worker_logic import BATCH_FRAGMENTS, run_investigation


class InvestigationFixture(unittest.TestCase):
    def setUp(self):
        self.container = MemoryContainer()
        self.store = OperationStore(self.container)
        self.pubsub = FakePubSub()
        self.operation = self.store.create("oncall", ["oncall", "database"])
        self.oid = self.operation.operation_id

    def run_worker(self):
        self.store.claim(self.oid)
        run_investigation(self.store, self.pubsub, self.oid, lambda: simulate(0))


class InvestigationTests(InvestigationFixture):
    def test_round_trip_and_create_only(self):
        actual, etag = self.store.load(self.oid)
        self.assertEqual(actual, self.operation)
        self.assertEqual(etag, "1")
        self.assertEqual(actual.sequence, 0)
        self.assertEqual(actual.status, "pending")

    def test_conditional_write_rejects_stale_etag(self):
        self.store.claim(self.oid)
        with self.assertRaises(ResourceModifiedError):
            self.store._save(self.operation, "1")

    def test_repeated_claim_does_not_restart(self):
        self.assertTrue(self.store.claim(self.oid)[1])
        self.assertFalse(self.store.claim(self.oid)[1])
        self.assertEqual(self.store.load(self.oid)[0].worker_starts, 1)

    def test_concurrent_claim_has_one_winner(self):
        original = self.store.load
        barrier = threading.Barrier(2)

        def simultaneous_load(oid):
            operation, etag = original(oid)
            if operation.status == "pending":
                barrier.wait(timeout=5)
            return operation, etag

        with patch.object(self.store, "load", side_effect=simultaneous_load):
            with ThreadPoolExecutor(max_workers=2) as pool:
                claims = list(pool.map(self.store.claim, [self.oid, self.oid]))
        self.assertEqual(sum(claimed for _, claimed in claims), 1)
        self.assertEqual(self.store.load(self.oid)[0].worker_starts, 1)

    def test_worker_batches_exact_text_and_final_partial_before_completion(self):
        self.run_worker()
        events = [event for _, event, _ in self.pubsub.events]
        findings = [event for event in events if event["type"] == "findings"]
        self.assertEqual(FRAGMENT_COUNT, 11)
        self.assertEqual(BATCH_FRAGMENTS, 3)
        self.assertEqual(len(findings), 4)
        self.assertLess(len(findings), FRAGMENT_COUNT)
        self.assertEqual("".join(event["payload"]["text"] for event in findings), EXPECTED_TEXT)
        self.assertEqual([event["type"] for event in events][-2:], ["findings", "completed"])
        self.assertEqual([event["sequence"] for event in events], list(range(1, 9)))
        self.assertEqual(len({event["event_id"] for event in events}), 8)
        for group, event, content_type in self.pubsub.events:
            self.assertEqual(group, group_name(self.oid))
            self.assertEqual(event["event_id"], f"{self.oid}:{event['sequence']}")
            self.assertEqual(content_type, "application/json")
        stored, _ = self.store.load(self.oid)
        self.assertEqual(stored.text, EXPECTED_TEXT)
        self.assertEqual(stored.progress, 100)
        self.assertEqual(stored.status, "completed")
        self.assertEqual(stored.sequence, events[-1]["sequence"])
        self.assertEqual(stored.result_ref, f"/api/operations/{self.oid}/result")
        self.assertEqual(self.store.result(self.oid)["text"], EXPECTED_TEXT)

    def test_every_event_is_persisted_before_publish(self):
        original = self.pubsub.send_to_group

        def check(**kwargs):
            event = kwargs["message"]
            stored, _ = self.store.load(self.oid)
            self.assertEqual(stored.sequence, event["sequence"])
            if event["type"] == "completed":
                self.assertEqual(self.store.result(self.oid)["text"], EXPECTED_TEXT)
            original(**kwargs)

        with patch.object(self.pubsub, "send_to_group", side_effect=check):
            self.run_worker()

    def test_publish_failure_retains_complete_recoverable_snapshot(self):
        self.pubsub.fail_publish = True
        with patch("notifications.time.sleep"), self.assertLogs("notifications", "WARNING"):
            self.run_worker()
        stored, _ = self.store.load(self.oid)
        self.assertEqual(stored.text, EXPECTED_TEXT)
        self.assertEqual(stored.status, "completed")
        self.assertIn("Live delivery failed", stored.delivery_error)

    def test_retry_uses_identical_event_and_clears_diagnostic(self):
        self.store.claim(self.oid)
        event = self.store.record(self.oid, "findings", {"text": "test"})
        self.store.delivery_problem(self.oid, "previous failure")
        attempts = []

        def send(**kwargs):
            attempts.append(kwargs["message"])
            if len(attempts) < 3:
                raise AzureError("temporary")

        with patch.object(self.pubsub, "send_to_group", side_effect=send):
            with patch("notifications.time.sleep"), self.assertLogs("notifications", "WARNING"):
                publish_event(self.pubsub, self.store, event)
        self.assertEqual(attempts, [event, event, event])
        self.assertIsNone(self.store.load(self.oid)[0].delivery_error)

    def test_storage_failure_does_not_publish_success(self):
        self.store.claim(self.oid)
        self.container.fail_writes = True
        with self.assertLogs("worker_logic", "ERROR"), self.assertRaises(AzureError):
            run_investigation(self.store, self.pubsub, self.oid, lambda: simulate(0))
        self.assertEqual(self.pubsub.events, [])
        self.assertEqual(self.store.load(self.oid)[0].sequence, 0)

    def test_simulator_failure_persists_failed_state(self):
        def broken():
            raise RuntimeError("Injected simulator failure")

        self.store.claim(self.oid)
        with self.assertLogs("worker_logic", "ERROR"):
            run_investigation(self.store, self.pubsub, self.oid, broken)
        stored, _ = self.store.load(self.oid)
        self.assertEqual(stored.status, "failed")
        self.assertEqual(self.pubsub.events[-1][1]["type"], "failed")

    def test_startup_interrupts_running_but_preserves_completed(self):
        self.run_worker()
        other = self.store.create("oncall", ["oncall", "database"])
        self.store.claim(other.operation_id)
        restarted = OperationStore(self.container)
        restarted.interrupt_abandoned()
        self.assertEqual(restarted.load(self.oid)[0].status, "completed")
        self.assertEqual(restarted.result(self.oid)["text"], EXPECTED_TEXT)
        abandoned = restarted.load(other.operation_id)[0]
        self.assertEqual(abandoned.status, "interrupted")
        self.assertEqual(abandoned.worker_starts, 1)
        self.assertFalse(restarted.claim(other.operation_id)[1])

    def test_only_active_worker_can_write(self):
        self.store.claim(self.oid)
        other = OperationStore(self.container)
        with self.assertRaisesRegex(ValueError, "active worker"):
            other.record(self.oid, "findings", {"text": "wrong worker"})

    def test_access_and_scoped_token(self):
        details = connection_details(self.pubsub, self.operation, "database")
        self.assertEqual(details["group"], group_name(self.oid))
        self.assertEqual(self.pubsub.token_requests, [{
            "user_id": "database",
            "roles": [f"webpubsub.joinLeaveGroup.{group_name(self.oid)}"],
            "minutes_to_expire": 5,
        }])
        with self.assertRaises(PermissionError):
            connection_details(self.pubsub, self.operation, "outsider")
        self.assertEqual(len(self.pubsub.token_requests), 1)
        with self.assertRaises(PermissionError):
            authorize(self.operation, "database", start=True)

    def test_invalid_operation_id(self):
        for invalid in ("../result", "", "a" * 31, "A" * 32):
            with self.assertRaises(ValueError):
                self.store.load(invalid)


class FlaskTests(InvestigationFixture):
    def setUp(self):
        super().setUp()
        self.app = create_app(self.store, self.pubsub, recover=False)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.csrf = self.initialize(self.client)

    def initialize(self, client):
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        return re.search(r'name="csrf-token" content="([^"]+)"', response.text).group(1)

    def post(self, url, data=None, *, client=None, csrf=None):
        return (client or self.client).post(
            url, json=data, headers={"X-CSRF-Token": csrf or self.csrf},
        )

    def test_persona_session_is_server_selected_and_access_is_consistent(self):
        self.assertEqual(self.post("/api/persona", {"persona": "outsider"}).status_code, 200)
        for suffix, method in (("", "GET"), ("/result", "GET"), ("/negotiate", "POST"), ("/start", "POST")):
            url = f"/api/operations/{self.oid}{suffix}"
            response = self.client.get(url) if method == "GET" else self.post(url, {"persona": "oncall"})
            self.assertEqual(response.status_code, 403, suffix)
        self.assertEqual(self.post("/api/operations").status_code, 403)
        self.assertEqual(self.pubsub.token_requests, [])

    def test_two_browser_sessions_share_one_operation(self):
        specialist = self.app.test_client()
        csrf = self.initialize(specialist)
        self.post("/api/persona", {"persona": "database"}, client=specialist, csrf=csrf)
        for client, token in ((self.client, self.csrf), (specialist, csrf)):
            self.assertEqual(client.get(f"/api/operations/{self.oid}").status_code, 200)
            self.assertEqual(self.post(
                f"/api/operations/{self.oid}/negotiate", client=client, csrf=token,
            ).status_code, 200)
        self.assertEqual(self.store.load(self.oid)[0].worker_starts, 0)
        with patch("app.threading.Thread") as thread:
            first = self.post(f"/api/operations/{self.oid}/start")
            second = self.post(f"/api/operations/{self.oid}/start")
        self.assertTrue(first.json["started"])
        self.assertFalse(second.json["started"])
        self.assertEqual(thread.return_value.start.call_count, 1)
        self.assertEqual(
            self.post(f"/api/operations/{self.oid}/start", client=specialist, csrf=csrf).status_code, 403,
        )

    def test_completed_snapshot_and_result_survive_reload(self):
        self.run_worker()
        reader = self.app.test_client()
        self.initialize(reader)
        self.assertEqual(reader.get(f"/api/operations/{self.oid}").json["text"], EXPECTED_TEXT)
        self.assertEqual(reader.get(f"/api/operations/{self.oid}/result").json["text"], EXPECTED_TEXT)
        self.assertEqual(self.store.load(self.oid)[0].worker_starts, 1)

    def test_csrf_and_cross_origin_rejected(self):
        self.assertEqual(self.client.post("/api/operations").status_code, 403)
        response = self.client.post("/api/operations", headers={
            "X-CSRF-Token": self.csrf, "Origin": "https://unrelated.invalid",
        })
        self.assertEqual(response.status_code, 403)

    def test_malformed_personas_and_json_are_not_accepted(self):
        for value in (None, [], {}, "unknown"):
            self.assertEqual(self.post("/api/persona", {"persona": value}).status_code, 400)
        response = self.client.post("/api/persona", data="{", content_type="application/json",
                                    headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(response.status_code, 400)

    def test_pending_result_and_unknown_operation(self):
        self.assertEqual(self.client.get(f"/api/operations/{self.oid}/result").status_code, 409)
        self.assertEqual(self.client.get("/api/operations/" + "f" * 32).status_code, 404)

    def test_azure_failure_has_explicit_error_status(self):
        with patch.object(self.store, "load", side_effect=AzureError("Injected failure")):
            with self.assertLogs(self.app.logger, "ERROR"):
                response = self.client.get(f"/api/operations/{self.oid}")
        self.assertEqual(response.status_code, 503)
        self.assertIn("error", response.json)
        self.assertNotIn("text", response.json)

    def test_worker_thread_start_failure_is_not_a_success(self):
        with patch("app.threading.Thread") as thread:
            thread.return_value.start.side_effect = RuntimeError("Cannot start thread")
            with self.assertLogs(self.app.logger, "ERROR"):
                response = self.post(f"/api/operations/{self.oid}/start")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.store.load(self.oid)[0].status, "failed")

    def test_missing_config_is_actionable(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "Run deployment option 4"):
                create_app()


if __name__ == "__main__":
    unittest.main()
