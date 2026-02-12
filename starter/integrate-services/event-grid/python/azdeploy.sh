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

# Resource names with hash for uniqueness
namespace_name="egns-exercise-${user_hash}"
topic_name="moderation-events"

# Event subscription names
sub_flagged="sub-flagged"
sub_approved="sub-approved"
sub_all="sub-all-events"

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

# Function to create Event Grid namespace and topic
create_namespace_and_topic() {
    echo "Creating Event Grid namespace '$namespace_name'..."

    local ns_exists=$(az eventgrid namespace show --resource-group $rg --name $namespace_name 2>/dev/null)
    if [ -z "$ns_exists" ]; then
        az eventgrid namespace create \
            --name $namespace_name \
            --resource-group $rg \
            --location $location \
            --sku "{name:standard,capacity:1}" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Event Grid namespace created: $namespace_name"
        else
            echo "Error: Failed to create Event Grid namespace"
            return 1
        fi
    else
        echo "✓ Event Grid namespace already exists: $namespace_name"
    fi

    echo ""
    echo "Creating namespace topic '$topic_name'..."

    local topic_exists=$(az eventgrid namespace topic show --resource-group $rg --namespace-name $namespace_name --name $topic_name 2>/dev/null)
    if [ -z "$topic_exists" ]; then
        az eventgrid namespace topic create \
            --name $topic_name \
            --namespace-name $namespace_name \
            --resource-group $rg \
            --event-retention-in-days 1 \
            --publisher-type Custom \
            --input-schema CloudEventSchemaV1_0 > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Namespace topic created: $topic_name"
        else
            echo "Error: Failed to create namespace topic"
            return 1
        fi
    else
        echo "✓ Namespace topic already exists: $topic_name"
    fi
}

# Function to create event subscriptions with filters
create_event_subscriptions() {
    echo "Creating event subscriptions..."

    # Prereq check: namespace must exist
    local ns_status=$(az eventgrid namespace show --resource-group $rg --name $namespace_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -z "$ns_status" ] || [ "$ns_status" != "Succeeded" ]; then
        echo "Error: Event Grid namespace '$namespace_name' not found or not ready."
        echo "Please run option 1 first, then try again."
        return 1
    fi

    # Prereq check: topic must exist
    local topic_status=$(az eventgrid namespace topic show --resource-group $rg --namespace-name $namespace_name --name $topic_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -z "$topic_status" ] || [ "$topic_status" != "Succeeded" ]; then
        echo "Error: Namespace topic '$topic_name' not found or not ready."
        echo "Please run option 1 first, then try again."
        return 1
    fi

    # Subscription for flagged content only
    local sub_exists=$(az eventgrid namespace topic event-subscription show --resource-group $rg --namespace-name $namespace_name --topic-name $topic_name --name $sub_flagged 2>/dev/null)
    if [ -z "$sub_exists" ]; then
        az eventgrid namespace topic event-subscription create \
            --name $sub_flagged \
            --namespace-name $namespace_name \
            --resource-group $rg \
            --topic-name $topic_name \
            --delivery-configuration "{deliveryMode:Queue,queue:{receiveLockDurationInSeconds:60,maxDeliveryCount:10,eventTimeToLive:P1D}}" \
            --event-delivery-schema CloudEventSchemaV1_0 \
            --filters-configuration "{includedEventTypes:['com.contoso.ai.ContentFlagged']}" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Subscription created: $sub_flagged (ContentFlagged events only)"
        else
            echo "Error: Failed to create subscription '$sub_flagged'"
            return 1
        fi
    else
        echo "✓ Subscription already exists: $sub_flagged"
    fi

    # Subscription for approved content only
    sub_exists=$(az eventgrid namespace topic event-subscription show --resource-group $rg --namespace-name $namespace_name --topic-name $topic_name --name $sub_approved 2>/dev/null)
    if [ -z "$sub_exists" ]; then
        az eventgrid namespace topic event-subscription create \
            --name $sub_approved \
            --namespace-name $namespace_name \
            --resource-group $rg \
            --topic-name $topic_name \
            --delivery-configuration "{deliveryMode:Queue,queue:{receiveLockDurationInSeconds:60,maxDeliveryCount:10,eventTimeToLive:P1D}}" \
            --event-delivery-schema CloudEventSchemaV1_0 \
            --filters-configuration "{includedEventTypes:['com.contoso.ai.ContentApproved']}" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Subscription created: $sub_approved (ContentApproved events only)"
        else
            echo "Error: Failed to create subscription '$sub_approved'"
            return 1
        fi
    else
        echo "✓ Subscription already exists: $sub_approved"
    fi

    # Subscription for all events (no filter — audit log)
    sub_exists=$(az eventgrid namespace topic event-subscription show --resource-group $rg --namespace-name $namespace_name --topic-name $topic_name --name $sub_all 2>/dev/null)
    if [ -z "$sub_exists" ]; then
        az eventgrid namespace topic event-subscription create \
            --name $sub_all \
            --namespace-name $namespace_name \
            --resource-group $rg \
            --topic-name $topic_name \
            --delivery-configuration "{deliveryMode:Queue,queue:{receiveLockDurationInSeconds:60,maxDeliveryCount:10,eventTimeToLive:P1D}}" \
            --event-delivery-schema CloudEventSchemaV1_0 > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Subscription created: $sub_all (all events — audit log)"
        else
            echo "Error: Failed to create subscription '$sub_all'"
            return 1
        fi
    else
        echo "✓ Subscription already exists: $sub_all"
    fi
}

