# Auto-Zip Workflow System

This system automatically creates zip files for specified folders when their contents change, using GitHub Actions workflows.

## How It Works

1. **Configuration File**: `zip-config.json` defines which folders to monitor and where to output zip files
2. **GitHub Workflow**: `.github/workflows/auto-zip.yml` monitors for changes and creates zip files
3. **Management Scripts**: Helper scripts to easily manage the configuration

## Configuration File Format

The `_zip-process/zip-config.json` file contains:

```json
{
  "description": "Configuration for automatic folder zipping workflow",
  "folders": [
    {
      "source": "path/to/source/folder",
      "output": "path/to/output/folder", 
      "name": "output-filename.zip"
    }
  ]
}
```

### Fields:
- **source**: Path to the folder to zip (relative to repository root)
- **output**: Path where the zip file should be created (relative to repository root)
- **name**: Name of the zip file (must include .zip extension)

## Workflow Triggers

The workflow runs when:
- Changes are pushed to monitored folders
- The `_zip-process/zip-config.json` file is modified
- Manually triggered via GitHub Actions interface

## Smart Change Detection

The workflow only creates zip files for folders that have actually changed:
- Compares current commit with previous commit
- Only processes folders with detected changes
- Saves processing time and avoids unnecessary commits

## Management Scripts

### PowerShell (Windows)
```powershell
# Navigate to zip process folder
cd _zip-process

# List current configuration
.\manage-zip-config.ps1 list

# Add new folder
.\manage-zip-config.ps1 add

# Remove folder
.\manage-zip-config.ps1 remove

# Validate JSON syntax
.\manage-zip-config.ps1 validate
```

### Bash (Linux/macOS/WSL)
```bash
# Navigate to zip process folder
cd _zip-process

# Make script executable (first time only)
chmod +x manage-zip-config.sh

# List current configuration
./manage-zip-config.sh list

# Add new folder
./manage-zip-config.sh add

# Remove folder
./manage-zip-config.sh remove

# Validate JSON syntax
./manage-zip-config.sh validate
```

## Example Usage

1. **Add a new folder to monitor:**
   ```powershell
   cd _zip-process
   .\manage-zip-config.ps1 add
   ```
   Then enter:
   - Source: `src/my-project`
   - Output: `downloads/projects`
   - Name: `my-project.zip`

2. **Make changes to the monitored folder:**
   - Edit files in `src/my-project`
   - Commit and push changes

3. **Automatic processing:**
   - Workflow detects changes in `src/my-project`
   - Creates `downloads/projects/my-project.zip`
   - Commits the zip file back to repository

## Workflow Features

- **Exclusions**: Automatically excludes common unwanted files:
  - `.git*` files
  - `.DS_Store` files
  - `__pycache__` directories
  - `.pyc` files

- **Directory Creation**: Automatically creates output directories if they don't exist

- **Commit Message**: Uses `[skip ci]` to prevent infinite workflow loops

- **Error Handling**: Validates source folders exist before processing

## Example Configuration

```json
{
  "description": "Configuration for automatic folder zipping workflow",
  "folders": [
    {
      "source": "src/amr/python",
      "output": "downloads/python",
      "name": "amr-python-code.zip"
    },
    {
      "source": "finished/amr/data-operations/dotnet",
      "output": "downloads/dotnet", 
      "name": "amr-dotnet-code.zip"
    },
    {
      "source": "instructions/compute-containers",
      "output": "downloads/instructions",
      "name": "container-instructions.zip"
    }
  ]
}
```

## Monitoring Multiple Folders

You can monitor as many folders as needed. The workflow will:
- Only process folders that have changes
- Create separate zip files for each configured folder
- Handle multiple output directories automatically

## Manual Execution

To manually run the workflow:
1. Go to GitHub Actions in your repository
2. Select "Auto-Zip Changed Folders" workflow
3. Click "Run workflow"
4. This will process ALL configured folders regardless of changes

## Troubleshooting

1. **Workflow not triggering:**
   - Check that changes are in monitored paths
   - Verify `zip-config.json` is valid JSON

2. **Zip files not created:**
   - Check workflow logs in GitHub Actions
   - Verify source folders exist
   - Check for permission issues

3. **Invalid configuration:**
   - Run validation: `cd _zip-process && .\manage-zip-config.ps1 validate`
   - Check JSON syntax with online validators

## File Structure After Setup

```
your-repo/
├── .github/
│   └── workflows/
│       └── auto-zip.yml
├── _zip-process/        # Auto-zip configuration folder
│   ├── zip-config.json
│   ├── manage-zip-config.ps1
│   ├── manage-zip-config.sh
│   └── AUTO-ZIP-README.md
├── downloads/           # Output directory (created automatically)
│   ├── python/
│   ├── dotnet/
│   └── instructions/
└── your-source-folders/
```