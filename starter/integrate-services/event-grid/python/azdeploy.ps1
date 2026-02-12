#!/usr/bin/env pwsh

# Change the values of these variables as needed

$rg = "<your-resource-group-name>"  # Resource Group name
$location = "<your-azure-region>"   # Azure region for the resources

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

function Get-UserHash {
    $userObjectId = (az ad signed-in-user show --query "id" -o tsv 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($userObjectId)) {
        Write-Host "Error: Not authenticated with Azure. Please run: az login"
        exit 1
    }

    $sha1 = [System.Security.Cryptography.SHA1]::Create()
    $hashBytes = $sha1.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($userObjectId))
    return ([System.BitConverter]::ToString($hashBytes).Replace("-", "").Substring(0, 8).ToLower())
}

$userHash = Get-UserHash
$userObjectId = (az ad signed-in-user show --query "id" -o tsv 2>$null)

# Resource names with hash for uniqueness
$namespaceName = "egns-exercise-$userHash"
$topicName = "moderation-events"

# Event subscription names
$subFlagged = "sub-flagged"
$subApproved = "sub-approved"
$subAll = "sub-all-events"

function Show-Menu {
    Clear-Host
    Write-Host "====================================================================="
    Write-Host "    Event Grid Exercise - Deployment Script"
    Write-Host "====================================================================="
    Write-Host "Resource Group: $rg"
    Write-Host "Location: $location"
    Write-Host "Namespace: $namespaceName"
    Write-Host "Topic: $topicName"
    Write-Host "====================================================================="
    Write-Host "1. Create Event Grid namespace and topic"
    Write-Host "2. Create event subscriptions"
    Write-Host "3. Assign user roles"
    Write-Host "4. Retrieve connection info"
    Write-Host "5. Check deployment status"
    Write-Host "6. Exit"
    Write-Host "====================================================================="
}

function Create-ResourceGroup {
    Write-Host "Checking/creating resource group '$rg'..."

    $exists = az group exists --name $rg
    if ($exists -eq "false") {
        az group create --name $rg --location $location 2>&1 | Out-Null
        Write-Host "✓ Resource group created: $rg"
    }
    else {
        Write-Host "✓ Resource group already exists: $rg"
    }
}

function Create-NamespaceAndTopic {
    Write-Host "Creating Event Grid namespace '$namespaceName'..."

    az eventgrid namespace show --resource-group $rg --name $namespaceName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az eventgrid namespace create `
            --name $namespaceName `
            --resource-group $rg `
            --location $location `
            --sku "{name:standard,capacity:1}" 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Event Grid namespace created: $namespaceName"
        }
        else {
            Write-Host "Error: Failed to create Event Grid namespace"
            return
        }
    }
    else {
        Write-Host "✓ Event Grid namespace already exists: $namespaceName"
    }

    Write-Host ""
    Write-Host "Creating namespace topic '$topicName'..."

    az eventgrid namespace topic show --resource-group $rg --namespace-name $namespaceName --name $topicName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az eventgrid namespace topic create `
            --name $topicName `
            --namespace-name $namespaceName `
            --resource-group $rg `
            --event-retention-in-days 1 `
            --publisher-type Custom `
            --input-schema CloudEventSchemaV1_0 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Namespace topic created: $topicName"
        }
        else {
            Write-Host "Error: Failed to create namespace topic"
            return
        }
    }
    else {
        Write-Host "✓ Namespace topic already exists: $topicName"
    }
}

