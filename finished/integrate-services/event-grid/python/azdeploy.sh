#!/usr/bin/env bash

# Change the values of these variables as needed

# rg="<your-resource-group-name>"  # Resource Group name
# location="<your-azure-region>"   # Azure region for the resources

rg="rg-exercises"           # Resource Group name
location="eastus2"          # Azure region for the resources

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
topic_name="egtopic-exercise-${user_hash}"
namespace_name="sbns-exercise-${user_hash}"

# Queue and subscription names
flagged_queue="flagged-content"
approved_queue="approved-content"
all_events_queue="all-events"
sub_flagged="sub-flagged-content"
sub_approved="sub-approved-content"
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

# Function to create Event Grid topic and Service Bus namespace
create_topic_and_namespace() {
    echo "Creating Event Grid topic '$topic_name'..."

    local topic_exists=$(az eventgrid topic show --resource-group $rg --name $topic_name 2>/dev/null)
    if [ -z "$topic_exists" ]; then
        az eventgrid topic create \
            --name $topic_name \
            --resource-group $rg \
            --location $location \
            --input-schema CloudEventSchemaV1_0 > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Event Grid topic created: $topic_name"
        else
            echo "Error: Failed to create Event Grid topic"
            return 1
        fi
    else
        echo "✓ Event Grid topic already exists: $topic_name"
    fi

    echo ""
    echo "Creating Service Bus namespace '$namespace_name'..."

    local ns_exists=$(az servicebus namespace show --resource-group $rg --name $namespace_name 2>/dev/null)
    if [ -z "$ns_exists" ]; then
        az servicebus namespace create \
            --name $namespace_name \
            --resource-group $rg \
            --location $location \
            --sku Standard > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Service Bus namespace created: $namespace_name"
        else
            echo "Error: Failed to create Service Bus namespace"
            return 1
        fi
    else
        echo "✓ Service Bus namespace already exists: $namespace_name"
    fi

    echo ""
    echo "Use option 2 to create queues and event subscriptions."
}

