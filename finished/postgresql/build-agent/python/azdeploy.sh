#!/usr/bin/env bash

# Change the values of these variables as needed

# rg="<your-resource-group-name>"  # Resource Group name
# location="<your-azure-region>"   # Azure region for the resources

rg="rg-exercises"           # Resource Group name
location="eastus2"          # Azure region for the resources

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

# Generate consistent hash from username (always produces valid Azure resource name)
user_hash=$(echo -n "$USER" | sha1sum | cut -c1-8)
server_name="psql-agent-${user_hash}"

# Function to create resource group
create_resource_group() {
    echo "Creating resource group '$rg' in '$location'..."
    az group create --name $rg --location $location --output none
    echo "Resource group created."
}

# Function to create Azure Database for PostgreSQL Flexible Server
create_postgres_server() {
    echo "Creating Azure Database for PostgreSQL Flexible Server '$server_name'..."
    echo "This may take several minutes..."

    az postgres flexible-server create \
        --resource-group $rg \
        --name $server_name \
        --location $location \
        --sku-name Standard_B1ms \
        --tier Burstable \
        --storage-size 32 \
        --version 16 \
        --public-access 0.0.0.0-255.255.255.255 \
        --active-directory-auth Enabled \
        --password-auth Disabled \
        --output none

    if [ $? -eq 0 ]; then
        echo ""
        echo "PostgreSQL server created successfully."
        echo "Server name: $server_name"
    else
        echo ""
        echo "Failed to create PostgreSQL server."
        return 1
    fi
}

# Function to configure Microsoft Entra admin
configure_entra_admin() {
    echo "Configuring Microsoft Entra administrator..."

    # Get the signed-in user's object ID and UPN
    user_object_id=$(az ad signed-in-user show --query id -o tsv 2>/dev/null)
    user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)

    if [ -z "$user_object_id" ] || [ -z "$user_upn" ]; then
        echo ""
        echo "Unable to retrieve signed-in user information."
        echo "Please ensure you are logged in with 'az login'."
        return 1
    fi

    echo "Setting '$user_upn' as Entra administrator..."

    az postgres flexible-server ad-admin create \
        --resource-group $rg \
        --server-name $server_name \
        --display-name "$user_upn" \
        --object-id "$user_object_id" \
        --type User \
        --output none

    if [ $? -eq 0 ]; then
        echo ""
        echo "Microsoft Entra administrator configured successfully."
        echo "Admin: $user_upn"
    else
        echo ""
        echo "Failed to configure Entra administrator."
        return 1
    fi
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking PostgreSQL server status..."
    state=$(az postgres flexible-server show --resource-group $rg --name $server_name --query "state" -o tsv 2>/dev/null)

    if [ -z "$state" ]; then
        echo "Server not found. Please create the server first."
    else
        echo "Server state: $state"
    fi
}

# Function to retrieve connection info and set environment variables
retrieve_connection_info() {
    echo "Retrieving connection information..."

    # Get the signed-in user's UPN for the database user
    user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)

    if [ -z "$user_upn" ]; then
        echo ""
        echo "Unable to retrieve signed-in user information."
        echo "Please ensure you are logged in with 'az login'."
        return 1
    fi

    # Get access token for PostgreSQL
    echo "Retrieving access token..."
    access_token=$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv 2>/dev/null)

    if [ -z "$access_token" ]; then
        echo ""
        echo "Unable to retrieve access token."
        return 1
    fi

    # Set connection variables
    db_host="${server_name}.postgres.database.azure.com"
    db_name="postgres"
    db_user="$user_upn"

    # Create or update .env file with export statements
    cat > .env << EOF
export DB_HOST="$db_host"
export DB_NAME="$db_name"
export DB_USER="$db_user"
export PGPASSWORD="$access_token"
EOF

    clear
    echo ""
    echo "PostgreSQL Connection Information"
    echo "==========================================================="
    echo "Host: $db_host"
    echo "Database: $db_name"
    echo "User: $db_user"
    echo "Password: (Entra token - expires in ~1 hour)"
    echo ""
    echo "Environment variables saved to .env file."
    echo ""
    echo "Run 'source .env' to load the variables into your terminal."
    echo ""
    echo "To connect with psql:"
    echo "  psql \"host=\$DB_HOST port=5432 dbname=\$DB_NAME user=\$DB_USER sslmode=require\""
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

