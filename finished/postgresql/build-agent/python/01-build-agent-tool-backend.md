---
lab:
    topic: Azure Database for PostgreSQL
    title: 'Build an agent tool backend'
    description: 'Learn how to ...'
---

# Build an agent tool backend

In this exercise, you create an Azure Database for PostgreSQL instance that serves as a tool backend for an AI agent. The database stores conversation context and task state that an agent can read and write during operation. You design a schema for agent memory, build Python functions that serve as agent tools, and test the complete workflow. This pattern provides a foundation for building AI agents that maintain persistent memory across sessions and can resume interrupted tasks.

Tasks performed in this exercise:

- Download the project starter files and deploy Azure services
- Deploy resources...
- ...

This exercise takes approximately **30** minutes to complete.

## Before you start

To complete the exercise, you need:

- An Azure subscription with the permissions to deploy the necessary Azure services. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- PostgreSQL command-line tools (`psql`) installed

## Download project starter files and deploy Azure services

In this section you download the project starter files and use a script to deploy the necessary services to your Azure subscription. The PostgreSQL server deployment takes a few minutes to complete.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/postgresql-agent-python.zip
    ```

1. Copy, or move, the file to a location in your system where you want to work on the project. Then unzip the file into a folder.

1. Launch Visual Studio Code (VS Code) and select **File > Open Folder...** in the menu, then choose the folder containing the project files.

1. The project contains deployment scripts for both Bash (*azdeploy.sh*) and PowerShell (*azdeploy.ps1*). Open the appropriate file for your environment and change the two values at the top of the script to meet your needs, then save your changes. **Note:** Do not change anything else in the script.

    ```
    "<your-resource-group-name>" # Resource Group name
    "<your-azure-region>" # Azure region for the resources
    ```

1. In the menu bar select **Terminal > New Terminal** to open a terminal window in VS Code.

1. Run the following command to login to your Azure account. Answer the prompts to select your Azure account and subscription for the exercise.

    ```
    az login
    ```

1. Run the following command to ensure your subscription has the necessary resource provider for the exercise.

    ```azurecli
    az provider register --namespace Microsoft.DBforPostgreSQL
    ```

### Create resources in Azure

In this section you run the deployment script to deploy the necessary services to your Azure subscription.

1. Make sure you are in the root directory of the project and run the appropriate command in the terminal to launch the deployment script.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

    >**Note:** Keep the terminal open. If you close it and create a new terminal, you might need to run the command to create the environment variable again.

1. When the script menu appears, enter **1** to launch the **Create PostgreSQL server with Entra authentication** option. This creates the server with Entra-only authentication enabled.

    >**Note:** The server deployment takes several minutes to complete.

1. When the server deployment completes, enter **2** to launch the **Configure Microsoft Entra administrator** option. This sets your Azure account as the database administrator.

1. When the previous operation completes, enter **3** to launch the **Check deployment status** option. This verifies the server is ready.

1. Enter **4** to launch the **Retrieve connection info and access token** option. This creates a *.env* file with the necessary environment variables.

1. Enter **5** to exit the deployment script.

1. Run the following command to load the environment variables into your terminal session from the file created in a previous step.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

    >**Note:** The access token expires after approximately one hour. If you need to reconnect later, run the script again and select option **4** to generate a new token, then export the variables again.

## Connect using psql and verify connectivity

In this section you test the connection using the **psql** command-line tool.

1. Run the following command to connect to the server using the environment variables. The **PGPASSWORD** environment variable is automatically used for authentication.

    **Bash**
    ```bash
    psql "host=$DB_HOST port=5432 dbname=$DB_NAME user=$DB_USER sslmode=require"
    ```

    **PowerShell**
    ```powershell
    psql "host=$env:DB_HOST port=5432 dbname=$env:DB_NAME user=$env:DB_USER sslmode=require"
    ```

1. Run the following command to verify the connection by checking the PostgreSQL version.

    ```sql
    SELECT version();
    ```

    You should see output showing the PostgreSQL version. Keep this connection open for the next steps.

## Create the agent memory schema

Design and create tables to store conversation history and task state.

1. In the `psql` session, create a database for the agent backend:

    ```sql
    CREATE DATABASE agent_memory;
    \c agent_memory
    ```

1. Create a table for conversations (agent sessions):

    ```sql
    CREATE TABLE conversations (
        id BIGSERIAL PRIMARY KEY,
        session_id UUID NOT NULL UNIQUE,
        user_id VARCHAR(255) NOT NULL,
        started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        ended_at TIMESTAMP WITH TIME ZONE,
        metadata JSONB DEFAULT '{}'::jsonb
    );
    ```

1. Create a table for messages within conversations:

    ```sql
    CREATE TABLE messages (
        id BIGSERIAL PRIMARY KEY,
        conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role VARCHAR(50) NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
        content TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        metadata JSONB DEFAULT '{}'::jsonb
    );
    ```

1. Create a table for task checkpoints (agent state persistence):

    ```sql
    CREATE TABLE task_checkpoints (
        id BIGSERIAL PRIMARY KEY,
        conversation_id BIGINT REFERENCES conversations(id) ON DELETE CASCADE,
        task_name VARCHAR(255) NOT NULL,
        status VARCHAR(50) NOT NULL CHECK (status IN ('pending', 'in_progress', 'completed', 'failed')),
        checkpoint_data JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    ```

1. Create indexes to optimize common queries:

    ```sql
    CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
    CREATE INDEX idx_messages_created_at ON messages(created_at);
    CREATE INDEX idx_task_checkpoints_conversation_id ON task_checkpoints(conversation_id);
    CREATE INDEX idx_conversations_session_id ON conversations(session_id);
    ```

1. Verify the schema:

    ```sql
    \dt
    ```

    You should see the three tables listed.

## Build Python tool functions

In this section you complete the *agent_tools.py* file by adding functions that an AI agent can call to persist and retrieve state. These functions serve as the agent's interface to the database. The *test_workflow.py* script, which you run later in this exercise, imports these functions to demonstrate how an agent would use them.

1. Open the *agent-backend/agent_tools.py* file in VS Code.

1. Search for the **BEGIN CREATE CONVERSATION FUNCTION** comment and add the following code directly after the comment. This function creates a new conversation record with a unique session ID and stores optional metadata as JSONB.

    ```python
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
    ```

1. Search for the **BEGIN RETRIEVE CONVERSATION HISTORY FUNCTION** comment and add the following code directly after the comment. This function retrieves messages from a conversation, ordered chronologically.

    ```python
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
    ```

1. Search for the **BEGIN TASK CHECKPOINT FUNCTIONS** comment and add the following code directly after the comment. This function uses an upsert pattern to save or update task state, allowing the agent to resume interrupted tasks.

    ```python
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
                row = cur.fetchone()
                conn.commit()
                return {
                    "checkpoint_id": row[0],
                    "updated_at": row[1].isoformat()
                }
    ```

1. Save the *agent_tools.py* file.

1. The **save_task_state** function uses **ON CONFLICT**, which requires a unique constraint. Run the following command in your **psql** session in the terminal to add it.

    ```sql
    ALTER TABLE task_checkpoints
    ADD CONSTRAINT unique_conversation_task
    UNIQUE (conversation_id, task_name);
    ```

## Test the agent memory workflow

In this section you run a test script to verify the tool functions work correctly. The *test_workflow.py* script is included in the project files and demonstrates creating conversations, storing messages, and managing task checkpoints.

1. In the menu bar select **Terminal > New Terminal** to open a terminal window in VS Code. This keeps your **psql** session active.

1. Run the following command to navigate to the *agent-backend* directory.

    ```
    cd agent-backend
    ```

1. Run the following command to create a virtual environment for the *test_workflow.py*  app. Depending on your environment the command might be **python** or **python3**.

    ```
    python -m venv .venv
    ```

1. Run the following command to activate the Python environment. **Note:** On Linux/macOS, use the Bash command. On Windows, use the PowerShell command. If using Git Bash on Windows, use **source .venv/Scripts/activate**.

    **Bash**
    ```bash
    source .venv/bin/activate
    ```

    **PowerShell**
    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

1. Run the following command to install the dependencies for the client app.

    ```bash
    pip install -r requirements.txt
    ```


1. Run the following command to execute the test script. This script exercises all the agent tool functions you created.

    ```bash
    python test_workflow.py
    ```

1. You should see output showing each step completing successfully, demonstrating that the agent can create conversations, store messages, save task state, and retrieve history.

## Query conversation context

Practice querying the data to support agent decision-making.

1. Return to your `psql` session connected to the `agent_memory` database.

1. Find all conversations for a specific user:

    ```sql
    SELECT id, session_id, started_at, metadata
    FROM conversations
    WHERE user_id = 'user_123'
    ORDER BY started_at DESC;
    ```

1. Get recent messages across all conversations:

    ```sql
    SELECT c.session_id, m.role, m.content, m.created_at
    FROM messages m
    JOIN conversations c ON m.conversation_id = c.id
    ORDER BY m.created_at DESC
    LIMIT 10;
    ```

1. Find in-progress tasks that might need attention:

    ```sql
    SELECT
        c.session_id,
        t.task_name,
        t.status,
        t.checkpoint_data,
        t.updated_at
    FROM task_checkpoints t
    JOIN conversations c ON t.conversation_id = c.id
    WHERE t.status = 'in_progress'
      AND t.updated_at < NOW() - INTERVAL '1 hour';
    ```

1. Count messages by role in each conversation:

    ```sql
    SELECT
        c.id AS conversation_id,
        m.role,
        COUNT(*) AS message_count
    FROM conversations c
    JOIN messages m ON c.id = m.conversation_id
    GROUP BY c.id, m.role
    ORDER BY c.id, m.role;
    ```

## Clean up resources

When you're finished with the exercise, delete the resource group to avoid ongoing charges:

```azurecli
az group delete --name rg-agent-backend --yes --no-wait
```

## Summary

In this exercise, you:

- Created an Azure Database for PostgreSQL server with Microsoft Entra authentication
- Configured passwordless access using Entra tokens
- Designed a schema for storing agent conversation history and task state
- Built Python functions that serve as tools for an AI agent to read and write state
- Tested the complete workflow of creating conversations, storing messages, and managing task checkpoints
- Queried the data to support agent context retrieval and decision-making