# Function to create Service Bus queues and Event Grid subscriptions
create_queues_and_subscriptions() {
    echo "Creating Service Bus queues and Event Grid subscriptions..."

    # Prereq check: topic must exist
    local topic_status=$(az eventgrid topic show --resource-group $rg --name $topic_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -z "$topic_status" ] || [ "$topic_status" != "Succeeded" ]; then
        echo "Error: Event Grid topic '$topic_name' not found or not ready."
        echo "Please run option 1 first, then try again."
        return 1
    fi

    # Prereq check: namespace must exist
    local ns_status=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -z "$ns_status" ] || [ "$ns_status" != "Succeeded" ]; then
        echo "Error: Service Bus namespace '$namespace_name' not found or not ready."
        echo "Please run option 1 first, then try again."
        return 1
    fi

    # Create the three Service Bus queues
    for queue in $flagged_queue $approved_queue $all_events_queue; do
        local q_exists=$(az servicebus queue show --resource-group $rg --namespace-name $namespace_name --name $queue 2>/dev/null)
        if [ -z "$q_exists" ]; then
            az servicebus queue create \
                --resource-group $rg \
                --namespace-name $namespace_name \
                --name $queue > /dev/null 2>&1

            if [ $? -eq 0 ]; then
                echo "✓ Queue created: $queue"
            else
                echo "Error: Failed to create queue '$queue'"
                return 1
            fi
        else
            echo "✓ Queue already exists: $queue"
        fi
    done

    echo ""

    # Get resource IDs for topic and queues
    local topic_id=$(az eventgrid topic show --resource-group $rg --name $topic_name --query "id" -o tsv)
    local flagged_queue_id=$(az servicebus queue show --resource-group $rg --namespace-name $namespace_name --name $flagged_queue --query "id" -o tsv)
    local approved_queue_id=$(az servicebus queue show --resource-group $rg --namespace-name $namespace_name --name $approved_queue --query "id" -o tsv)
    local all_events_queue_id=$(az servicebus queue show --resource-group $rg --namespace-name $namespace_name --name $all_events_queue --query "id" -o tsv)

    # Create event subscription for flagged content
    local sub_exists=$(az eventgrid event-subscription show --name $sub_flagged --source-resource-id $topic_id 2>/dev/null)
    if [ -z "$sub_exists" ]; then
        az eventgrid event-subscription create \
            --name $sub_flagged \
            --source-resource-id $topic_id \
            --endpoint-type servicebusqueue \
            --endpoint $flagged_queue_id \
            --event-delivery-schema CloudEventSchemaV1_0 \
            --included-event-types "com.contoso.ai.ContentFlagged" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Subscription created: $sub_flagged (ContentFlagged → $flagged_queue)"
        else
            echo "Error: Failed to create subscription '$sub_flagged'"
            return 1
        fi
    else
        echo "✓ Subscription already exists: $sub_flagged"
    fi

    # Create event subscription for approved content
    sub_exists=$(az eventgrid event-subscription show --name $sub_approved --source-resource-id $topic_id 2>/dev/null)
    if [ -z "$sub_exists" ]; then
        az eventgrid event-subscription create \
            --name $sub_approved \
            --source-resource-id $topic_id \
            --endpoint-type servicebusqueue \
            --endpoint $approved_queue_id \
            --event-delivery-schema CloudEventSchemaV1_0 \
            --included-event-types "com.contoso.ai.ContentApproved" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Subscription created: $sub_approved (ContentApproved → $approved_queue)"
        else
            echo "Error: Failed to create subscription '$sub_approved'"
            return 1
        fi
    else
        echo "✓ Subscription already exists: $sub_approved"
    fi

    # Create event subscription for all events (no filter)
    sub_exists=$(az eventgrid event-subscription show --name $sub_all --source-resource-id $topic_id 2>/dev/null)
    if [ -z "$sub_exists" ]; then
        az eventgrid event-subscription create \
            --name $sub_all \
            --source-resource-id $topic_id \
            --endpoint-type servicebusqueue \
            --endpoint $all_events_queue_id \
            --event-delivery-schema CloudEventSchemaV1_0 > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Subscription created: $sub_all (all events → $all_events_queue)"
        else
            echo "Error: Failed to create subscription '$sub_all'"
            return 1
        fi
    else
        echo "✓ Subscription already exists: $sub_all"
    fi

    echo ""
    echo "Use option 3 to assign roles."
}

