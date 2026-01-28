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
