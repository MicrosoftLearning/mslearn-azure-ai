"""Deterministic sample records for the persistent-memory workflow."""

TENANT_ID = "contoso"
USER_ID = "user-42"
ACTIVE_THREAD_ID = "thread-model-endpoint"
MEMORY_THREAD_ID = f"memory-{USER_ID}"

SAMPLE_TURNS = [
    {
        "id": "turn-request-1001",
        "tenantId": TENANT_ID,
        "userId": USER_ID,
        "threadId": "thread-sdk-timeout",
        "memoryType": "turn",
        "timestamp": "2026-09-28T17:05:00Z",
        "content": {
            "userMessage": "Use Python examples when we troubleshoot this SDK timeout.",
            "assistantMessage": "I'll use Python examples for the investigation.",
        },
        "schemaVersion": 1,
    },
    {
        "id": "turn-request-2001",
        "tenantId": TENANT_ID,
        "userId": USER_ID,
        "threadId": ACTIVE_THREAD_ID,
        "memoryType": "turn",
        "timestamp": "2026-09-28T18:10:00Z",
        "content": {
            "userMessage": "The deployment succeeds, but document processing fails.",
            "assistantMessage": "The health log shows a missing model endpoint setting.",
        },
        "schemaVersion": 1,
    },
    {
        "id": "turn-request-2002",
        "tenantId": TENANT_ID,
        "userId": USER_ID,
        "threadId": ACTIVE_THREAD_ID,
        "memoryType": "turn",
        "timestamp": "2026-09-28T18:14:00Z",
        "content": {
            "userMessage": "The setting should come from Azure Key Vault.",
            "assistantMessage": (
                "The application configuration doesn't reference the vault secret."
            ),
        },
        "schemaVersion": 1,
    },
]

SAMPLE_PREFERENCE = {
    "id": "preference-user-42-code-language",
    "tenantId": TENANT_ID,
    "userId": USER_ID,
    "threadId": MEMORY_THREAD_ID,
    "memoryType": "preference",
    "timestamp": "2026-09-28T17:06:00Z",
    "content": {
        "name": "codeLanguage",
        "value": "Python",
    },
    "sourceTurnIds": ["turn-request-1001"],
    "confidence": 1.0,
    "schemaVersion": 1,
    "ttl": -1,
}