function Create-EventSubscriptions {
    Write-Host "Creating event subscriptions..."

    # Prereq check: namespace must exist
    $nsStatus = az eventgrid namespace show --resource-group $rg --name $namespaceName --query "provisioningState" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($nsStatus) -or $nsStatus -ne "Succeeded") {
        Write-Host "Error: Event Grid namespace '$namespaceName' not found or not ready."
        Write-Host "Please run option 1 first, then try again."
        return
    }

    # Prereq check: topic must exist
    $topicStatus = az eventgrid namespace topic show --resource-group $rg --namespace-name $namespaceName --name $topicName --query "provisioningState" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($topicStatus) -or $topicStatus -ne "Succeeded") {
        Write-Host "Error: Namespace topic '$topicName' not found or not ready."
        Write-Host "Please run option 1 first, then try again."
        return
    }

    # Subscription for flagged content only
    az eventgrid namespace topic event-subscription show --resource-group $rg --namespace-name $namespaceName --topic-name $topicName --name $subFlagged 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az eventgrid namespace topic event-subscription create `
            --name $subFlagged `
            --namespace-name $namespaceName `
            --resource-group $rg `
            --topic-name $topicName `
            --delivery-configuration "{deliveryMode:Queue,queue:{receiveLockDurationInSeconds:60,maxDeliveryCount:10,eventTimeToLive:P1D}}" `
            --event-delivery-schema CloudEventSchemaV1_0 `
            --filters-configuration "{includedEventTypes:['com.contoso.ai.ContentFlagged']}" 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Subscription created: $subFlagged (ContentFlagged events only)"
        }
        else {
            Write-Host "Error: Failed to create subscription '$subFlagged'"
            return
        }
    }
    else {
        Write-Host "✓ Subscription already exists: $subFlagged"
    }

    # Subscription for approved content only
    az eventgrid namespace topic event-subscription show --resource-group $rg --namespace-name $namespaceName --topic-name $topicName --name $subApproved 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az eventgrid namespace topic event-subscription create `
            --name $subApproved `
            --namespace-name $namespaceName `
            --resource-group $rg `
            --topic-name $topicName `
            --delivery-configuration "{deliveryMode:Queue,queue:{receiveLockDurationInSeconds:60,maxDeliveryCount:10,eventTimeToLive:P1D}}" `
            --event-delivery-schema CloudEventSchemaV1_0 `
            --filters-configuration "{includedEventTypes:['com.contoso.ai.ContentApproved']}" 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Subscription created: $subApproved (ContentApproved events only)"
        }
        else {
            Write-Host "Error: Failed to create subscription '$subApproved'"
            return
        }
    }
    else {
        Write-Host "✓ Subscription already exists: $subApproved"
    }

    # Subscription for all events (no filter — audit log)
    az eventgrid namespace topic event-subscription show --resource-group $rg --namespace-name $namespaceName --topic-name $topicName --name $subAll 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az eventgrid namespace topic event-subscription create `
            --name $subAll `
            --namespace-name $namespaceName `
            --resource-group $rg `
            --topic-name $topicName `
            --delivery-configuration "{deliveryMode:Queue,queue:{receiveLockDurationInSeconds:60,maxDeliveryCount:10,eventTimeToLive:P1D}}" `
            --event-delivery-schema CloudEventSchemaV1_0 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Subscription created: $subAll (all events — audit log)"
        }
        else {
            Write-Host "Error: Failed to create subscription '$subAll'"
            return
        }
    }
    else {
        Write-Host "✓ Subscription already exists: $subAll"
    }
}

