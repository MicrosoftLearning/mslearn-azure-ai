# AI Agent / Copilot Instructions

This file documents the development environment for AI agents working on this repository.

## Key Information for Agents

### Development Tools
- **Package Manager**: uv (not pip or poetry)
- **Environment**: WSL2 (Windows Subsystem for Linux)
- **Python Version**: 3.12+ (see project's `pyproject.toml`)
- **Shell**: bash in WSL

### File System Paths
When executing commands, use WSL paths:
- Windows path: `C:\LabGit\mslearn-azure-ai\`
- WSL path: `/mnt/c/LabGit/mslearn-azure-ai/`
- Always use `/mnt/c/` prefix for Windows drive access in WSL

### Running Python Commands

**ALWAYS use uv syntax:**
```bash
# Correct (WSL path, uv command)
cd /mnt/c/LabGit/mslearn-azure-ai/finished/amr/vector-query/python
uv run python script.py

# Correct (alternative)
uv run --python 3.12 python script.py
```

**DO NOT use:**
```bash
python script.py          # Wrong - no uv
python3 script.py         # Wrong - no uv
pip install package      # Wrong - use uv add instead
```

### Testing Python Code
```bash
# Test imports
uv run python -c "import module_name; print('OK')"

# Run a script
uv run python script.py

# Interactive REPL
uv run python
```

### Adding Dependencies
```bash
cd /path/to/project
uv add package_name        # Add dependency
uv add package_name==1.0   # Specific version
uv sync                    # Install from lock file
```

### Project Structure Recognition
When working on Python projects, look for:
- `pyproject.toml` → Project config and dependency list
- `uv.lock` → Locked versions (commit this!)
- `.venv/` → Virtual environment (auto-managed by uv, ignore)
- `requirements.txt` → Legacy format (reference only, not used)

### Common Patterns in This Repo

#### Vector/Embeddings Projects
- Located in: `finished/amr/vector-query/python/`
- Key files: `manage_vector.py`, `vectorapp.py`, `sample_data.json`
- Dependencies: `redis>=7.0.1`, `numpy>=1.24.0`, `python-dotenv`
- Entry point: `uv run python vectorapp.py`

#### Environment Variables
- Use `.env` file (load with `python-dotenv`)
- Never commit `.env` files
- Required for: Azure credentials, API keys, connection strings

### Debugging Tips

**Import errors with redis:**
```bash
# Correct import path (snake_case, not camelCase)
from redis.commands.search.index_definition import IndexDefinition, IndexType
```

**WSL path errors:**
```bash
# Use /mnt/c/ for Windows paths in WSL
cd /mnt/c/LabGit/mslearn-azure-ai/finished/...
```

**Module not found:**
```bash
# Clear and resync dependencies
rm -rf .venv/
uv sync
```

### Code Review Checklist
When reviewing Python files:
- ✓ Uses `uv run python` syntax in examples/docs
- ✓ Uses WSL paths (`/mnt/c/...`) not Windows paths
- ✓ Imports use correct case (`index_definition`, not `indexDefinition`)
- ✓ `pyproject.toml` lists all dependencies (no bare `pip` commands)
- ✓ Comments explain product/business logic, not just what code does
- ✓ Function names are product-centric (e.g., `store_product` not `store_vector`)

### Environment Persistence
Remember across conversations:
- This project uses **uv** (always)
- This project uses **WSL2** (always)
- Python projects here follow uv conventions
- Use `/mnt/c/` paths in WSL commands

### Quick Reference
| Task | Command |
|------|---------|
| Run script | `uv run python script.py` |
| Add package | `uv add package_name` |
| Sync dependencies | `uv sync` |
| Check version | `uv run python --version` |
| List packages | `uv run pip list` |
| Test import | `uv run python -c "import pkg"` |
