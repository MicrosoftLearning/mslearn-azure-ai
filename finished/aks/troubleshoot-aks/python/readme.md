# Troubleshoot an app in AKS

## Task 1: Prepare the AKS environment

In this task, you confirm that you are connected to the correct cluster and create a namespace for the exercise.

1. Verify that `kubectl` points to the target AKS cluster.
2. Create a namespace for AI workloads.

Example commands:

```bash
kubectl config current-context
kubectl create namespace ai-workloads
kubectl get namespaces
```

You should see the new namespace in the list.

## Task 2: Deploy the sample AI application

Next, you deploy a simple HTTP API that simulates an AI inference service. The application exposes an endpoint that returns a fixed response or echoes back input.

1. Create a Deployment manifest file for the sample API.
2. Apply the manifest to the `ai-workloads` namespace.
3. Create a Service that exposes the Deployment inside the cluster.

Example commands:

```bash
kubectl apply -f inference-deployment.yaml -n ai-workloads
kubectl apply -f inference-service.yaml -n ai-workloads
kubectl get pods -n ai-workloads
kubectl get service -n ai-workloads
```

You confirm that pods move to the Running state and the Service appears.

## Task 3: Monitor logs and metrics

With the application running, you monitor its behavior.

1. Use `kubectl logs` to observe startup messages and request handling.
2. Send test requests to generate activity.
3. Use `kubectl top` to inspect resource usage if metrics are available.

Example commands:

```bash
kubectl logs <pod-name> -n ai-workloads
kubectl logs -f <pod-name> -n ai-workloads
kubectl top pods -n ai-workloads
```

You look for error messages or warnings in logs and note whether CPU or memory usage appears normal for the workload. If `kubectl top` reports that metrics are unavailable, your cluster might not have the metrics server or AKS monitoring features enabled, so you focus on logs and other signals instead.

## Task 4: Troubleshoot a simulated issue

Now you introduce a configuration issue and use troubleshooting techniques to find and fix it.

1. Update the Deployment manifest to include an incorrect environment variable or label.
2. Reapply the manifest so the cluster picks up the change.
3. Observe the impact on pods and Services.

You might see pods enter `CrashLoopBackOff` or a Service with no endpoints. You then:

- Use `kubectl describe pod` to inspect events and environment variables
- Use `kubectl describe service` and `kubectl get endpoints` to check label selectors
- Use `kubectl exec` to open a shell in a container and confirm configuration

After you identify the root cause, you correct the manifest and reapply it. You confirm that pods return to a healthy state and that the Service routes traffic again.

## Task 5: Verify connectivity end-to-end

Finally, you verify that clients can reach the AI endpoint.

1. Use `kubectl port-forward` to send requests from your workstation to the Service.
2. Optionally, configure or inspect a LoadBalancer Service or ingress rule and test from outside the cluster.

Example commands:

```bash
kubectl port-forward service/inference-api 8080:80 -n ai-workloads
curl http://localhost:8080/api/inference
```

You look for successful responses and correlate them with logs and metrics. At the end of the exercise, you have practiced a complete loop of deploying, monitoring, troubleshooting, and verifying an AI application on AKS.
