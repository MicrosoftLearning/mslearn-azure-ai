import json
import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client"))

from operation_access import connection_details, get_client, group_name
from operation_store import OperationStore
from simulator import EXPECTED_TEXT, simulate
from worker_logic import run_investigation


@unittest.skipUnless(os.environ.get("RUN_AZURE_LIVE_TESTS") == "1", "Opt-in Azure test; no resource provisioning")
class LiveDeliveryTests(unittest.TestCase):
    def test_shared_delivery_isolation_and_snapshot_recovery(self):
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import ContainerClient
        from websockets.sync.client import connect

        with DefaultAzureCredential() as credential:
            with ContainerClient(
                account_url=os.environ["BLOB_ACCOUNT_URL"],
                container_name=os.environ["BLOB_CONTAINER"], credential=credential,
            ) as container, get_client(credential) as service:
                store = OperationStore(container)
                operation = store.create("oncall", ["oncall", "database"])
                unrelated = store.create("oncall", ["oncall"])
                with self.assertRaises(PermissionError):
                    connection_details(service, operation, "outsider")
                details = connection_details(service, operation, "oncall")
                second = connection_details(service, operation, "database")
                isolated = connection_details(service, unrelated, "oncall")

                def join(socket, group):
                    socket.send(json.dumps({"type": "joinGroup", "group": group, "ackId": 1}))
                    while True:
                        message = json.loads(socket.recv(timeout=20))
                        if message.get("type") == "ack" and message.get("ackId") == 1:
                            self.assertTrue(message.get("success"), message.get("error"))
                            return

                def events(socket):
                    received = []
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        message = json.loads(socket.recv(timeout=max(0.1, deadline - time.monotonic())))
                        if message.get("type") == "message" and message.get("from") == "server":
                            data = message["data"]
                            received.append(json.loads(data) if isinstance(data, str) else data)
                            if received[-1]["type"] == "completed":
                                return received
                    self.fail("Completion did not arrive.")

                protocol = ["json.webpubsub.azure.v1"]
                with connect(details["url"], subprotocols=protocol) as first_socket, connect(
                    second["url"], subprotocols=protocol,
                ) as second_socket, connect(isolated["url"], subprotocols=protocol) as isolated_socket:
                    join(first_socket, details["group"])
                    join(second_socket, second["group"])
                    join(isolated_socket, isolated["group"])
                    first_socket.send(json.dumps({
                        "type": "sendToGroup", "group": group_name(unrelated.operation_id),
                        "dataType": "text", "data": "must be denied", "ackId": 2,
                    }))
                    while True:
                        acknowledgement = json.loads(first_socket.recv(timeout=20))
                        if acknowledgement.get("ackId") == 2:
                            self.assertFalse(acknowledgement["success"])
                            break
                    self.assertTrue(store.claim(operation.operation_id)[1])
                    self.assertFalse(store.claim(operation.operation_id)[1])
                    run_investigation(store, service, operation.operation_id, lambda: simulate(0))
                    received = events(first_socket)
                    self.assertEqual(received, events(second_socket))
                    batches = [event for event in received if event["type"] == "findings"]
                    self.assertEqual(len(batches), 4)
                    self.assertEqual("".join(event["payload"]["text"] for event in batches), EXPECTED_TEXT)
                    self.assertEqual(received[-2]["type"], "findings")
                    with self.assertRaises(TimeoutError):
                        isolated_socket.recv(timeout=2)
                # A new connection joins the same operation without starting another worker.
                reconnected = connection_details(service, operation, "database")
                with connect(reconnected["url"], subprotocols=protocol) as socket:
                    join(socket, reconnected["group"])
                    snapshot, _ = store.load(operation.operation_id)
                    self.assertEqual(snapshot.status, "completed")
                    self.assertEqual(snapshot.worker_starts, 1)
                    self.assertEqual(snapshot.sequence, received[-1]["sequence"])
                    self.assertEqual(store.result(operation.operation_id)["text"], EXPECTED_TEXT)


if __name__ == "__main__":
    unittest.main()
