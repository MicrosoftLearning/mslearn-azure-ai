In this exercise, you write KQL queries to investigate application telemetry in Application Insights and use the Azure CLI to configure alerting. You query the `requests`, `exceptions`, and `dependencies` tables to identify errors and analyze performance, then create an action group and a log search alert rule using CLI commands.

## Query request telemetry

You can start by querying the `requests` table to understand the overall health of the document processing pipeline. The following query retrieves failed requests from the last 24 hours, grouped by service and response code, to identify which services experience the most failures:

```kusto
requests
| where timestamp > ago(24h)
| where success == false
| summarize failedCount = count() by cloud_RoleName, resultCode
| order by failedCount desc
```

This query shows a breakdown of failures by service and HTTP status code. You can use these results to determine whether failures concentrate in a specific service or spread across the entire pipeline.

To understand request volume and performance across the pipeline, write a query that summarizes request counts and average duration by service over hourly intervals:

```kusto
requests
| where timestamp > ago(24h)
| summarize requestCount = count(), avgDuration = avg(duration),
    p95Duration = percentile(duration, 95)
    by bin(timestamp, 1h), cloud_RoleName
| order by timestamp desc
```

The `p95Duration` column reveals the response time experienced by the slowest five percent of requests. Comparing the average duration to the 95th percentile highlights services where most requests are fast but a subset experiences significant delays.

## Join exceptions with requests

You can correlate exceptions with the requests that triggered them by joining the `exceptions` and `requests` tables on `operation_Id`. This join reveals which requests generate the most errors and which exception types are involved:

```kusto
exceptions
| where timestamp > ago(24h)
| join kind=inner (
    requests
    | where timestamp > ago(24h)
) on operation_Id
| summarize exceptionCount = count() by requestName = name1,
    exceptionType = type, cloud_RoleName
| order by exceptionCount desc
| take 15
```

Each row shows a combination of request name, exception type, and service. This view helps you identify the specific operations that produce the most exceptions and the types of errors involved.

To find the full details of a specific failure, you can query a single operation by its `operation_Id`. First, identify an `operation_Id` from the previous query results, then query all telemetry for that operation:

```kusto
union requests, dependencies, exceptions, traces
| where operation_Id == "replace-with-actual-operation-id"
| order by timestamp asc
| project timestamp, itemType, name, resultCode, success, duration, type, message
```

This query shows the complete timeline of a single distributed request. You can see each dependency call, exception, and trace message in chronological order, which helps identify exactly where in the processing chain the failure occurred.

## Analyze dependency latency

You can analyze dependency performance to identify slow external calls that affect pipeline throughput. The following query calculates latency percentiles for each dependency target:

```kusto
dependencies
| where timestamp > ago(24h)
| summarize callCount = count(),
    avgDuration = avg(duration),
    p50 = percentile(duration, 50),
    p95 = percentile(duration, 95),
    p99 = percentile(duration, 99)
    by target, type
| order by p95 desc
```

The results reveal which dependencies contribute the most latency. A large gap between the p50 and p95 values indicates inconsistent performance, where most calls are fast but a notable percentage takes much longer.

To visualize dependency latency over time for the slowest dependency target, write a query that creates a time chart:

```kusto
dependencies
| where timestamp > ago(24h)
| where target == "replace-with-target-name"
| summarize p95Duration = percentile(duration, 95) by bin(timestamp, 15m)
| render timechart
```

This chart shows how the 95th-percentile latency for a specific dependency changes over time, helping you identify time periods when the dependency degrades.

## Create an action group and alert rule with Azure CLI

You can use the Azure CLI to create an action group that sends email notifications when alerts fire. The following command creates an action group with an email notification:

```azurecli
az monitor action-group create \
    --resource-group myResourceGroup \
    --name pipeline-alerts-ag \
    --short-name PipeAlert \
    --action email oncall-email oncall@contoso.com
```

This command creates an action group named `pipeline-alerts-ag` with a single email action that sends notifications to the on-call team's email address.

Next, you can create a log search alert rule that detects when the failure rate exceeds a threshold. The following command creates a scheduled query alert that monitors the Application Insights resource for failed requests:

```azurecli
az monitor scheduled-query create \
    --resource-group myResourceGroup \
    --name high-failure-rate-alert \
    --scopes "/subscriptions/{sub-id}/resourceGroups/myResourceGroup/providers/microsoft.insights/components/myAppInsights" \
    --condition "count 'FailedRequests' > 10" \
    --condition-query FailedRequests="requests | where success == false" \
    --action-groups "/subscriptions/{sub-id}/resourceGroups/myResourceGroup/providers/microsoft.insights/actionGroups/pipeline-alerts-ag" \
    --evaluation-frequency 5m \
    --window-size 5m \
    --severity 1 \
    --description "Alert when more than 10 requests fail in a 5-minute window"
```

This command creates a log search alert rule that runs every five minutes. The rule evaluates the query `requests | where success == false` over a five-minute window and fires the alert if the count exceeds ten. When the alert fires, it triggers the `pipeline-alerts-ag` action group, which sends an email notification. The severity is set to one (Error) to indicate a significant but not outage-level problem.

You can verify the alert rule was created successfully by listing the scheduled queries in the resource group:

```azurecli
az monitor scheduled-query list --resource-group myResourceGroup --output table
```

## Additional resources

- [Get started with log queries](/azure/azure-monitor/logs/get-started-queries)
- [Action groups](/azure/azure-monitor/alerts/action-groups)
- [az monitor scheduled-query](/cli/azure/monitor/scheduled-query)
