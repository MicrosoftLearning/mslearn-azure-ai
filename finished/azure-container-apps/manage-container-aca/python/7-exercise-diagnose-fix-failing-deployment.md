# Exercise - Diagnose and fix a failing deployment

In this exercise, you troubleshoot a failing revision and apply a targeted fix. The goal is to practice a repeatable workflow that uses revision status, logs, and probe configuration to isolate a deployment issue. This workflow is common in AI solutions because startup behavior changes frequently when you update models and dependencies.

> [!NOTE]
> This exercise uses Azure CLI patterns and assumes you have access to an Azure subscription with permission to manage Azure Container Apps resources. You can adapt the steps to an existing container app, or you can create a new one if your environment requires it.

## Setup

Before you start, confirm you have a container app with an ingress-enabled HTTP service. If you are using an existing app, note the resource group, app name, and current active revision. If you create a new app for practice, keep the configuration minimal so you can focus on revision troubleshooting.

## Create a failing revision

You need a controlled failure so you can practice diagnosis. A common and realistic failure is a readiness probe configuration that points to the wrong path, which causes the platform to keep the revision unready.

1. Update your container app in a way that creates a new revision with an incorrect readiness probe path.
1. Wait for the new revision to start.
1. Confirm the new revision is present and identify its revision name.

Use revision listing to confirm which revision is active and which revision is unhealthy.

```azurecli
az containerapp revision list \
  --name <app-name> \
  --resource-group <resource-group> \
  -o table
```

## Observe symptoms and collect evidence

In a real incident, you should avoid making random changes until you understand the failure mode. Collect evidence first. Evidence includes revision state and log output during startup.

1. Stream logs while the failing revision attempts to become ready.
1. Look for errors that indicate probe failure or missing routes.

```azurecli
az containerapp logs show \
  --name <app-name> \
  --resource-group <resource-group> \
  --follow
```

## Fix the configuration and roll forward

Once you confirm the issue is probe-related, apply a targeted fix. The best fix is to update the probe path and timing so readiness matches your service behavior.

1. Update the container app configuration to set the correct readiness probe path.
1. Create a new revision with the corrected configuration.
1. Validate that the new revision becomes ready.

If your app uses multiple revision mode, keep the healthy revision active and confirm it receives traffic. If your app is in single revision mode, confirm that the updated revision replaces the prior active revision.

## Clean up stale revisions

Cleanup is part of day-two management. After validation, deactivate unneeded revisions so the next incident investigation is easier. Container Apps automatically purges inactive revisions when you exceed 100, so explicit deletion is not required.

1. Deactivate the failing revision so it cannot receive traffic.
1. Confirm the revision is inactive and no longer receiving requests.

```azurecli
az containerapp revision deactivate \
  --name <app-name> \
  --resource-group <resource-group> \
  --revision <failing-revision-name>
```

## Success criteria

Success criteria help you confirm you fixed the right problem instead of introducing a workaround. They also reflect the signals you typically validate during a real on-call incident.

To complete the exercise, verify these outcomes:

- The corrected revision becomes ready and receives traffic.
- Logs show clean startup and no repeated probe failure messages.
- The container app has only the revisions you need for rollback and investigation.

## Additional resources

These resources provide deeper reference material for probe behavior, revision state, and log collection. Use them when you want to extend the exercise into a team runbook.

- [Azure Container Apps health probes](/azure/container-apps/health-probes)
- [Azure Container Apps logging](/azure/container-apps/logging)
- [Azure Container Apps revisions](/azure/container-apps/revisions)