# Function to assign roles
assign_roles() {
    echo "Assigning roles..."

    # Prereq check: topic must exist
    local topic_status=$(az eventgrid topic show --resource-group $rg --name $topic_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -z "$topic_status" ] || [ "$topic_status" != "Succeeded" ]; then
        echo "Error: Event Grid topic '$topic_name' not found or not ready."
        echo "Please run option 1 first, then try again."
        return 1
    fi

    # Prereq check: namespace must exist
    local ns_status=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -z "$ns_status" ] || [ "$ns_status" != "Succeeded" ]; then
        echo "Error: Service Bus namespace '$namespace_name' not found or not ready."
        echo "Please run option 1 first, then try again."
        return 1
    fi

    local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)

    if [ -z "$user_object_id" ] || [ -z "$user_upn" ]; then
        echo "Error: Unable to retrieve signed-in user information."
        echo "Please ensure you are logged in with 'az login'."
        return 1
    fi

    # Assign EventGrid Data Sender on the topic
    local topic_id=$(az eventgrid topic show --resource-group $rg --name $topic_name --query "id" -o tsv)

    local role_exists=$(az role assignment list \
        --assignee $user_object_id \
        --scope $topic_id \
        --role "EventGrid Data Sender" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -n "$role_exists" ]; then
        echo "✓ EventGrid Data Sender role already assigned"
    else
        az role assignment create \
            --role "EventGrid Data Sender" \
            --assignee "$user_object_id" \
            --scope "$topic_id" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ EventGrid Data Sender role assigned"
        else
            echo "Error: Failed to assign EventGrid Data Sender role"
            return 1
        fi
    fi

    # Assign Azure Service Bus Data Owner on the namespace
    local ns_id=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "id" -o tsv)

    role_exists=$(az role assignment list \
        --assignee $user_object_id \
        --scope $ns_id \
        --role "Azure Service Bus Data Owner" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -n "$role_exists" ]; then
        echo "✓ Azure Service Bus Data Owner role already assigned"
    else
        az role assignment create \
            --role "Azure Service Bus Data Owner" \
            --assignee "$user_object_id" \
            --scope "$ns_id" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Azure Service Bus Data Owner role assigned"
        else
            echo "Error: Failed to assign Azure Service Bus Data Owner role"
            return 1
        fi
    fi

    echo ""
    echo "Roles configured for: $user_upn"
    echo "  - EventGrid Data Sender: publish events to the topic"
    echo "  - Azure Service Bus Data Owner: read from queues"
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    echo ""

    # Check Event Grid topic
    echo "Event Grid Topic ($topic_name):"
    local topic_status=$(az eventgrid topic show --resource-group $rg --name $topic_name --query "provisioningState" -o tsv 2>/dev/null)

    if [ -z "$topic_status" ]; then
        echo "  Status: Not created"
    else
        echo "  Status: $topic_status"
        if [ "$topic_status" = "Succeeded" ]; then
            echo "  ✓ Topic is ready"
            local topic_schema=$(az eventgrid topic show --resource-group $rg --name $topic_name --query "inputSchema" -o tsv 2>/dev/null)
            echo "  Input schema: $topic_schema"
            local topic_endpoint=$(az eventgrid topic show --resource-group $rg --name $topic_name --query "endpoint" -o tsv 2>/dev/null)
            echo "  Endpoint: $topic_endpoint"

            # Check EventGrid Data Sender role
            local topic_id=$(az eventgrid topic show --resource-group $rg --name $topic_name --query "id" -o tsv)
            local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)
            local eg_role=$(az role assignment list \
                --assignee $user_object_id \
                --scope $topic_id \
                --role "EventGrid Data Sender" \
                --query "[0].id" -o tsv 2>/dev/null)

            if [ -n "$eg_role" ]; then
                echo "  ✓ Role assigned: $user_upn (EventGrid Data Sender)"
            else
                echo "  ⚠ EventGrid Data Sender role not assigned"
            fi
        else
            echo "  ⚠ Topic is still provisioning. Please wait and try again."
        fi
    fi

    echo ""

    # Check Service Bus namespace
    echo "Service Bus Namespace ($namespace_name):"
    local ns_status=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "provisioningState" -o tsv 2>/dev/null)

    if [ -z "$ns_status" ]; then
        echo "  Status: Not created"
    else
        echo "  Status: $ns_status"
        if [ "$ns_status" = "Succeeded" ]; then
            echo "  ✓ Namespace is ready"
            local ns_sku=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "sku.name" -o tsv 2>/dev/null)
            echo "  SKU: $ns_sku"

            # Check queues
            for queue in $flagged_queue $approved_queue $all_events_queue; do
                local q_exists=$(az servicebus queue show --resource-group $rg --namespace-name $namespace_name --name $queue 2>/dev/null)
                if [ -n "$q_exists" ]; then
                    echo "  ✓ Queue: $queue"
                else
                    echo "  ⚠ Queue not created: $queue"
                fi
            done

            # Check Azure Service Bus Data Owner role
            local ns_id=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "id" -o tsv)
            local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)
            local sb_role=$(az role assignment list \
                --assignee $user_object_id \
                --scope $ns_id \
                --role "Azure Service Bus Data Owner" \
                --query "[0].id" -o tsv 2>/dev/null)

            if [ -n "$sb_role" ]; then
                echo "  ✓ Role assigned: $user_upn (Azure Service Bus Data Owner)"
            else
                echo "  ⚠ Azure Service Bus Data Owner role not assigned"
            fi
        else
            echo "  ⚠ Namespace is still provisioning. Please wait and try again."
        fi
    fi

    echo ""

    # Check event subscriptions
    echo "Event Subscriptions:"
    local topic_id=$(az eventgrid topic show --resource-group $rg --name $topic_name --query "id" -o tsv 2>/dev/null)
    if [ -n "$topic_id" ]; then
        for sub in $sub_flagged $sub_approved $sub_all; do
            local sub_status=$(az eventgrid event-subscription show --name $sub --source-resource-id $topic_id --query "provisioningState" -o tsv 2>/dev/null)
            if [ -n "$sub_status" ]; then
                echo "  ✓ $sub ($sub_status)"
            else
                echo "  ⚠ $sub: Not created"
            fi
        done
    else
        echo "  Topic not found — subscriptions cannot be checked."
    fi
}

