"""
Telemetry generator for the analyze logs exercise.
Generates sample request, dependency, and exception telemetry
and exports it to Application Insights.
"""
from analyze_logs_functions import (
    configure_telemetry,
    generate_requests,
    generate_dependencies,
    generate_exceptions,
)

# Configure telemetry before generating spans
configure_telemetry()

print("Generating telemetry data for Application Insights...")
print("")

print("Generating request telemetry...")
request_results = generate_requests()
success_count = sum(1 for r in request_results if not r["failed"])
fail_count = sum(1 for r in request_results if r["failed"])
print(f"  Created {len(request_results)} request spans ({success_count} succeeded, {fail_count} failed)")

print("Generating dependency telemetry...")
dep_results = generate_dependencies()
slow_count = sum(1 for r in dep_results if r["slow"])
print(f"  Created {len(dep_results)} dependency spans ({slow_count} with high latency)")

print("Generating exception telemetry...")
exc_results = generate_exceptions()
print(f"  Created {len(exc_results)} exception spans")

print("")
print("Telemetry generation complete.")
print("Wait 2-3 minutes for the data to appear in Application Insights before running queries.")
