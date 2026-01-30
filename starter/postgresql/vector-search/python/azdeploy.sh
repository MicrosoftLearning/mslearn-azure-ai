#!/usr/bin/env bash

# Change the values of these variables as needed

rg="<your-resource-group-name>"  # Resource Group name
location="<your-azure-region>"   # Azure region for the resources

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

# Generate consistent hash from Azure user object ID (based on az login account)
user_object_id=$(az ad signed-in-user show --query "id" -o tsv 2>/dev/null)
if [ -z "$user_object_id" ]; then
    echo "Error: Not authenticated with Azure. Please run: az login"
    exit 1
fi
user_hash=$(echo -n "$user_object_id" | sha1sum | cut -c1-8)
server_name="psql-vector-${user_hash}"

# Function to create resource group if it doesn't exist
create_resource_group() {
    echo "Checking/creating resource group '$rg'..."

    local exists=$(az group exists --name $rg)
    if [ "$exists" = "false" ]; then
        az group create --name $rg --location $location > /dev/null 2>&1
        echo "✓ Resource group created: $rg"
    else
        echo "✓ Resource group already exists: $rg"
    fi
}

# Function to create Azure Database for PostgreSQL Flexible Server
create_postgres_server() {
    echo "Creating Azure Database for PostgreSQL Flexible Server '$server_name'..."
    echo "This may take several minutes..."

    local server_exists=$(az postgres flexible-server show --resource-group $rg --name $server_name 2>/dev/null)
    if [ -z "$server_exists" ]; then
        az postgres flexible-server create \
            --resource-group $rg \
            --name $server_name \
            --location $location \
            --sku-name Standard_B1ms \
            --tier Burstable \
            --storage-size 32 \
            --version 16 \
            --public-access 0.0.0.0-255.255.255.255 \
            --microsoft-entra-auth Enabled \
            --password-auth Disabled > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ PostgreSQL server created successfully"

            # Allow-list the vector extension
            echo "Configuring vector extension..."
            az postgres flexible-server parameter set \
                --resource-group $rg \
                --server-name $server_name \
                --name azure.extensions \
                --value vector > /dev/null 2>&1

            if [ $? -eq 0 ]; then
                echo "✓ Vector extension allowed"
            fi

            echo "  Use option 2 to configure Microsoft Entra administrator."
        else
            echo "Error: Failed to start PostgreSQL server deployment"
            return 1
        fi
    else
        echo "✓ PostgreSQL server already exists: $server_name"
    fi
}

# Function to configure Microsoft Entra admin
configure_entra_admin() {
    echo "Configuring Microsoft Entra administrator..."

    # Prereq check: PostgreSQL server must exist
    local state=$(az postgres flexible-server show --resource-group $rg --name $server_name --query "state" -o tsv 2>/dev/null)
    if [ -z "$state" ]; then
        echo "Error: PostgreSQL server '$server_name' not found."
        echo "Please run option 1 to create the PostgreSQL server, then try again."
        return 1
    fi

    # Prereq check: Server must be in Ready state
    if [ "$state" != "Ready" ]; then
        echo "Error: PostgreSQL server is not ready (current state: $state)."
        echo "Please wait for deployment to complete. Use option 3 to check status."
        return 1
    fi

    # Get the signed-in user's UPN (object ID already retrieved at startup)
    local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)

    if [ -z "$user_object_id" ] || [ -z "$user_upn" ]; then
        echo "Error: Unable to retrieve signed-in user information."
        echo "Please ensure you are logged in with 'az login'."
        return 1
    fi

    echo "Setting '$user_upn' as Entra administrator..."

    az postgres flexible-server microsoft-entra-admin create \
        --resource-group $rg \
        --server-name $server_name \
        --display-name "$user_upn" \
        --object-id "$user_object_id" > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        echo "✓ Microsoft Entra administrator configured: $user_upn"
    else
        echo "Error: Failed to configure Entra administrator"
        return 1
    fi
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    echo ""

    # Check PostgreSQL server
    echo "PostgreSQL Server ($server_name):"
    local state=$(az postgres flexible-server show --resource-group $rg --name $server_name --query "state" -o tsv 2>/dev/null)

    if [ -z "$state" ]; then
        echo "  Status: Not created"
    else
        echo "  Status: $state"
        if [ "$state" = "Ready" ]; then
            echo "  ✓ PostgreSQL server is ready"
        fi

        # Check Entra admin configuration
        local admin_name=$(az postgres flexible-server microsoft-entra-admin list --resource-group $rg --server-name $server_name --query "[0].principalName" -o tsv 2>/dev/null)
        if [ -n "$admin_name" ]; then
            echo "  ✓ Entra administrator: $admin_name"
        else
            echo "  ⚠ Entra administrator not configured"
        fi
    fi
}