function Assign-Roles {
    Write-Host "Assigning roles..."

    # Prereq check: namespace must exist
    $nsStatus = az eventgrid namespace show --resource-group $rg --name $namespaceName --query "provisioningState" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($nsStatus) -or $nsStatus -ne "Succeeded") {
        Write-Host "Error: Event Grid namespace '$namespaceName' not found or not ready."
        Write-Host "Please run option 1 first, then try again."
        return
    }

    $userUpn = az ad signed-in-user show --query userPrincipalName -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($userObjectId) -or [string]::IsNullOrWhiteSpace($userUpn)) {
        Write-Host "Error: Unable to retrieve signed-in user information."
        Write-Host "Please ensure you are logged in with 'az login'."
        return
    }

    $nsId = az eventgrid namespace show --resource-group $rg --name $namespaceName --query "id" -o tsv

    # Assign EventGrid Data Sender on the namespace (publish events)
    $roleExists = az role assignment list `
        --assignee $userObjectId `
        --scope $nsId `
        --role "EventGrid Data Sender" `
        --query "[0].id" -o tsv 2>$null

    if (-not [string]::IsNullOrWhiteSpace($roleExists)) {
        Write-Host "✓ EventGrid Data Sender role already assigned"
    }
    else {
        az role assignment create `
            --role "EventGrid Data Sender" `
            --assignee "$userObjectId" `
            --scope "$nsId" 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ EventGrid Data Sender role assigned"
        }
        else {
            Write-Host "Error: Failed to assign EventGrid Data Sender role"
            return
        }
    }

    # Assign EventGrid Data Receiver on the namespace (pull events)
    $roleExists = az role assignment list `
        --assignee $userObjectId `
        --scope $nsId `
        --role "EventGrid Data Receiver" `
        --query "[0].id" -o tsv 2>$null

    if (-not [string]::IsNullOrWhiteSpace($roleExists)) {
        Write-Host "✓ EventGrid Data Receiver role already assigned"
    }
    else {
        az role assignment create `
            --role "EventGrid Data Receiver" `
            --assignee "$userObjectId" `
            --scope "$nsId" 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ EventGrid Data Receiver role assigned"
        }
        else {
            Write-Host "Error: Failed to assign EventGrid Data Receiver role"
            return
        }
    }

    Write-Host ""
    Write-Host "Roles configured for: $userUpn"
    Write-Host "  - EventGrid Data Sender: publish events to the namespace topic"
    Write-Host "  - EventGrid Data Receiver: receive events from subscriptions"
}

function Retrieve-ConnectionInfo {
    Write-Host "Retrieving connection information..."

    # Prereq check: namespace must exist
    $nsStatus = az eventgrid namespace show --resource-group $rg --name $namespaceName --query "provisioningState" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($nsStatus) -or $nsStatus -ne "Succeeded") {
        Write-Host "Error: Event Grid namespace '$namespaceName' not found or not ready."
        Write-Host "Please run option 1 first, then try again."
        return
    }

    # Prereq check: roles must be assigned
    $nsId = az eventgrid namespace show --resource-group $rg --name $namespaceName --query "id" -o tsv

    $senderRole = az role assignment list `
        --assignee $userObjectId `
        --scope $nsId `
        --role "EventGrid Data Sender" `
        --query "[0].id" -o tsv 2>$null

    $receiverRole = az role assignment list `
        --assignee $userObjectId `
        --scope $nsId `
        --role "EventGrid Data Receiver" `
        --query "[0].id" -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($senderRole) -or [string]::IsNullOrWhiteSpace($receiverRole)) {
        Write-Host "Error: Required roles not assigned."
        Write-Host "Please run option 3 to assign roles, then try again."
        return
    }

    $nsHostname = az eventgrid namespace show --resource-group $rg --name $namespaceName --query "topicsConfiguration.hostname" -o tsv 2>$null

    # Fall back to constructed hostname if query returns empty
    if ([string]::IsNullOrWhiteSpace($nsHostname)) {
        $nsHostname = "$namespaceName.$location-1.eventgrid.azure.net"
    }

    $scriptDir = Split-Path -Parent $PSCommandPath

    # Create .env.ps1 file (for PowerShell shell variables)
    $envPs1File = Join-Path $scriptDir ".env.ps1"

    @(
        "`$env:RESOURCE_GROUP = `"$rg`"",
        "`$env:NAMESPACE_NAME = `"$namespaceName`"",
        "`$env:EVENTGRID_TOPIC_NAME = `"$topicName`"",
        "`$env:EVENTGRID_ENDPOINT = `"https://$nsHostname`""
    ) | Set-Content -Path $envPs1File -Encoding UTF8

    Write-Host ""
    Write-Host "Event Grid Connection Information"
    Write-Host "==========================================================="
    Write-Host "Namespace endpoint: https://$nsHostname"
    Write-Host "Topic name: $topicName"
    Write-Host "Authentication: Microsoft Entra ID (DefaultAzureCredential)"
    Write-Host ""
    Write-Host "Environment variables saved to: .env.ps1"
}

