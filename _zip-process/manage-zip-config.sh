#!/bin/bash

# Zip Configuration Management Script
# Usage: ./manage-zip-config.sh [add|remove|list|validate]

CONFIG_FILE="zip-config.json"

# Function to validate JSON
validate_json() {
    if command -v jq >/dev/null 2>&1; then
        jq empty "$CONFIG_FILE" 2>/dev/null
        return $?
    else
        echo "Warning: jq not found. Cannot validate JSON syntax."
        return 0
    fi
}

# Function to list current configuration
list_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "Configuration file not found: $CONFIG_FILE"
        return 1
    fi
    
    echo "Current zip configuration:"
    echo "=========================="
    
    if command -v jq >/dev/null 2>&1; then
        jq -r '.folders[] | "Source: \(.source) → Output: \(.output)/\(.name)"' "$CONFIG_FILE"
    else
        cat "$CONFIG_FILE"
    fi
}

# Function to add new folder configuration
add_folder() {
    read -p "Enter source folder path: " source_path
    read -p "Enter output folder path: " output_path
    read -p "Enter zip file name (with .zip extension): " zip_name
    
    # Validate inputs
    if [ -z "$source_path" ] || [ -z "$output_path" ] || [ -z "$zip_name" ]; then
        echo "Error: All fields are required"
        return 1
    fi
    
    if [[ "$zip_name" != *.zip ]]; then
        echo "Warning: Adding .zip extension to filename"
        zip_name="${zip_name}.zip"
    fi
    
    # Create config file if it doesn't exist
    if [ ! -f "$CONFIG_FILE" ]; then
        echo '{"description": "Configuration for automatic folder zipping workflow", "folders": []}' > "$CONFIG_FILE"
    fi
    
    # Add new folder entry
    if command -v jq >/dev/null 2>&1; then
        temp_file=$(mktemp)
        jq --arg source "$source_path" --arg output "$output_path" --arg name "$zip_name" \
           '.folders += [{"source": $source, "output": $output, "name": $name}]' \
           "$CONFIG_FILE" > "$temp_file" && mv "$temp_file" "$CONFIG_FILE"
        
        echo "✅ Added: $source_path → $output_path/$zip_name"
    else
        echo "Error: jq is required to modify JSON configuration"
        return 1
    fi
}

# Function to remove folder configuration
remove_folder() {
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "Configuration file not found: $CONFIG_FILE"
        return 1
    fi
    
    echo "Current folders:"
    if command -v jq >/dev/null 2>&1; then
        jq -r '.folders[] | @base64' "$CONFIG_FILE" | while IFS= read -r folder_data; do
            folder_info=$(echo "$folder_data" | base64 -d)
            source_path=$(echo "$folder_info" | jq -r '.source')
            echo "- $source_path"
        done
    fi
    
    read -p "Enter source folder path to remove: " source_to_remove
    
    if command -v jq >/dev/null 2>&1; then
        temp_file=$(mktemp)
        jq --arg source "$source_to_remove" '.folders = [.folders[] | select(.source != $source)]' \
           "$CONFIG_FILE" > "$temp_file" && mv "$temp_file" "$CONFIG_FILE"
        
        echo "✅ Removed folder: $source_to_remove"
    else
        echo "Error: jq is required to modify JSON configuration"
        return 1
    fi
}

# Main script logic
case "${1:-list}" in
    "add")
        add_folder
        ;;
    "remove")
        remove_folder
        ;;
    "list")
        list_config
        ;;
    "validate")
        if validate_json; then
            echo "✅ Configuration file is valid JSON"
        else
            echo "❌ Configuration file has invalid JSON syntax"
            exit 1
        fi
        ;;
    *)
        echo "Usage: $0 [add|remove|list|validate]"
        echo ""
        echo "Commands:"
        echo "  add      - Add new folder to zip configuration"
        echo "  remove   - Remove folder from zip configuration"
        echo "  list     - List current configuration (default)"
        echo "  validate - Validate JSON syntax"
        exit 1
        ;;
esac