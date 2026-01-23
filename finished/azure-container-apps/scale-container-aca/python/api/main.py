"""Service Bus queue processor for Azure Container Apps scaling exercise.

This application processes messages from an Azure Service Bus queue using managed
identity authentication. It includes a configurable processing delay to demonstrate
KEDA-based autoscaling behavior in Container Apps.
"""

import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone

from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusReceiveMode
from flask import Flask, jsonify

# Configuration from environment variables
SERVICE_BUS_NAMESPACE = os.getenv("SERVICE_BUS_NAMESPACE", "")
QUEUE_NAME = os.getenv("QUEUE_NAME", "orders")
PROCESSING_DELAY_SECONDS = int(os.getenv("PROCESSING_DELAY_SECONDS", "2"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8080"))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Flask app for health endpoint
app = Flask(__name__)

# Global state for health checks
processor_healthy = True
messages_processed = 0
shutdown_requested = False


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for Container Apps probes."""
    if processor_healthy:
        return jsonify({
            "status": "healthy",
            "messages_processed": messages_processed,
            "queue_name": QUEUE_NAME,
            "namespace": SERVICE_BUS_NAMESPACE,
        })
    return jsonify({"status": "unhealthy"}), 503


@app.route("/", methods=["GET"])
def root():
    """Service info endpoint."""
    return jsonify({
        "service": "Service Bus Queue Processor",
        "status": "running",
        "version": "1.0.0",
        "config": {
            "namespace": SERVICE_BUS_NAMESPACE,
            "queue_name": QUEUE_NAME,
            "processing_delay_seconds": PROCESSING_DELAY_SECONDS,
        },
        "stats": {
            "messages_processed": messages_processed,
        },
    })


def run_health_server():
    """Run the Flask health server in a separate thread."""
    logger.info("Starting health server on port %d", HEALTH_PORT)
    app.run(host="0.0.0.0", port=HEALTH_PORT, threaded=True, use_reloader=False)


def process_message(message_body: str) -> None:
    """Process a single message with configurable delay.

    The delay simulates work and allows scaling behavior to be observed.
    """
    global messages_processed

    logger.info("Processing message: %s", message_body[:100] if len(message_body) > 100 else message_body)

    # Simulate processing work
    time.sleep(PROCESSING_DELAY_SECONDS)

    messages_processed += 1
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    logger.info("Message processed at %s (total: %d)", timestamp, messages_processed)


def handle_shutdown(signum, frame):
    """Handle graceful shutdown on SIGTERM/SIGINT."""
    global shutdown_requested
    logger.info("Shutdown signal received, finishing current message...")
    shutdown_requested = True


def run_queue_processor():
    """Main loop to receive and process messages from Service Bus."""
    global processor_healthy

    if not SERVICE_BUS_NAMESPACE:
        logger.error("SERVICE_BUS_NAMESPACE environment variable is required")
        processor_healthy = False
        sys.exit(1)

    fully_qualified_namespace = f"{SERVICE_BUS_NAMESPACE}.servicebus.windows.net"
    logger.info("Connecting to Service Bus namespace: %s", fully_qualified_namespace)
    logger.info("Queue name: %s", QUEUE_NAME)
    logger.info("Processing delay: %d seconds", PROCESSING_DELAY_SECONDS)

    try:
        credential = DefaultAzureCredential()

        with ServiceBusClient(
            fully_qualified_namespace=fully_qualified_namespace,
            credential=credential,
        ) as client:
            with client.get_queue_receiver(
                queue_name=QUEUE_NAME,
                receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
            ) as receiver:
                logger.info("Connected to queue, waiting for messages...")
                processor_healthy = True

                while not shutdown_requested:
                    # Receive messages with a timeout to allow checking shutdown flag
                    messages = receiver.receive_messages(max_message_count=1, max_wait_time=5)

                    for message in messages:
                        try:
                            message_body = str(message)
                            process_message(message_body)
                            receiver.complete_message(message)
                        except Exception as exc:
                            logger.error("Error processing message: %s", exc)
                            # Message will be abandoned and retried
                            receiver.abandon_message(message)

                logger.info("Shutdown complete, processed %d messages", messages_processed)

    except Exception as exc:
        logger.error("Fatal error in queue processor: %s", exc)
        processor_healthy = False
        raise


def main():
    """Application entry point."""
    logger.info("Starting Service Bus Queue Processor")
    logger.info("SERVICE_BUS_NAMESPACE=%s", SERVICE_BUS_NAMESPACE)
    logger.info("QUEUE_NAME=%s", QUEUE_NAME)
    logger.info("PROCESSING_DELAY_SECONDS=%d", PROCESSING_DELAY_SECONDS)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Start health server in background thread
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # Run the main queue processor
    run_queue_processor()


if __name__ == "__main__":
    main()
