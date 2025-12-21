# AKS Configuration API Client

Console application for interacting with the AKS Configuration API.

## Features

Menu-driven interface to:
1. Check API Health (Liveness)
2. Check API Readiness
3. View Secrets Information
4. Get Single Product
5. List All Products
6. View Log Summary
7. Exit

## Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Update `.env` with your API endpoint:
   ```
   API_ENDPOINT=http://<your-service-ip>
   ```

   For local testing:
   ```
   API_ENDPOINT=http://localhost:8000
   ```

   For AKS deployment, get the external IP:
   ```bash
   kubectl get services
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Run

```bash
python main.py
```

## Usage

The client presents a menu with options to interact with the API:

- **Option 1**: Checks if the API is alive (liveness probe)
- **Option 2**: Checks if the API is ready with proper configuration
- **Option 3**: Views information about loaded secrets (values are masked)
- **Option 4**: Retrieves a single product by ID (1-10)
- **Option 5**: Lists all available products
- **Option 6**: Views summary of logged requests from persistent storage
- **Option 7**: Exits the application

## Example

```
======================================================================
  AKS Configuration API - Client Menu
======================================================================
API Endpoint: http://20.1.2.3
======================================================================
1. Check API Health (Liveness)
2. Check API Readiness
3. View Secrets Information
4. Get Single Product
5. List All Products
6. View Log Summary
7. Exit
======================================================================
Select option (1-7): 1

[*] Checking API health...
✓ API is healthy
  Service: aks-config-api
  Version: 1.0.0
  Student: John Doe

Press Enter to continue...
```
