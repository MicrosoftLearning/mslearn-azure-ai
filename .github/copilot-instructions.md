# Copilot Instructions for mslearn-azure-ai

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
