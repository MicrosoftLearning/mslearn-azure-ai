This exercise is focused on configuring an API hosted on AKS. This gives hands-on experience:

- Store non-sensitive settings
- Create Secrets to store sensitive information
- Create persistent storage for API log data

Students will use a deployment script to provision Azure resources and deploy the container to ACR.

## API parameters

The Python API is not connected to any external services. It's a containerized app deployed to Azure Container Registry. It will have the following endpoints:

- GET /healthz - Liveness probe
- GET /readyz - Readiness probe (checks Foundry connectivity)
- GET /secrets - Returns mock secrets stored in AKS
- GET /product - Returns mock product information for a single item from a set of pre-defined products.
- GET /products - Returns the full list of products

The API should log the requests to the endpoints in the persistent storage.

## Client app

The Python console app has menu options for each of the four endpoints. User is prompted to enter a product ID to retrieve the single product information.

## AKS

Not sure what would be a good non-sensitive value to set for the API. Maybe have them store their name and have it be part of the information returned from the API calls?

The Secrets will be mock secrets like: "SecretEndpointValue", and "SecretAccessKey".