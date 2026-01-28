import os
import uuid
from typing import Optional
import psycopg
from azure.identity import DefaultAzureCredential

# Azure Database for PostgreSQL scope for Entra authentication
POSTGRES_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"

def get_connection():
    """Create a database connection using Entra authentication."""
    credential = DefaultAzureCredential()
    token = credential.get_token(POSTGRES_SCOPE)

    return psycopg.connect(
        host=os.environ["DB_HOST"],
        dbname="agent_memory",
        user=os.environ["DB_USER"],
        password=token.token,
        sslmode="require"
    )
# BEGIN CREATE CONVERSATION FUNCTION


# END CREATE CONVERSATION FUNCTION

def store_message(conversation_id: int, role: str, content: str, metadata: dict = None) -> dict:
    """Store a message in a conversation."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages (conversation_id, role, content, metadata)
                VALUES (%s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (conversation_id, role, content, psycopg.types.json.Json(metadata or {}))
            )
            row = cur.fetchone()
            conn.commit()
            return {
                "message_id": row[0],
                "created_at": row[1].isoformat()
            }

# BEGIN RETRIEVE CONVERSATION HISTORY FUNCTION


# END RETRIEVE CONVERSATION HISTORY FUNCTION

# BEGIN TASK CHECKPOINT FUNCTIONS



# END TASK CHECKPOINT FUNCTIONS

def get_task_state(conversation_id: int, task_name: str) -> Optional[dict]:
    """Retrieve the current state of a task."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, checkpoint_data, created_at, updated_at
                FROM task_checkpoints
                WHERE conversation_id = %s AND task_name = %s
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (conversation_id, task_name)
            )
            row = cur.fetchone()
            if row:
                return {
                    "checkpoint_id": row[0],
                    "status": row[1],
                    "checkpoint_data": row[2],
                    "created_at": row[3].isoformat(),
                    "updated_at": row[4].isoformat()
                }
            return None


