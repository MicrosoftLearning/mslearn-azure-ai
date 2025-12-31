# Troubleshoot an app in AKS

In this exercise, you practice diagnosing and fixing common issues with applications running on Azure Kubernetes Service. You deploy a mock API, intentionally break it in several ways, and use `kubectl` commands to identify and resolve each problem.

**Estimated time:** 30-40 minutes

## Task 1: Verify the deployment (~5 minutes)

In this task, you confirm the application deployed by the setup script is running correctly.

1. Run the deployment script and complete options 1-6 to provision Azure resources and deploy the application. This process takes approximately 10-15 minutes.

    - **Bash (Linux/macOS):** `bash azdeploy.sh`
    - **PowerShell (Windows/Linux/macOS):** `pwsh azdeploy.ps1`

1. Verify that the pod is running and the Service has endpoints.

    ```
    kubectl get pods -n aks-troubleshoot
    kubectl get endpointslices -n aks-troubleshoot
    ```

    You should see one pod in `Running` status and one endpoint slice listed.

1. Test connectivity with port-forward.

    ```
    kubectl port-forward service/api-service 8080:80 -n aks-troubleshoot
    ```

1. In a separate terminal on your workstation, send a test request.

    - **Bash/macOS/Linux:** `curl http://localhost:8080/healthz`
    - **PowerShell:** `Invoke-RestMethod http://localhost:8080/healthz`

    You should receive a JSON response with `"status": "healthy"`.

1. Stop the port-forward (Ctrl+C) before continuing to the troubleshooting tasks.

## Task 2: Diagnose a label mismatch (~7 minutes)

A Service routes traffic to pods based on label selectors. When labels don't match, the Service has no endpoints and requests fail.

1. Edit the Deployment to change the pod label from `app: api` to `app: api-v2`.

    ```
    kubectl edit deployment api-deployment -n aks-troubleshoot
    ```

1. Wait for the new pod to start, then check the Service endpoint slices.

    ```
    kubectl get pods --show-labels -n aks-troubleshoot
    kubectl get endpointslices -l kubernetes.io/service-name=api-service -n aks-troubleshoot
    ```

    Notice the endpoint slice shows no addresses.

1. Compare the Service selector with the pod labels.

    ```
    kubectl describe service api-service -n aks-troubleshoot
    kubectl get pods --show-labels -n aks-troubleshoot
    ```

    Look for the `Selector` field in the Service description and compare it to the pod labels.

1. Fix the issue by changing the pod label back to `app: api`, or update the Service selector to match `app: api-v2`.

1. Verify the endpoint slice addresses are restored.

    ```
    kubectl get endpointslices -l kubernetes.io/service-name=api-service -n aks-troubleshoot
    ```

## Task 3: Diagnose a CrashLoopBackOff (~8 minutes)

When a container fails to start, Kubernetes repeatedly restarts it, resulting in `CrashLoopBackOff` status. Reading logs reveals why the application crashed.

1. Edit the Deployment to remove or rename the required `API_KEY` environment variable.

    ```
    kubectl edit deployment api-deployment -n aks-troubleshoot
    ```

1. Watch the pod status.

    ```
    kubectl get pods -n aks-troubleshoot -w
    ```

    After a few moments, the pod enters `CrashLoopBackOff`.

1. Check the pod logs for the error message.

    ```
    kubectl logs <pod-name> -n aks-troubleshoot
    ```

    You should see an error indicating the missing environment variable.

1. Inspect the pod events for additional context.

    ```
    kubectl describe pod <pod-name> -n aks-troubleshoot
    ```

1. Fix the issue by restoring the `API_KEY` environment variable in the Deployment.

1. Verify the pod returns to `Running` status.

    ```
    kubectl get pods -n aks-troubleshoot
    ```

## Task 4: Diagnose a port mismatch (~7 minutes)

When the Service targetPort doesn't match the container's listening port, connections are refused even though the pod is running.

1. Edit the Service to change `targetPort` from `8000` to `9000`.

    ```
    kubectl edit service api-service -n aks-troubleshoot
    ```

1. Attempt to connect via port-forward.

    ```
    kubectl port-forward service/api-service 8080:80 -n aks-troubleshoot
    ```

1. In a separate terminal, send a request.

    - **Bash/macOS/Linux:** `curl http://localhost:8080/healthz`
    - **PowerShell:** `Invoke-RestMethod http://localhost:8080/healthz`

    The connection is refused, even though the pod shows `Running`.

1. Use `kubectl exec` to test the port from inside the container.

    ```
    kubectl exec -it <pod-name> -n aks-troubleshoot -- wget -qO- http://localhost:8000/healthz
    ```

    This works because you're connecting directly to the container's actual port.

1. Fix the Service by setting `targetPort` back to `8000`.

1. Test again with port-forward to confirm connectivity is restored.

## Task 5: Diagnose a readiness probe failure (~8 minutes)

When a readiness probe fails, the pod shows `Running` but `0/1` containers are ready. Kubernetes removes the pod from the Service endpoints, so no traffic is routed to it.

1. Edit the Deployment to change the readiness probe path from `/healthz` to `/invalid-path`.

    ```
    kubectl edit deployment api-deployment -n aks-troubleshoot
    ```

1. Watch the pod status.

    ```
    kubectl get pods -n aks-troubleshoot
    ```

    The pod shows `Running` but `0/1` in the READY column.

1. Check the pod events for probe failures.

    ```
    kubectl describe pod <pod-name> -n aks-troubleshoot
    ```

    Look for `Readiness probe failed` in the Events section.

1. Verify the Service endpoint slice has no addresses.

    ```
    kubectl get endpointslices -l kubernetes.io/service-name=api-service -n aks-troubleshoot
    ```

1. Fix the readiness probe path back to `/healthz`.

1. Verify the pod becomes ready and endpoint slice addresses are restored.

    ```
    kubectl get pods -n aks-troubleshoot
    kubectl get endpointslices -l kubernetes.io/service-name=api-service -n aks-troubleshoot
    ```

## Task 6: Verify end-to-end connectivity (~5 minutes)

After completing all troubleshooting scenarios, confirm the application is fully functional.

1. Use port-forward to access the Service.

    ```
    kubectl port-forward service/api-service 8080:80 -n aks-troubleshoot
    ```

1. In a separate terminal, test all endpoints.

    - **Bash/macOS/Linux:**

        ```
        curl http://localhost:8080/healthz
        curl http://localhost:8080/readyz
        curl http://localhost:8080/api/info
        ```

    - **PowerShell:**

        ```powershell
        Invoke-RestMethod http://localhost:8080/healthz
        Invoke-RestMethod http://localhost:8080/readyz
        Invoke-RestMethod http://localhost:8080/api/info
        ```

1. Check the pod logs to see the requests.

    ```
    kubectl logs <pod-name> -n aks-troubleshoot
    ```

## Summary

In this exercise, you practiced four common troubleshooting scenarios:

| Scenario | Symptom | Key Commands |
|----------|---------|--------------|
| Label mismatch | Service has no endpoints | `kubectl get endpointslices`, `kubectl describe svc` |
| CrashLoopBackOff | Pod repeatedly restarts | `kubectl logs`, `kubectl describe pod` |
| Port mismatch | Connection refused, pod running | `kubectl exec`, compare Service and container ports |
| Readiness probe failure | Pod running but 0/1 ready | `kubectl describe pod`, check Events section |

These diagnostic techniques apply to any application running on Kubernetes, regardless of the workload type.
