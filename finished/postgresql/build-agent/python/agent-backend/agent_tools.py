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

def create_conversation(user_id: str, metadata: dict = None) -> dict:
    """Create a new conversation and return its details."""
    session_id = uuid.uuid4()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (session_id, user_id, metadata)
                VALUES (%s, %s, %s)
                RETURNING id, session_id, started_at
                """,
                (str(session_id), user_id, psycopg.types.json.Json(metadata or {}))
            )
            row = cur.fetchone()
            conn.commit()
            return {
                "conversation_id": row[0],
                "session_id": str(row[1]),
                "started_at": row[2].isoformat()
            }

# END CREATE CONVERSATION FUNCTION

# BEGIN STORE MESSAGE FUNCTION

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

# END STORE MESSAGE FUNCTION

# BEGIN RETRIEVE CONVERSATION HISTORY FUNCTION

def get_conversation_history(conversation_id: int, limit: int = 50) -> list:
    """Retrieve recent messages from a conversation."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, role, content, created_at, metadata
                FROM messages
                WHERE conversation_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (conversation_id, limit)
            )
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "role": row[1],
                    "content": row[2],
                    "created_at": row[3].isoformat(),
                    "metadata": row[4]
                }
                for row in reversed(rows)  # Return in chronological order
            ]

# END RETRIEVE CONVERSATION HISTORY FUNCTION

# BEGIN TASK CHECKPOINT FUNCTIONS

def save_task_state(conversation_id: int, task_name: str, status: str, checkpoint_data: dict) -> dict:
    """Save or update a task checkpoint."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO task_checkpoints (conversation_id, task_name, status, checkpoint_data)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (conversation_id, task_name)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    checkpoint_data = EXCLUDED.checkpoint_data,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id, updated_at
                """,
                (conversation_id, task_name, status, psycopg.types.json.Json(checkpoint_data))
            )
            # Note: The ON CONFLICT requires a unique constraint we need to add
            row = cur.fetchone()
            conn.commit()
            return {
                "checkpoint_id": row[0],
                "updated_at": row[1].isoformat()
            }

# END TASK CHECKPOINT FUNCTIONS

# BEGIN RETRIEVE TASK STATE FUNCTION

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

# END RETRIEVE TASK STATE FUNCTION