function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    Write-Host ""

    # Check Event Grid namespace
    Write-Host "Event Grid Namespace ($namespaceName):"
    $nsStatus = az eventgrid namespace show --resource-group $rg --name $namespaceName --query "provisioningState" -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($nsStatus)) {
        Write-Host "  Status: Not created"
    }
    else {
        Write-Host "  Status: $nsStatus"
        if ($nsStatus -eq "Succeeded") {
            Write-Host "  ✓ Namespace is ready"
            $nsSku = az eventgrid namespace show --resource-group $rg --name $namespaceName --query "sku.name" -o tsv 2>$null
            Write-Host "  SKU: $nsSku"

            # Check namespace topic
            $topicStatus = az eventgrid namespace topic show --resource-group $rg --namespace-name $namespaceName --name $topicName --query "provisioningState" -o tsv 2>$null
            if (-not [string]::IsNullOrWhiteSpace($topicStatus)) {
                Write-Host "  ✓ Topic: $topicName ($topicStatus)"
            }
            else {
                Write-Host "  ⚠ Topic not created: $topicName"
            }

            # Check roles
            $nsId = az eventgrid namespace show --resource-group $rg --name $namespaceName --query "id" -o tsv
            $userUpn = az ad signed-in-user show --query userPrincipalName -o tsv 2>$null

            $senderRole = az role assignment list `
                --assignee $userObjectId `
                --scope $nsId `
                --role "EventGrid Data Sender" `
                --query "[0].id" -o tsv 2>$null

            if (-not [string]::IsNullOrWhiteSpace($senderRole)) {
                Write-Host "  ✓ Role assigned: $userUpn (EventGrid Data Sender)"
            }
            else {
                Write-Host "  ⚠ EventGrid Data Sender role not assigned"
            }

            $receiverRole = az role assignment list `
                --assignee $userObjectId `
                --scope $nsId `
                --role "EventGrid Data Receiver" `
                --query "[0].id" -o tsv 2>$null

            if (-not [string]::IsNullOrWhiteSpace($receiverRole)) {
                Write-Host "  ✓ Role assigned: $userUpn (EventGrid Data Receiver)"
            }
            else {
                Write-Host "  ⚠ EventGrid Data Receiver role not assigned"
            }
        }
        else {
            Write-Host "  ⚠ Namespace is still provisioning. Please wait and try again."
        }
    }

    Write-Host ""

    # Check event subscriptions
    Write-Host "Event Subscriptions:"
    foreach ($sub in @($subFlagged, $subApproved, $subAll)) {
        $subStatus = az eventgrid namespace topic event-subscription show --resource-group $rg --namespace-name $namespaceName --topic-name $topicName --name $sub --query "provisioningState" -o tsv 2>$null
        if (-not [string]::IsNullOrWhiteSpace($subStatus)) {
            Write-Host "  ✓ $sub ($subStatus)"
        }
        else {
            Write-Host "  ⚠ ${sub}: Not created"
        }
    }
}

while ($true) {
    Show-Menu
    $choice = Read-Host "Please select an option (1-6)"

    switch ($choice) {
        "1" {
            Write-Host ""
            Create-ResourceGroup
            Write-Host ""
            Create-NamespaceAndTopic
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "2" {
            Write-Host ""
            Create-EventSubscriptions
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "3" {
            Write-Host ""
            Assign-Roles
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "4" {
            Write-Host ""
            Retrieve-ConnectionInfo
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "5" {
            Write-Host ""
            Check-DeploymentStatus
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "6" {
            Write-Host "Exiting..."
            Clear-Host
            exit 0
        }
        default {
            Write-Host ""
            Write-Host "Invalid option. Please select 1-6."
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
    }
}
