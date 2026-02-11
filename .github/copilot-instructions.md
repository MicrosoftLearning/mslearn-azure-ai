# Copilot Instructions for mslearn-azure-ai

## General Rules

### Starter Folder

Never browse, read, or reference files in the `starter/` folder unless the user explicitly asks you to. The starter folder contains incomplete versions of exercises and should not be used as a reference for patterns, code, or structure.

### Deleted Files

If a file you previously worked on during the current session has been deleted, ask the user before re-creating it. Do not automatically recreate deleted files.

## Writing Exercise Instructions

### Inline Code Usage

Do not use inline code formatting (backticks) in exercise instructions except when:

1. **Commands the student must run** - e.g., `az login`, `pip install psycopg`

Avoid using inline code for:
- General technical terms (PostgreSQL, Microsoft Entra, Azure CLI)
- Describing concepts or features
- Menu options or UI elements (use **bold** instead)
- File names (use *italics* instead)
- Referencing commands, environment variables, or syntax in prose or notes (use **bold** instead)

### When to Use Bold vs Inline Code

- Use inline code only when the student must literally type, enter, or copy the value
  - Example: "Open this URL in your browser: `https://portal.azure.com`"
- Use **bold** when referencing commands, variables, or syntax in explanatory text
  - Example: "The **PGPASSWORD** environment variable is automatically used for authentication."
  - Example: "After running the script, use the **source** command to load variables."

### File Names

Use italics for file names in prose - e.g., *azdeploy.sh*, *agent_tools.py*, *.env*

### Command Steps

Steps that direct a student to run a command should:

1. Start with "Run the following command to **<do something>**."
2. Follow with a brief explanation of what the command does

Example:
```
1. Run the following command to load the environment variables into your terminal session. This command exports the variables from the *.env* file so they are available to subsequent commands and scripts.

    ```bash
    source .env
    ```
```

### Section Introductions

Each section (## heading) should begin with an introductory sentence that follows the pattern "In this section you..." followed by a clear explanation of what the student will accomplish and why.

Example:
```
## Create the agent memory schema

In this section you design and create the database schema that stores conversation history and task state. The schema includes three tables: one for conversations (agent sessions), one for messages within those conversations, and one for task checkpoints that enable the agent to resume interrupted work.
```

### Clean Up Resources Section

Always use the following exact verbiage for the clean up resources section at the end of exercises:

```markdown
# Clean up resources

Now that you finished the exercise, you should delete the cloud resources you created to avoid unnecessary resource usage.

1. Run the following command in the VS Code terminal to delete the resource group, and all resources in the group. Replace **\<rg-name>** with the name you choose earlier in the exercise. The command will launch a background task in Azure to delete the resource group.

    ```
    az group delete --name <rg-name> --no-wait --yes
    ```

> **CAUTION:** Deleting a resource group deletes all resources contained within it. If you chose an existing resource group for this exercise, any existing resources outside the scope of this exercise will also be deleted.
```

### Deployment Scripts (azdeploy.sh / azdeploy.ps1)

When updating deployment scripts for new exercises:

1. **Never modify the first 11 lines** - The header section with variable declarations (`rg`, `location`) and comments must remain unchanged.

2. **Preserve existing patterns** - Do not rewrite functions that don't need changes. Only modify:
   - Resource names and variables below line 11
   - Service-specific creation/configuration functions
   - Menu items and descriptions
   - Status check logic for the new services

3. **Follow established conventions**:
   - Use `> /dev/null 2>&1` for output suppression (not `--output none`)
   - Check if resources exist before creating them
   - Use checkmarks (✓) for success and warnings (⚠) for incomplete states
   - Use "Error: ..." prefix for error messages
   - Use `local` for function-scoped variables
   - Generate unique resource names using Azure user object ID hash
   - Include Azure auth check at script startup

4. **Reference scripts** - Use existing scripts in the repository as templates. Good examples:
   - *finished/azure-container-apps/scale-container-aca/python/azdeploy.sh*

5. **When asked to update a copied script**:
   - First review the source script to understand existing patterns
   - Only modify service-specific logic (create, configure, status check functions)
   - Keep the menu loop structure, resource group function, and env file patterns intact
   - Update variable names and menu text to match the new exercise

### Azure CLI Commands

Before answering questions about Azure CLI commands, generating CLI commands, or updating content that includes CLI commands:

1. **Always verify command syntax** - Use MCP tools or official documentation to confirm:
   - Available parameters and their correct names
   - Required vs optional parameters
   - Valid parameter values (case sensitivity matters, e.g., `Enabled` not `enabled`)
   - Whether parameters like `--no-wait` are actually supported for that specific command

2. **Check for deprecated commands** - Azure CLI commands change over time:
   - `ad-admin` commands were replaced by `microsoft-entra-admin`
   - `--active-directory-auth` was replaced by `--microsoft-entra-auth`
   - Always verify the current recommended command

3. **Use available tools** - When in doubt:
   - Run `az <command> --help` in the terminal to see actual available options
   - Fetch the official Microsoft Learn documentation for the command
   - Don't assume a parameter exists just because it seems logical
