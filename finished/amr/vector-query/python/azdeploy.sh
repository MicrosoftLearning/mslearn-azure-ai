#!/usr/bin/env bash

# Change the values of these variables as needed

rg="rg-exercises" # Resource Group name
location="westus2" # Azure region for the resources

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

# Generate consistent hash from username (always produces valid Azure resource name)
user_hash=$(echo -n "$USER" | sha1sum | cut -c1-8)
cache_name="amr-exercise-${user_hash}"
cache_name="amr-exercise-jjkl1234" # Temporary hardcoded name for testing purposes

# Function to create Azure Managed Redis resource
create_redis_resource() {
    echo "Creating Azure Managed Redis Enterprise cluster '$cache_name'..."

    # Create the Redis Enterprise cluster (E10 is the cheapest SKU that supports modules)
    az redisenterprise create \
        --resource-group $rg \
        --name $cache_name \
        --location $location \
        --sku Enterprise_E10 \
        --public-network-access "Enabled" \
        --clustering-policy "EnterpriseCluster" \
        --eviction-policy "NoEviction" \
        --modules "name=RediSearch" \
        --no-wait

    echo "The Azure Managed Redis Enterprise cluster is being created and takes 5-10 minutes to complete."
    echo "You can check the deployment status from the menu later in the exercise."
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    az redisenterprise show --resource-group $rg --name $cache_name --query "provisioningState"
}

# Function to retrieve endpoint and access key
retrieve_endpoint_and_key() {

    echo "Enabling access key authentication to trigger key generation..."

    # Enable access key authentication on the database to trigger key generation
    az redisenterprise database update \
        --resource-group $rg \
        --cluster-name $cache_name \
        --access-keys-auth "Enabled" \
        > /dev/null

    echo "Retrieving endpoint and access key..."

    # Get the endpoint (hostname and port)
    hostname=$(az redisenterprise show --resource-group $rg --name $cache_name --query "hostName" -o tsv 2>/dev/null)

    # Get the primary access key
    primaryKey=$(az redisenterprise database list-keys --cluster-name $cache_name -g $rg --query "primaryKey" -o tsv 2>/dev/null)

    # Check if values are empty
    if [ -z "$hostname" ] || [ -z "$primaryKey" ]; then
        echo ""
        echo "Unable to retrieve endpoint or access key."
        echo "Please check the deployment status to ensure the resource is fully provisioned."
        echo "Use menu option 2 to check deployment status."
        return 1
    fi

    # Create or update .env file
    if [ -f ".env" ]; then
        # Update existing .env file
        if grep -q "^REDIS_HOST=" .env; then
            sed -i "s|^REDIS_HOST=.*|REDIS_HOST=$hostname|" .env
        else
            echo "REDIS_HOST=$hostname" >> .env
        fi

        if grep -q "^REDIS_KEY=" .env; then
            sed -i "s|^REDIS_KEY=.*|REDIS_KEY=$primaryKey|" .env
        else
            echo "REDIS_KEY=$primaryKey" >> .env
        fi
        echo "Updated existing .env file"
    else
        # Create new .env file
        echo "REDIS_HOST=$hostname" > .env
        echo "REDIS_KEY=$primaryKey" >> .env
        echo "Created new .env file"
    fi

    clear
    echo ""
    echo "Redis Connection Information"
    echo "==========================================================="
    echo "Endpoint: $hostname"
    echo "Primary Key: $primaryKey"
    echo ""
    echo "Values have been saved to .env file"
}

# Display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    Azure Managed Redis Deployment Menu"
    echo "====================================================================="
    echo "Resource Group: $rg"
    echo "Cache Name: $cache_name"
    echo "Location: $location"
    echo "====================================================================="
    echo "1. Create Azure Managed Redis resource"
    echo "2. Check deployment status"
    echo "3. Configure for search and retrieve endpoint and access key"
    echo "4. Exit"
    echo "====================================================================="
}

# Main menu loop
while true; do
    show_menu
    read -p "Please select an option (1-4): " choice

    case $choice in
        1)
            echo ""
            create_redis_resource
            echo ""
            read -p "Press Enter to continue..."
            ;;
        2)
            echo ""
            check_deployment_status
            echo ""
            read -p "Press Enter to continue..."
            ;;
        3)
            echo ""
            retrieve_endpoint_and_key
            echo ""
            read -p "Press Enter to continue..."
            ;;
        4)
            echo "Exiting..."
            clear
            exit 0
            ;;
        *)
            echo ""
            echo "Invalid option. Please select 1-4."
            echo ""
            read -p "Press Enter to continue..."
            ;;
    esac

    echo ""
done