# Function to retrieve connection info and set environment variables
retrieve_connection_info() {
    echo "Retrieving connection information..."

    # Prereq check: PostgreSQL server must exist
    local state=$(az postgres flexible-server show --resource-group $rg --name $server_name --query "state" -o tsv 2>/dev/null)
    if [ -z "$state" ]; then
        echo "Error: PostgreSQL server '$server_name' not found."
        echo "Please run option 1 to create the PostgreSQL server, then try again."
        return 1
    fi

    # Prereq check: Server must be in Ready state
    if [ "$state" != "Ready" ]; then
        echo "Error: PostgreSQL server is not ready (current state: $state)."
        echo "Please wait for deployment to complete. Use option 3 to check status."
        return 1
    fi

    # Prereq check: Entra admin must be configured
    local admin_name=$(az postgres flexible-server microsoft-entra-admin list --resource-group $rg --server-name $server_name --query "[0].principalName" -o tsv 2>/dev/null)
    if [ -z "$admin_name" ]; then
        echo "Error: Microsoft Entra administrator not configured on '$server_name'."
        echo "Please run option 2 to configure the Entra administrator, then try again."
        return 1
    fi

    # Get the signed-in user's UPN for the database user
    local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)

    if [ -z "$user_upn" ]; then
        echo "Error: Unable to retrieve signed-in user information."
        echo "Please ensure you are logged in with 'az login'."
        return 1
    fi

    # Get access token for PostgreSQL
    echo "Retrieving access token..."
    local access_token=$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv 2>/dev/null)

    if [ -z "$access_token" ]; then
        echo "Error: Unable to retrieve access token."
        return 1
    fi

    # Set connection variables
    local db_host="${server_name}.postgres.database.azure.com"
    local db_name="postgres"
    local db_user="$user_upn"
    local env_file="$(dirname "$0")/.env"

    # Create or update .env file with export statements
    cat > "$env_file" << EOF
export DB_HOST="$db_host"
export DB_NAME="$db_name"
export DB_USER="$db_user"
export PGPASSWORD="$access_token"
EOF

    echo ""
    echo "PostgreSQL Connection Information"
    echo "==========================================================="
    echo "Host: $db_host"
    echo "Database: $db_name"
    echo "User: $db_user"
    echo "Password: (Entra token - expires in ~1 hour)"
    echo ""
    echo "Environment variables saved to: $env_file"
}

# Display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    Azure Database for PostgreSQL Deployment Menu"
    echo "====================================================================="
    echo "Resource Group: $rg"
    echo "Server Name: $server_name"
    echo "Location: $location"
    echo "====================================================================="
    echo "1. Create PostgreSQL server with Entra authentication"
    echo "2. Configure Microsoft Entra administrator"
    echo "3. Check deployment status"
    echo "4. Retrieve connection info and access token"
    echo "5. Exit"
    echo "====================================================================="
}

# Main menu loop
while true; do
    show_menu
    read -p "Please select an option (1-5): " choice

    case $choice in
        1)
            echo ""
            create_resource_group
            echo ""
            create_postgres_server
            echo ""
            read -p "Press Enter to continue..."
            ;;
        2)
            echo ""
            configure_entra_admin
            echo ""
            read -p "Press Enter to continue..."
            ;;
        3)
            echo ""
            check_deployment_status
            echo ""
            read -p "Press Enter to continue..."
            ;;
        4)
            echo ""
            retrieve_connection_info
            echo ""
            read -p "Press Enter to continue..."
            ;;
        5)
            echo "Exiting..."
            clear
            exit 0
            ;;
        *)
            echo ""
            echo "Invalid option. Please select 1-5."
            echo ""
            read -p "Press Enter to continue..."
            ;;
    esac

    echo ""
done

