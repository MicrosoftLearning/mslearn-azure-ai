---
title: Lab requirements
permalink: lab-requirements.html
layout: page
---

This document provides a consolidated list of the accounts and software used across all exercises in this repository. It is intended for students who want to configure a system to complete every lab and for lab providers who want to build a single environment that supports all exercises. Because this list represents the combined requirements, individual exercises require only a subset of these items.

## Required accounts and software

Obtain the following accounts and install the listed software before completing the exercises.

- An [Azure subscription](https://azure.microsoft.com/) with the permissions and quota to provision the necessary Azure services.
- A [GitHub account](https://github.com/) with access to GitHub Copilot.
- A current web browser.
- [Visual Studio Code](https://code.visualstudio.com/) on a [supported platform](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12 or later](https://www.python.org/downloads/).
- The latest version of the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).
- The [PostgreSQL psql command-line client](https://www.postgresql.org/download/). A local PostgreSQL server is not required.
- [kubectl](https://kubernetes.io/docs/tasks/tools/).
- [Azure Functions Core Tools](https://learn.microsoft.com/azure/azure-functions/functions-run-local) version 4 or later.
- The [Azure Functions extension for Visual Studio Code](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-azurefunctions).
- The [GitHub Copilot extension for Visual Studio Code](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot).
- The [Azurite extension for Visual Studio Code](https://marketplace.visualstudio.com/items?itemName=Azurite.azurite).

### Recommended options

The following are strongly recommended to help complete the exercises.

- The [Ruff extension for Visual Studio Code](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff) for formatting and linting Python code.
- The [YAML extension for Visual Studio Code](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) for YAML language support, validation, and formatting.

## Azure services

Each exercise provisions one or more the following Azure services:

- Application Insights
- Azure App Configuration
- Azure App Service
- Azure Container Apps
- Azure Container Registry
- Azure Cosmos DB for NoSQL
- Azure Database for PostgreSQL flexible server
- Azure Event Grid
- Azure Key Vault
- Azure Kubernetes Service
- Azure Managed Redis
- Azure Service Bus
- Log Analytics
- Microsoft Foundry
