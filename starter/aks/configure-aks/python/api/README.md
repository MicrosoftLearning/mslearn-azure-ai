# AKS Configuration API

FastAPI application demonstrating AKS configuration patterns:
- **ConfigMaps** for non-sensitive configuration
- **Secrets** for sensitive data
- **Persistent Volumes** for log storage

## Endpoints

- `GET /healthz` - Liveness probe
- `GET /readyz` - Readiness probe (checks configuration)
- `GET /secrets` - Returns information about loaded secrets (masked)
- `GET /product/{product_id}` - Returns product information by ID
- `GET /products` - Returns list of all products
- `GET /logs/summary` - Returns summary of logged requests

## Local Development

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Update `.env` with your values:
   ```
   STUDENT_NAME=YourName
   API_VERSION=1.0.0
   LOG_PATH=./logs
   SECRET_ENDPOINT=SecretEndpointValue
   SECRET_ACCESS_KEY=SecretAccessKey123456
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the API:
   ```bash
   python main.py
   ```

The API will be available at `http://localhost:8000`.

## Build Container

```bash
docker build -t aks-config-api:latest .
```

## Push to Azure Container Registry

```bash
# Tag the image
docker tag aks-config-api:latest <your-acr>.azurecr.io/aks-config-api:latest

# Push to ACR
docker push <your-acr>.azurecr.io/aks-config-api:latest
```

## Deploy to AKS

1. Create ConfigMap:
   ```bash
   kubectl apply -f ../k8s/configmap.yaml
   ```

2. Create Secrets:
   ```bash
   kubectl apply -f ../k8s/secrets.yaml
   ```

3. Create Persistent Volume Claim:
   ```bash
   kubectl apply -f ../k8s/pvc.yaml
   ```

4. Update deployment.yaml with your ACR endpoint, then deploy:
   ```bash
   kubectl apply -f ../k8s/deployment.yaml
   ```

5. Create Service:
   ```bash
   kubectl apply -f ../k8s/service.yaml
   ```

## Verify Deployment

```bash
# Check pods
kubectl get pods

# Check services
kubectl get services

# Check logs
kubectl logs <pod-name>

# Check ConfigMap
kubectl describe configmap api-config

# Check Secrets
kubectl describe secret api-secrets

# Check PVC
kubectl get pvc
```