# Function to retrieve connection info and create .env file
retrieve_connection_info() {
    echo "Retrieving connection information..."

    # Prereq check: topic must exist
    local topic_status=$(az eventgrid topic show --resource-group $rg --name $topic_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -z "$topic_status" ] || [ "$topic_status" != "Succeeded" ]; then
        echo "Error: Event Grid topic '$topic_name' not found or not ready."
        echo "Please run option 1 first, then try again."
        return 1
    fi

    # Prereq check: namespace must exist
    local ns_status=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -z "$ns_status" ] || [ "$ns_status" != "Succeeded" ]; then
        echo "Error: Service Bus namespace '$namespace_name' not found or not ready."
        echo "Please run option 1 first, then try again."
        return 1
    fi

    # Prereq check: roles must be assigned
    local topic_id=$(az eventgrid topic show --resource-group $rg --name $topic_name --query "id" -o tsv)
    local eg_role=$(az role assignment list \
        --assignee $user_object_id \
        --scope $topic_id \
        --role "EventGrid Data Sender" \
        --query "[0].id" -o tsv 2>/dev/null)

    local ns_id=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "id" -o tsv)
    local sb_role=$(az role assignment list \
        --assignee $user_object_id \
        --scope $ns_id \
        --role "Azure Service Bus Data Owner" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -z "$eg_role" ] || [ -z "$sb_role" ]; then
        echo "Error: Required roles not assigned."
        echo "Please run option 3 to assign roles, then try again."
        return 1
    fi

    local topic_endpoint=$(az eventgrid topic show --resource-group $rg --name $topic_name --query "endpoint" -o tsv)
    local fqdn="${namespace_name}.servicebus.windows.net"

    local env_file="$(dirname "$0")/.env"

    cat > "$env_file" << EOF
export RESOURCE_GROUP="$rg"
export EVENTGRID_TOPIC_NAME="$topic_name"
export EVENTGRID_TOPIC_ENDPOINT="$topic_endpoint"
export NAMESPACE_NAME="$namespace_name"
export SERVICE_BUS_FQDN="$fqdn"
EOF

    echo ""
    echo "Event Grid & Service Bus Connection Information"
    echo "==========================================================="
    echo "Topic endpoint: $topic_endpoint"
    echo "Service Bus FQDN: $fqdn"
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
    echo "Topic: $topic_name"
    echo "Namespace: $namespace_name"
    echo "====================================================================="
    echo "1. Create Event Grid topic and Service Bus namespace"
    echo "2. Create queues and event subscriptions"
    echo "3. Assign roles"
    echo "4. Check deployment status"
    echo "5. Retrieve connection info"
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
            create_topic_and_namespace
            echo ""
            read -p "Press Enter to continue..."
            ;;
        2)
            echo ""
            create_queues_and_subscriptions
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
            check_deployment_status
            echo ""
            read -p "Press Enter to continue..."
            ;;
        5)
            echo ""
            retrieve_connection_info
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
