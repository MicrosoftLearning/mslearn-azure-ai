"""
OpenTelemetry instrumentation functions for tracing a document processing pipeline.
These functions serve as the interface between the Flask app and the OpenTelemetry SDK.
"""
import os
import time
import random
from azure.identity import DefaultAzureCredential
from opentelemetry import trace
from opentelemetry.trace import StatusCode


def get_tracer():
    """Get an OpenTelemetry tracer for creating custom spans."""
    return trace.get_tracer("document-pipeline")


# BEGIN CONFIGURE TELEMETRY FUNCTION
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
# END CONFIGURE TELEMETRY FUNCTION


# BEGIN PROCESS DOCUMENTS FUNCTION
def process_documents(doc_count):
    """Process a batch of documents through the pipeline with tracing."""
    tracer = get_tracer()
    results = []

    with tracer.start_as_current_span("process-documents") as parent_span:
        parent_span.set_attribute("document.count", doc_count)
        parent_span.set_attribute("pipeline.name", "document-processing")

        for i in range(1, doc_count + 1):
            doc_id = f"DOC-{i:04d}"

            validate_result = validate_document(doc_id)
            enrich_result = enrich_document(doc_id)
            store_result = store_document(doc_id)

            results.append({
                "doc_id": doc_id,
                "validate": validate_result,
                "enrich": enrich_result,
                "store": store_result
            })

        parent_span.set_attribute("document.processed", len(results))

    return results
# END PROCESS DOCUMENTS FUNCTION


# BEGIN PIPELINE STAGE FUNCTIONS
def validate_document(doc_id):
    """Validate a document and record a traced span."""
    tracer = get_tracer()

    with tracer.start_as_current_span("validate-document") as span:
        span.set_attribute("document.id", doc_id)
        span.set_attribute("document.stage", "validate")

        # Simulate validation work
        time.sleep(random.uniform(0.05, 0.15))
        is_valid = True

        span.set_attribute("document.valid", is_valid)
        span.set_status(StatusCode.OK)

    return {"status": "valid", "duration_ms": round(random.uniform(50, 150))}


def enrich_document(doc_id):
    """Enrich a document with metadata and record a traced span."""
    tracer = get_tracer()

    with tracer.start_as_current_span("enrich-document") as span:
        span.set_attribute("document.id", doc_id)
        span.set_attribute("document.stage", "enrich")

        # Simulated latency issue: documents DOC-0003 and DOC-0005
        # experience high latency during enrichment, representing
        # a bottleneck for the student to diagnose in Application Insights
        if doc_id in ("DOC-0003", "DOC-0005"):
            delay = random.uniform(1.5, 3.0)
            span.set_attribute("enrichment.slow", True)
        else:
            delay = random.uniform(0.05, 0.2)
            span.set_attribute("enrichment.slow", False)

        time.sleep(delay)
        span.set_attribute("enrichment.duration_s", round(delay, 3))
        span.set_status(StatusCode.OK)

    return {
        "status": "enriched",
        "duration_ms": round(delay * 1000),
        "slow": doc_id in ("DOC-0003", "DOC-0005")
    }


def store_document(doc_id):
    """Store a document and record a traced span."""
    tracer = get_tracer()

    with tracer.start_as_current_span("store-document") as span:
        span.set_attribute("document.id", doc_id)
        span.set_attribute("document.stage", "store")
        span.set_attribute("storage.type", "blob")

        # Simulate storage write
        time.sleep(random.uniform(0.05, 0.2))

        span.set_status(StatusCode.OK)

    return {"status": "stored", "duration_ms": round(random.uniform(50, 200))}
# END PIPELINE STAGE FUNCTIONS


def check_telemetry_status():
    """Check the current telemetry configuration status."""
    tracer_provider = trace.get_tracer_provider()
    resource = getattr(tracer_provider, "resource", None)

    resource_attrs = {}
    if resource:
        resource_attrs = dict(resource.attributes)

    span_processors = []
    if hasattr(tracer_provider, "_active_span_processor"):
        processor = tracer_provider._active_span_processor
        if hasattr(processor, "_span_processors"):
            for sp in processor._span_processors:
                span_processors.append(type(sp).__name__)
        else:
            span_processors.append(type(processor).__name__)

    return {
        "tracer_provider": type(tracer_provider).__name__,
        "resource_attributes": resource_attrs,
        "span_processors": span_processors,
        "configured": type(tracer_provider).__name__ != "ProxyTracerProvider"
    }