# Function to assign roles
assign_roles() {
    echo "Assigning roles..."

    # Prereq check: namespace must exist
    local ns_status=$(az eventgrid namespace show --resource-group $rg --name $namespace_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -z "$ns_status" ] || [ "$ns_status" != "Succeeded" ]; then
        echo "Error: Event Grid namespace '$namespace_name' not found or not ready."
        echo "Please run option 1 first, then try again."
        return 1
    fi

    local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)

    if [ -z "$user_object_id" ] || [ -z "$user_upn" ]; then
        echo "Error: Unable to retrieve signed-in user information."
        echo "Please ensure you are logged in with 'az login'."
        return 1
    fi

    local ns_id=$(az eventgrid namespace show --resource-group $rg --name $namespace_name --query "id" -o tsv)

    # Assign EventGrid Data Sender on the namespace (publish events)
    local role_exists=$(az role assignment list \
        --assignee $user_object_id \
        --scope $ns_id \
        --role "EventGrid Data Sender" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -n "$role_exists" ]; then
        echo "✓ EventGrid Data Sender role already assigned"
    else
        az role assignment create \
            --role "EventGrid Data Sender" \
            --assignee "$user_object_id" \
            --scope "$ns_id" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ EventGrid Data Sender role assigned"
        else
            echo "Error: Failed to assign EventGrid Data Sender role"
            return 1
        fi
    fi

    # Assign EventGrid Data Receiver on the namespace (pull events)
    role_exists=$(az role assignment list \
        --assignee $user_object_id \
        --scope $ns_id \
        --role "EventGrid Data Receiver" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -n "$role_exists" ]; then
        echo "✓ EventGrid Data Receiver role already assigned"
    else
        az role assignment create \
            --role "EventGrid Data Receiver" \
            --assignee "$user_object_id" \
            --scope "$ns_id" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ EventGrid Data Receiver role assigned"
        else
            echo "Error: Failed to assign EventGrid Data Receiver role"
            return 1
        fi
    fi

    echo ""
    echo "Roles configured for: $user_upn"
    echo "  - EventGrid Data Sender: publish events to the namespace topic"
    echo "  - EventGrid Data Receiver: receive events from subscriptions"
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    echo ""

    # Check Event Grid namespace
    echo "Event Grid Namespace ($namespace_name):"
    local ns_status=$(az eventgrid namespace show --resource-group $rg --name $namespace_name --query "provisioningState" -o tsv 2>/dev/null)

    if [ -z "$ns_status" ]; then
        echo "  Status: Not created"
    else
        echo "  Status: $ns_status"
        if [ "$ns_status" = "Succeeded" ]; then
            echo "  ✓ Namespace is ready"
            local ns_sku=$(az eventgrid namespace show --resource-group $rg --name $namespace_name --query "sku.name" -o tsv 2>/dev/null)
            echo "  SKU: $ns_sku"

            # Check namespace topic
            local topic_status=$(az eventgrid namespace topic show --resource-group $rg --namespace-name $namespace_name --name $topic_name --query "provisioningState" -o tsv 2>/dev/null)
            if [ -n "$topic_status" ]; then
                echo "  ✓ Topic: $topic_name ($topic_status)"
            else
                echo "  ⚠ Topic not created: $topic_name"
            fi

            # Check roles
            local ns_id=$(az eventgrid namespace show --resource-group $rg --name $namespace_name --query "id" -o tsv)
            local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)

            local sender_role=$(az role assignment list \
                --assignee $user_object_id \
                --scope $ns_id \
                --role "EventGrid Data Sender" \
                --query "[0].id" -o tsv 2>/dev/null)

            if [ -n "$sender_role" ]; then
                echo "  ✓ Role assigned: $user_upn (EventGrid Data Sender)"
            else
                echo "  ⚠ EventGrid Data Sender role not assigned"
            fi

            local receiver_role=$(az role assignment list \
                --assignee $user_object_id \
                --scope $ns_id \
                --role "EventGrid Data Receiver" \
                --query "[0].id" -o tsv 2>/dev/null)

            if [ -n "$receiver_role" ]; then
                echo "  ✓ Role assigned: $user_upn (EventGrid Data Receiver)"
            else
                echo "  ⚠ EventGrid Data Receiver role not assigned"
            fi
        else
            echo "  ⚠ Namespace is still provisioning. Please wait and try again."
        fi
    fi

    echo ""

    # Check event subscriptions
    echo "Event Subscriptions:"
    for sub in $sub_flagged $sub_approved $sub_all; do
        local sub_status=$(az eventgrid namespace topic event-subscription show --resource-group $rg --namespace-name $namespace_name --topic-name $topic_name --name $sub --query "provisioningState" -o tsv 2>/dev/null)
        if [ -n "$sub_status" ]; then
            echo "  ✓ $sub ($sub_status)"
        else
            echo "  ⚠ $sub: Not created"
        fi
    done
}

