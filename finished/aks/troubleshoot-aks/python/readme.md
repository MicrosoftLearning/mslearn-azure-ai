# Troubleshoot an app in AKS

In this exercise, you practice diagnosing and fixing common issues with applications running on Azure Kubernetes Service. You deploy a mock API, intentionally break it in several ways, and use `kubectl` commands to identify and resolve each problem.

**Estimated time:** 30-40 minutes

## Task 1: Deploy the sample application (~5 minutes)

In this task, you deploy a working application and verify it's healthy before introducing issues.

1. Verify that `kubectl` points to the target AKS cluster.

    ```bash
    kubectl config current-context
    ```

1. Create a namespace for the exercise.

    ```bash
    kubectl create namespace troubleshoot-lab
    ```

1. Deploy the sample API and Service.

    ```bash
    kubectl apply -f api-deployment.yaml -n troubleshoot-lab
    kubectl apply -f api-service.yaml -n troubleshoot-lab
    ```

1. Verify that the pod is running and the Service has endpoints.

    ```bash
    kubectl get pods -n troubleshoot-lab
    kubectl get endpoints -n troubleshoot-lab
    ```

1. Test connectivity with port-forward.

    ```bash
    kubectl port-forward service/api-service 8080:80 -n troubleshoot-lab
    ```

1. In a separate terminal, send a test request.

    ```bash
    curl http://localhost:8080/healthz
    ```

You should receive a successful response. Stop the port-forward (Ctrl+C) before continuing.

## Task 2: Diagnose a label mismatch (~7 minutes)

A Service routes traffic to pods based on label selectors. When labels don't match, the Service has no endpoints and requests fail.

1. Edit the Deployment to change the pod label from `app: api` to `app: api-v2`.

    ```bash
    kubectl edit deployment api-deployment -n troubleshoot-lab
    ```

1. Wait for the new pod to start, then check the Service endpoints.

    ```bash
    kubectl get pods --show-labels -n troubleshoot-lab
    kubectl get endpoints api-service -n troubleshoot-lab
    ```

    Notice the endpoints list is empty.

1. Compare the Service selector with the pod labels.

    ```bash
    kubectl describe service api-service -n troubleshoot-lab | grep Selector
    kubectl get pods --show-labels -n troubleshoot-lab
    ```

1. Fix the issue by changing the pod label back to `app: api`, or update the Service selector to match `app: api-v2`.

1. Verify the endpoints are restored.

    ```bash
    kubectl get endpoints api-service -n troubleshoot-lab
    ```

## Task 3: Diagnose a CrashLoopBackOff (~8 minutes)

When a container fails to start, Kubernetes repeatedly restarts it, resulting in `CrashLoopBackOff` status. Reading logs reveals why the application crashed.

1. Edit the Deployment to remove or rename the required `API_KEY` environment variable.

    ```bash
    kubectl edit deployment api-deployment -n troubleshoot-lab
    ```

1. Watch the pod status.

    ```bash
    kubectl get pods -n troubleshoot-lab -w
    ```

    After a few moments, the pod enters `CrashLoopBackOff`.

1. Check the pod logs for the error message.

    ```bash
    kubectl logs <pod-name> -n troubleshoot-lab
    ```

    You should see an error indicating the missing environment variable.

1. Inspect the pod events for additional context.

    ```bash
    kubectl describe pod <pod-name> -n troubleshoot-lab
    ```

1. Fix the issue by restoring the `API_KEY` environment variable in the Deployment.

1. Verify the pod returns to `Running` status.

    ```bash
    kubectl get pods -n troubleshoot-lab
    ```

## Task 4: Diagnose a port mismatch (~7 minutes)

When the Service targetPort doesn't match the container's listening port, connections are refused even though the pod is running.

1. Edit the Service to change `targetPort` from `8000` to `9000`.

    ```bash
    kubectl edit service api-service -n troubleshoot-lab
    ```

1. Attempt to connect via port-forward.

    ```bash
    kubectl port-forward service/api-service 8080:80 -n troubleshoot-lab
    ```

1. In a separate terminal, send a request.

    ```bash
    curl http://localhost:8080/healthz
    ```

    The connection is refused, even though the pod shows `Running`.

1. Use `kubectl exec` to test the port from inside the cluster.

    ```bash
    kubectl exec -it <pod-name> -n troubleshoot-lab -- wget -qO- http://localhost:8000/healthz
    ```

    This works because you're connecting directly to the container's actual port.

1. Fix the Service by setting `targetPort` back to `8000`.

1. Test again with port-forward to confirm connectivity is restored.

## Task 5: Diagnose a readiness probe failure (~8 minutes)

When a readiness probe fails, the pod shows `Running` but `0/1` containers are ready. Kubernetes removes the pod from the Service endpoints, so no traffic is routed to it.

1. Edit the Deployment to change the readiness probe path from `/healthz` to `/invalid-path`.

    ```bash
    kubectl edit deployment api-deployment -n troubleshoot-lab
    ```

1. Watch the pod status.

    ```bash
    kubectl get pods -n troubleshoot-lab
    ```

    The pod shows `Running` but `0/1` in the READY column.

1. Check the pod events for probe failures.

    ```bash
    kubectl describe pod <pod-name> -n troubleshoot-lab
    ```

    Look for `Readiness probe failed` in the Events section.

1. Verify the Service has no endpoints.

    ```bash
    kubectl get endpoints api-service -n troubleshoot-lab
    ```

1. Fix the readiness probe path back to `/healthz`.

1. Verify the pod becomes ready and endpoints are restored.

    ```bash
    kubectl get pods -n troubleshoot-lab
    kubectl get endpoints api-service -n troubleshoot-lab
    ```

## Task 6: Verify end-to-end connectivity (~5 minutes)

After completing all troubleshooting scenarios, confirm the application is fully functional.

1. Use port-forward to access the Service.

    ```bash
    kubectl port-forward service/api-service 8080:80 -n troubleshoot-lab
    ```

1. In a separate terminal, test all endpoints.

    ```bash
    curl http://localhost:8080/healthz
    curl http://localhost:8080/readyz
    curl http://localhost:8080/api/info
    ```

1. Check the pod logs to see the requests.

    ```bash
    kubectl logs <pod-name> -n troubleshoot-lab
    ```

## Summary

In this exercise, you practiced four common troubleshooting scenarios:

| Scenario | Symptom | Key Commands |
|----------|---------|--------------|
| Label mismatch | Service has no endpoints | `kubectl get endpoints`, `kubectl describe svc` |
| CrashLoopBackOff | Pod repeatedly restarts | `kubectl logs`, `kubectl describe pod` |
| Port mismatch | Connection refused, pod running | `kubectl exec`, compare Service and container ports |
| Readiness probe failure | Pod running but 0/1 ready | `kubectl describe pod`, check Events section |

These diagnostic techniques apply to any application running on Kubernetes, regardless of the workload type.
