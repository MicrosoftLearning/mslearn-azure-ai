---
lab:
    topic: Azure Database for PostgreSQL
    title: 'Build an agent tool backend'
    description: 'Learn how to ...'
---

# Build an agent tool backend

In this exercise, you create an Azure Database for PostgreSQL instance that serves as a tool backend for an AI agent. The database stores conversation context and task state that an agent can read and write during operation. You design a schema for agent memory, build Python functions that serve as agent tools, and test the complete workflow.

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

In this section you download the project starter files and use a script to deploy the necessary services to your Azure subscription. The Azure Container Registry and Container Apps environment deployment takes a few minutes to complete.

1. Open a browser and enter the following URL to download the starter file. The file will be saved in your default download location.

    ```
    https://github.com/MicrosoftLearning/mslearn-azure-ai/raw/main/downloads/python/aca-deploy-python.zip
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

1. Run the following commands to ensure your subscription has the necessary resource providers for the exercise.

    ```azurecli
    az provider register --namespace Microsoft.DBforPostgreSQL
    ```

### Create resources in Azure

In this section you run the deployment script to deploy the necessary services to your Azure subscription.

1. Make sure you are in the root directory of the project and run the appropriate command in the terminal to launch the deployment script. The deployment script will deploy ACR and create a file with environment variables needed for exercise.

    **Bash**
    ```bash
    bash azdeploy.sh
    ```

    **PowerShell**
    ```powershell
    ./azdeploy.ps1
    ```

1. When the script is running, enter **1** to launch the **Create Azure Container Registry and build container image** option. This option creates the ACR service and uses ACR Tasks to build and push the image to the registry.

1. When the previous operation is finished, enter **2** to launch the **Create Container Apps environment** options. Creating the environment is necessary before deploying the container.

    >**Note:** A file containing environment variables is created after the Container Apps environment is created. You use these variables throughout the exercise.

1. When the previous operation is finished, enter **4** to exit the deployment script.

1. Run the appropriate command to load the environment variables into your terminal session from the file created in a previous step.

    **Bash**
    ```bash
    source .env
    ```

    **PowerShell**
    ```powershell
    . .\.env.ps1
    ```

    >**Note:** Keep the terminal open. If you close it and create a new terminal, you might need to run the command to create the environment variable again.


## Create an Azure Database for PostgreSQL server

Start by creating a PostgreSQL server using the Azure CLI.

1. Open a terminal and sign in to Azure:

    ```azurecli
    az login
    ```

1. Create a resource group for this exercise:

    ```azurecli
    az group create \
        --name rg-agent-backend \
        --location eastus
    ```

1. Create the PostgreSQL server. Replace `<unique-server-name>` with a globally unique name and `<your-password>` with a strong password:

    ```azurecli
    az postgres flexible-server create \
        --resource-group rg-agent-backend \
        --name <unique-server-name> \
        --location eastus \
        --admin-user agentadmin \
        --admin-password <your-password> \
        --sku-name Standard_B1ms \
        --tier Burstable \
        --storage-size 32 \
        --version 16 \
        --public-access 0.0.0.0-255.255.255.255
    ```

    The `--public-access` parameter allows connections from any IP address for this exercise. In production, restrict access to specific IP ranges or use private networking.

1. Note the server name and admin credentials. You need them to connect.

## Configure firewall rules

The server creation command configured public access. Verify the firewall rules allow your client IP:

1. Check your current public IP address:

    ```bash
    curl ifconfig.me
    ```

1. Add a firewall rule for your IP if needed:

    ```azurecli
    az postgres flexible-server firewall-rule create \
        --resource-group rg-agent-backend \
        --name <unique-server-name> \
        --rule-name AllowMyIP \
        --start-ip-address <your-ip> \
        --end-ip-address <your-ip>
    ```

## Connect using psql and verify connectivity

Test the connection using the `psql` command-line tool.

1. Connect to the server:

    ```bash
    psql "host=<unique-server-name>.postgres.database.azure.com port=5432 dbname=postgres user=agentadmin sslmode=require"
    ```

1. Enter your password when prompted.

1. Verify the connection by checking the PostgreSQL version:

    ```sql
    SELECT version();
    ```

1. You should see output showing the PostgreSQL version. Keep this connection open for the next steps.

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

Create Python functions that an AI agent can call to persist and retrieve state. These functions serve as the agent's interface to the database.

1. Create a new directory for your project and navigate to it:

    ```bash
    mkdir agent-backend && cd agent-backend
    ```

1. Create a virtual environment and activate it:

    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

1. Install the required packages:

    ```bash
    pip install "psycopg[binary]" python-dotenv
    ```

1. Create a `.env` file with your connection details:

    ```
    DB_HOST=<unique-server-name>.postgres.database.azure.com
    DB_NAME=agent_memory
    DB_USER=agentadmin
    DB_PASSWORD=<your-password>
    ```

1. Create a file named `agent_tools.py` with the following code:

    ```python
    import os
    import uuid
    from datetime import datetime
    from typing import Optional
    import psycopg
    from dotenv import load_dotenv

    load_dotenv()

    def get_connection():
        """Create a database connection."""
        return psycopg.connect(
            host=os.environ["DB_HOST"],
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            sslmode="require"
        )

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
    ```

1. The `save_task_state` function uses `ON CONFLICT`, which requires a unique constraint. Go back to your `psql` session and add it:

    ```sql
    ALTER TABLE task_checkpoints
    ADD CONSTRAINT unique_conversation_task
    UNIQUE (conversation_id, task_name);
    ```

## Test the agent memory workflow

Create a test script to verify the tool functions work correctly.

1. Create a file named `test_workflow.py`:

    ```python
    from agent_tools import (
        create_conversation,
        store_message,
        get_conversation_history,
        save_task_state,
        get_task_state
    )

    def test_agent_workflow():
        print("=== Testing Agent Memory Backend ===\n")

        # Step 1: Create a new conversation
        print("1. Creating conversation...")
        conv = create_conversation(
            user_id="user_123",
            metadata={"source": "web", "model": "gpt-4"}
        )
        print(f"   Created conversation: {conv}\n")
        conversation_id = conv["conversation_id"]

        # Step 2: Store messages simulating an agent interaction
        print("2. Storing messages...")
        messages = [
            ("system", "You are a helpful research assistant."),
            ("user", "Can you help me find information about PostgreSQL?"),
            ("assistant", "I'd be happy to help you research PostgreSQL. Let me search for relevant information."),
            ("tool", '{"tool": "search", "results": ["PostgreSQL documentation", "PostgreSQL tutorial"]}'),
            ("assistant", "I found some resources about PostgreSQL. The official documentation is a great starting point.")
        ]

        for role, content in messages:
            result = store_message(conversation_id, role, content)
            print(f"   Stored {role} message: {result}")
        print()

        # Step 3: Save task state (agent checkpoint)
        print("3. Saving task checkpoint...")
        task_result = save_task_state(
            conversation_id=conversation_id,
            task_name="research_postgresql",
            status="in_progress",
            checkpoint_data={
                "step": 2,
                "sources_found": 2,
                "next_action": "summarize_findings"
            }
        )
        print(f"   Saved checkpoint: {task_result}\n")

        # Step 4: Retrieve conversation history
        print("4. Retrieving conversation history...")
        history = get_conversation_history(conversation_id, limit=10)
        print(f"   Found {len(history)} messages:")
        for msg in history:
            print(f"   - [{msg['role']}]: {msg['content'][:50]}...")
        print()

        # Step 5: Retrieve task state
        print("5. Retrieving task state...")
        state = get_task_state(conversation_id, "research_postgresql")
        print(f"   Current state: {state}\n")

        # Step 6: Update task state (simulating progress)
        print("6. Updating task state to completed...")
        final_state = save_task_state(
            conversation_id=conversation_id,
            task_name="research_postgresql",
            status="completed",
            checkpoint_data={
                "step": 3,
                "sources_found": 2,
                "summary": "PostgreSQL is an advanced open-source database."
            }
        )
        print(f"   Updated checkpoint: {final_state}\n")

        # Verify final state
        print("7. Verifying final state...")
        final = get_task_state(conversation_id, "research_postgresql")
        print(f"   Final status: {final['status']}")
        print(f"   Checkpoint data: {final['checkpoint_data']}")

        print("\n=== All tests completed successfully! ===")

    if __name__ == "__main__":
        test_agent_workflow()
    ```

1. Run the test script:

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

- Created an Azure Database for PostgreSQL server using the Azure CLI
- Configured network access with firewall rules
- Designed a schema for storing agent conversation history and task state
- Built Python functions that serve as tools for an AI agent to read and write state
- Tested the complete workflow of creating conversations, storing messages, and managing task checkpoints
- Queried the data to support agent context retrieval and decision-making

This pattern provides a foundation for building AI agents that maintain persistent memory across sessions and can resume interrupted tasks.
