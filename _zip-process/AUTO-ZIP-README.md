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
      "source": "starter/amr/data-operations/python",
      "output": "downloads/python",
      "name": "amr-data-operations-python.zip"
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

## Workflow Features

- **Exclusions**: Automatically excludes common unwanted files:
  - `.git*` files
  - `.DS_Store` files
  - `__pycache__` directories
  - `.pyc` files

- **Directory Creation**: Automatically creates output directories if they don't exist

- **Commit Message**: Uses `[skip ci]` to prevent infinite workflow loops

- **Error Handling**: Validates source folders exist before processing

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
   - Check JSON syntax with online validators

