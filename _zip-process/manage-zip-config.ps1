# Zip Configuration Management Script (PowerShell)
# Usage: .\manage-zip-config.ps1 [add|remove|list|validate]

param(
    [string]$Action = "list"
)

$ConfigFile = "zip-config.json"

# Function to validate JSON
function Test-JsonSyntax {
    param([string]$FilePath)
    
    try {
        if (Test-Path $FilePath) {
            Get-Content $FilePath | ConvertFrom-Json | Out-Null
            return $true
        }
        return $false
    }
    catch {
        return $false
    }
}

# Function to list current configuration
function Show-Configuration {
    if (-not (Test-Path $ConfigFile)) {
        Write-Host "Configuration file not found: $ConfigFile" -ForegroundColor Red
        return
    }
    
    Write-Host "Current zip configuration:" -ForegroundColor Green
    Write-Host "==========================" -ForegroundColor Green
    
    try {
        $config = Get-Content $ConfigFile | ConvertFrom-Json
        foreach ($folder in $config.folders) {
            Write-Host "Source: $($folder.source) → Output: $($folder.output)/$($folder.name)" -ForegroundColor White
        }
    }
    catch {
        Write-Host "Error reading configuration file: $_" -ForegroundColor Red
    }
}

# Function to add new folder configuration
function Add-FolderConfig {
    $sourcePath = Read-Host "Enter source folder path"
    $outputPath = Read-Host "Enter output folder path"
    $zipName = Read-Host "Enter zip file name (with .zip extension)"
    
    # Validate inputs
    if ([string]::IsNullOrWhiteSpace($sourcePath) -or 
        [string]::IsNullOrWhiteSpace($outputPath) -or 
        [string]::IsNullOrWhiteSpace($zipName)) {
        Write-Host "Error: All fields are required" -ForegroundColor Red
        return
    }
    
    if (-not $zipName.EndsWith(".zip")) {
        Write-Host "Warning: Adding .zip extension to filename" -ForegroundColor Yellow
        $zipName = "$zipName.zip"
    }
    
    # Create config file if it doesn't exist
    if (-not (Test-Path $ConfigFile)) {
        $defaultConfig = @{
            description = "Configuration for automatic folder zipping workflow"
            folders = @()
        }
        $defaultConfig | ConvertTo-Json | Set-Content $ConfigFile
    }
    
    # Add new folder entry
    try {
        $config = Get-Content $ConfigFile | ConvertFrom-Json
        $newFolder = @{
            source = $sourcePath
            output = $outputPath
            name = $zipName
        }
        
        $config.folders += $newFolder
        $config | ConvertTo-Json | Set-Content $ConfigFile
        
        Write-Host "✅ Added: $sourcePath → $outputPath/$zipName" -ForegroundColor Green
    }
    catch {
        Write-Host "Error adding folder configuration: $_" -ForegroundColor Red
    }
}

# Function to remove folder configuration
function Remove-FolderConfig {
    if (-not (Test-Path $ConfigFile)) {
        Write-Host "Configuration file not found: $ConfigFile" -ForegroundColor Red
        return
    }
    
    try {
        $config = Get-Content $ConfigFile | ConvertFrom-Json
        
        Write-Host "Current folders:" -ForegroundColor Yellow
        for ($i = 0; $i -lt $config.folders.Count; $i++) {
            Write-Host "$($i + 1). $($config.folders[$i].source)" -ForegroundColor White
        }
        
        $selection = Read-Host "Enter the number of the folder to remove (or source path)"
        
        if ($selection -match '^\d+$') {
            $index = [int]$selection - 1
            if ($index -ge 0 -and $index -lt $config.folders.Count) {
                $removedFolder = $config.folders[$index]
                $config.folders = $config.folders | Where-Object { $_ -ne $config.folders[$index] }
                Write-Host "✅ Removed folder: $($removedFolder.source)" -ForegroundColor Green
            } else {
                Write-Host "Invalid selection" -ForegroundColor Red
                return
            }
        } else {
            $originalCount = $config.folders.Count
            $config.folders = $config.folders | Where-Object { $_.source -ne $selection }
            if ($config.folders.Count -lt $originalCount) {
                Write-Host "✅ Removed folder: $selection" -ForegroundColor Green
            } else {
                Write-Host "Folder not found: $selection" -ForegroundColor Red
                return
            }
        }
        
        $config | ConvertTo-Json | Set-Content $ConfigFile
    }
    catch {
        Write-Host "Error removing folder configuration: $_" -ForegroundColor Red
    }
}

# Main script logic
switch ($Action.ToLower()) {
    "add" {
        Add-FolderConfig
    }
    "remove" {
        Remove-FolderConfig
    }
    "list" {
        Show-Configuration
    }
    "validate" {
        if (Test-JsonSyntax $ConfigFile) {
            Write-Host "✅ Configuration file is valid JSON" -ForegroundColor Green
        } else {
            Write-Host "❌ Configuration file has invalid JSON syntax" -ForegroundColor Red
            exit 1
        }
    }
    default {
        Write-Host "Usage: .\manage-zip-config.ps1 [add|remove|list|validate]"
        Write-Host ""
        Write-Host "Commands:"
        Write-Host "  add      - Add new folder to zip configuration"
        Write-Host "  remove   - Remove folder from zip configuration"
        Write-Host "  list     - List current configuration (default)"
        Write-Host "  validate - Validate JSON syntax"
    }
}