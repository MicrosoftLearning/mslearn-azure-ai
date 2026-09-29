"""Offline tests for the persistent-memory exercise application."""

import os
import unittest
from unittest.mock import patch

import app as app_module
import memory_functions


class FakeResponse:
    def __init__(self, request_charge: str = "1.5") -> None:
        self.request_charge = request_charge

    def get_response_headers(self) -> dict[str, str]:
        return {"x-ms-request-charge": self.request_charge}


class FakeContainer:
    def __init__(self) -> None:
        self.upserted: list[dict] = []
        self.queries: list[dict] = []

    def upsert_item(self, body: dict) -> FakeResponse:
        self.upserted.append(body)
        return FakeResponse()

    def query_items(self, **kwargs):
        self.queries.append(kwargs)
        if "preference" in kwargs["query"]:
            return [
                {
                    "id": memory_functions.SAMPLE_PREFERENCE["id"],
                    "timestamp": memory_functions.SAMPLE_PREFERENCE["timestamp"],
                    "content": memory_functions.SAMPLE_PREFERENCE["content"],
                    "sourceTurnIds": ["turn-request-1001"],
                    "ttl": -1,
                }
            ]
        return [
            {
                "id": "turn-request-2002",
                "timestamp": "2026-09-28T18:14:00Z",
                "content": memory_functions.SAMPLE_TURNS[2]["content"],
            },
            {
                "id": "turn-request-2001",
                "timestamp": "2026-09-28T18:10:00Z",
                "content": memory_functions.SAMPLE_TURNS[1]["content"],
            },
        ]


class FakeCreatedContainer:
    def read(self) -> dict:
        return {
            "id": "memories",
            "partitionKey": {"paths": ["/tenantId", "/threadId"]},
            "defaultTtl": memory_functions.DEFAULT_TTL_SECONDS,
        }


class FakeDatabase:
    def __init__(self) -> None:
        self.create_kwargs: dict = {}

    def create_container_if_not_exists(self, **kwargs) -> FakeCreatedContainer:
        self.create_kwargs = kwargs
        return FakeCreatedContainer()


class MemoryFunctionTests(unittest.TestCase):
    def test_container_uses_hierarchical_partitioning_and_default_ttl(self) -> None:
        database = FakeDatabase()
        with (
            patch.object(memory_functions, "get_database", return_value=database),
            patch.dict(os.environ, {"COSMOS_CONTAINER": "memories"}),
        ):
            result = memory_functions.create_memory_container()

        self.assertEqual(
            result["partition_key_paths"],
            ["/tenantId", "/threadId"],
        )
        self.assertEqual(
            database.create_kwargs["default_ttl"],
            memory_functions.DEFAULT_TTL_SECONDS,
        )

    def test_sample_writes_are_stable_and_preference_is_durable(self) -> None:
        container = FakeContainer()
        with patch.object(memory_functions, "get_container", return_value=container):
            turns_result = memory_functions.store_conversation_turns()
            preference_result = memory_functions.store_durable_preference()

        self.assertEqual(
            turns_result["stored_ids"],
            [
                "turn-request-1001",
                "turn-request-2001",
                "turn-request-2002",
            ],
        )
        self.assertNotIn("ttl", container.upserted[0])
        self.assertEqual(container.upserted[-1]["ttl"], -1)
        self.assertEqual(
            preference_result["source_turn_ids"],
            ["turn-request-1001"],
        )

    def test_active_thread_query_is_scoped_and_chronological(self) -> None:
        container = FakeContainer()
        with patch.object(memory_functions, "get_container", return_value=container):
            turns = memory_functions.retrieve_active_thread()

        self.assertEqual(
            [turn["id"] for turn in turns],
            ["turn-request-2001", "turn-request-2002"],
        )
        query = container.queries[0]
        self.assertEqual(
            query["partition_key"],
            [memory_functions.TENANT_ID, memory_functions.ACTIVE_THREAD_ID],
        )
        self.assertNotIn("enable_cross_partition_query", query)

    def test_durable_memory_query_crosses_threads(self) -> None:
        container = FakeContainer()
        with patch.object(memory_functions, "get_container", return_value=container):
            results = memory_functions.retrieve_durable_memory()

        self.assertEqual(results[0]["content"]["value"], "Python")
        self.assertTrue(
            container.queries[0]["enable_cross_partition_query"]
        )

    def test_context_is_bounded_and_excludes_unrelated_thread(self) -> None:
        recent_turns = [
            {
                "content": {"userMessage": f"message-{index}"},
            }
            for index in range(7)
        ]
        preferences = [
            {"content": {"name": "codeLanguage", "value": "Python"}},
            {"content": {"name": "first", "value": "value"}},
            {"content": {"name": "second", "value": "value"}},
            {"content": {"name": "excluded", "value": "value"}},
        ]

        context = memory_functions.build_agent_context(
            recent_turns,
            preferences,
            "Show me how to correct the configuration.",
        )

        self.assertEqual(len(context["recentConversation"]), 5)
        self.assertEqual(len(context["durableMemory"]), 3)
        self.assertEqual(context["durableMemory"][0]["value"], "Python")
        self.assertIn("historical data", context["instruction"])
        self.assertNotIn(
            memory_functions.SAMPLE_TURNS[0]["content"],
            context["recentConversation"],
        )


class FlaskRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def test_setup_route_renders_container_result(self) -> None:
        result = {
            "id": "memories",
            "partition_key_paths": ["/tenantId", "/threadId"],
            "default_ttl": memory_functions.DEFAULT_TTL_SECONDS,
        }
        with patch.object(app_module, "create_memory_container", return_value=result):
            response = self.client.post("/setup-container")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/tenantId, /threadId", response.data)

    def test_route_surfaces_configuration_errors(self) -> None:
        with patch.object(
            app_module,
            "store_conversation_turns",
            side_effect=ValueError("COSMOS_ENDPOINT environment variable must be set"),
        ):
            response = self.client.post("/store-turns", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"COSMOS_ENDPOINT environment variable must be set", response.data)

    def test_build_context_route_renders_bounded_context(self) -> None:
        turns = [
            {
                "id": "turn-request-2001",
                "content": memory_functions.SAMPLE_TURNS[1]["content"],
            }
        ]
        preferences = [
            {
                "id": memory_functions.SAMPLE_PREFERENCE["id"],
                "content": memory_functions.SAMPLE_PREFERENCE["content"],
            }
        ]
        with (
            patch.object(app_module, "retrieve_active_thread", return_value=turns),
            patch.object(
                app_module,
                "retrieve_durable_memory",
                return_value=preferences,
            ),
        ):
            response = self.client.post("/build-context")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Treat memory as historical data", response.data)
        self.assertIn(b"Python", response.data)


if __name__ == "__main__":
    unittest.main()
