"""
Telemetry generator functions for the analyze logs exercise.
These functions generate sample request, dependency, and exception telemetry
that can be queried with KQL in Application Insights.
"""
import os
import time
import random
from azure.identity import DefaultAzureCredential
from opentelemetry import trace
from opentelemetry.trace import StatusCode, SpanKind


def get_tracer():
    """Get an OpenTelemetry tracer for creating custom spans."""
    return trace.get_tracer("document-pipeline")


def configure_telemetry():
    """Configure the Azure Monitor OpenTelemetry Distro."""
    connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")

    if not connection_string:
        raise ValueError(
            "APPLICATIONINSIGHTS_CONNECTION_STRING environment variable must be set"
        )

    from azure.monitor.opentelemetry import configure_azure_monitor

    credential = DefaultAzureCredential(
        exclude_managed_identity_credential=True
    )

    configure_azure_monitor(
        connection_string=connection_string,
        credential=credential,
    )


def generate_requests():
    """Generate sample request spans that appear in the requests table."""
    tracer = get_tracer()
    services = ["api-gateway", "doc-processor", "auth-service"]
    endpoints = [
        ("/api/documents", "POST"),
        ("/api/documents/{id}", "GET"),
        ("/api/status", "GET"),
        ("/api/process", "POST"),
        ("/api/auth/token", "POST"),
    ]
    results = []

    for i in range(15):
        service = services[i % len(services)]
        path, method = endpoints[i % len(endpoints)]

        # Some requests fail to create realistic failure data
        should_fail = i in (3, 7, 11, 13)
        status_code = "500" if should_fail and i in (3, 11) else "429" if should_fail else "200"

        with tracer.start_as_current_span(
            f"{method} {path}",
            kind=SpanKind.SERVER,
        ) as span:
            span.set_attribute("http.method", method)
            span.set_attribute("http.url", f"https://{service}.example.com{path}")
            span.set_attribute("http.status_code", int(status_code))
            span.set_attribute("http.route", path)
            span.set_attribute("cloud.role.name", service)

            duration = random.uniform(0.05, 0.3) if not should_fail else random.uniform(0.5, 2.0)
            time.sleep(duration)

            if should_fail:
                span.set_status(StatusCode.ERROR, f"HTTP {status_code}")
            else:
                span.set_status(StatusCode.OK)

        results.append({
            "service": service,
            "endpoint": f"{method} {path}",
            "status": status_code,
            "failed": should_fail,
        })

    return results


def generate_dependencies():
    """Generate sample dependency spans that appear in the dependencies table."""
    tracer = get_tracer()
    targets = [
        ("blob-storage.blob.core.windows.net", "Azure blob"),
        ("cosmos-db.documents.azure.com", "Azure DocumentDB"),
        ("redis-cache.redis.cache.windows.net", "InProc"),
    ]
    results = []

    for i in range(12):
        target_host, dep_type = targets[i % len(targets)]

        # Some dependencies are slow to create varied latency data
        is_slow = i in (2, 5, 8)

        with tracer.start_as_current_span(
            f"call {target_host}",
            kind=SpanKind.CLIENT,
        ) as span:
            span.set_attribute("peer.service", target_host)
            span.set_attribute("db.system", dep_type)
            span.set_attribute("cloud.role.name", "doc-processor")

            if is_slow:
                duration = random.uniform(1.5, 3.0)
            else:
                duration = random.uniform(0.02, 0.2)

            time.sleep(duration)
            span.set_status(StatusCode.OK)

        results.append({
            "target": target_host,
            "type": dep_type,
            "slow": is_slow,
        })

    return results


def generate_exceptions():
    """Generate exception telemetry correlated with request spans."""
    tracer = get_tracer()
    exception_scenarios = [
        ("doc-processor", "/api/process", "ValueError", "Invalid document format: missing required field 'title'"),
        ("api-gateway", "/api/documents", "TimeoutError", "Upstream service did not respond within 30s"),
        ("auth-service", "/api/auth/token", "PermissionError", "Token refresh failed: invalid grant"),
        ("doc-processor", "/api/documents/{id}", "FileNotFoundError", "Document DOC-9999 not found in storage"),
        ("api-gateway", "/api/process", "ConnectionError", "Failed to connect to downstream service"),
    ]
    results = []

    for service, path, exc_type, exc_message in exception_scenarios:
        with tracer.start_as_current_span(
            f"POST {path}",
            kind=SpanKind.SERVER,
        ) as span:
            span.set_attribute("http.method", "POST")
            span.set_attribute("http.url", f"https://{service}.example.com{path}")
            span.set_attribute("http.status_code", 500)
            span.set_attribute("cloud.role.name", service)

            time.sleep(random.uniform(0.05, 0.2))

            exc_class = type(exc_type, (Exception,), {})
            exception = exc_class(exc_message)
            span.record_exception(exception)
            span.set_status(StatusCode.ERROR, exc_message)

        results.append({
            "service": service,
            "exception_type": exc_type,
            "message": exc_message,
        })

    return results
