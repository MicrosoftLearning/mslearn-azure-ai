"""Offline tests for the persistent-memory exercise application."""

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


class MemoryFunctionTests(unittest.TestCase):
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
        app_module.workflow.reset()
        self.client = app_module.app.test_client()

    def test_index_marks_only_the_first_step_as_next(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"1. Store Conversation Turns", response.data)
        self.assertIn(b'aria-current="step"', response.data)
        self.assertEqual(response.data.count(b"Next"), 1)
        self.assertEqual(response.data.count(b"Pending"), 4)

    def test_out_of_order_route_is_rejected(self) -> None:
        with patch.object(app_module, "store_durable_preference") as store_preference:
            response = self.client.post("/store-preference", follow_redirects=True)

        store_preference.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Complete the previous step", response.data)

    def test_store_turns_route_advances_workflow(self) -> None:
        result = {
            "stored_ids": ["turn-request-1001"],
            "count": 1,
            "request_charge": 1.0,
        }
        with patch.object(app_module, "store_conversation_turns", return_value=result):
            response = self.client.post("/store-turns")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"turn-request-1001", response.data)
        self.assertTrue(app_module.workflow.turns_stored)
        self.assertIn(b"2. Store Durable Preference", response.data)

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
        for step in (
            "turns_stored",
            "preference_stored",
            "thread_retrieved",
            "memory_retrieved",
        ):
            setattr(app_module.workflow, step, True)
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
        self.assertTrue(app_module.workflow.context_built)


if __name__ == "__main__":
    unittest.main()