# Function to retrieve connection info and create .env file
retrieve_connection_info() {
    echo "Retrieving connection information..."

    # Prereq check: namespace must exist
    local ns_status=$(az eventgrid namespace show --resource-group $rg --name $namespace_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -z "$ns_status" ] || [ "$ns_status" != "Succeeded" ]; then
        echo "Error: Event Grid namespace '$namespace_name' not found or not ready."
        echo "Please run option 1 first, then try again."
        return 1
    fi

    # Prereq check: roles must be assigned
    local ns_id=$(az eventgrid namespace show --resource-group $rg --name $namespace_name --query "id" -o tsv)

    local sender_role=$(az role assignment list \
        --assignee $user_object_id \
        --scope $ns_id \
        --role "EventGrid Data Sender" \
        --query "[0].id" -o tsv 2>/dev/null)

    local receiver_role=$(az role assignment list \
        --assignee $user_object_id \
        --scope $ns_id \
        --role "EventGrid Data Receiver" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -z "$sender_role" ] || [ -z "$receiver_role" ]; then
        echo "Error: Required roles not assigned."
        echo "Please run option 3 to assign roles, then try again."
        return 1
    fi

    local ns_hostname=$(az eventgrid namespace show --resource-group $rg --name $namespace_name --query "topicsConfiguration.hostname" -o tsv 2>/dev/null)

    # Fall back to constructed hostname if query returns empty
    if [ -z "$ns_hostname" ]; then
        ns_hostname="$namespace_name.$location-1.eventgrid.azure.net"
    fi

    local env_file="$(dirname "$0")/.env"

    cat > "$env_file" << EOF
export RESOURCE_GROUP="$rg"
export NAMESPACE_NAME="$namespace_name"
export EVENTGRID_TOPIC_NAME="$topic_name"
export EVENTGRID_ENDPOINT="https://$ns_hostname"
EOF

    echo ""
    echo "Event Grid Connection Information"
    echo "==========================================================="
    echo "Namespace endpoint: https://$ns_hostname"
    echo "Topic name: $topic_name"
    echo "Authentication: Microsoft Entra ID (DefaultAzureCredential)"
    echo ""
    echo "Environment variables saved to: $env_file"
}

# Display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    Event Grid Exercise - Deployment Script"
    echo "====================================================================="
    echo "Resource Group: $rg"
    echo "Location: $location"
    echo "Namespace: $namespace_name"
    echo "Topic: $topic_name"
    echo "====================================================================="
    echo "1. Create Event Grid namespace and topic"
    echo "2. Create event subscriptions"
    echo "3. Assign user roles"
    echo "4. Retrieve connection info"
    echo "5. Check deployment status"
    echo "6. Exit"
    echo "====================================================================="
}

# Main menu loop
while true; do
    show_menu
    read -p "Please select an option (1-6): " choice

    case $choice in
        1)
            echo ""
            create_resource_group
            echo ""
            create_namespace_and_topic
            echo ""
            read -p "Press Enter to continue..."
            ;;
        2)
            echo ""
            create_event_subscriptions
            echo ""
            read -p "Press Enter to continue..."
            ;;
        3)
            echo ""
            assign_roles
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
            echo ""
            check_deployment_status
            echo ""
            read -p "Press Enter to continue..."
            ;;
        6)
            echo "Exiting..."
            clear
            exit 0
            ;;
        *)
            echo ""
            echo "Invalid option. Please select 1-6."
            echo ""
            read -p "Press Enter to continue..."
            ;;
    esac

    echo ""
done
