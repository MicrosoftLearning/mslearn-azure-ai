#!/usr/bin/env python3
import argparse
import os
import sys
from typing import Iterable, List

from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage


def _chunks(items: List[ServiceBusMessage], size: int) -> Iterable[List[ServiceBusMessage]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def main() -> int:
    parser = argparse.ArgumentParser(description="Send test messages to an Azure Service Bus queue using Microsoft Entra ID.")
    parser.add_argument("--count", type=int, default=100, help="Number of messages to send (default: 100)")
    parser.add_argument("--prefix", type=str, default="Order", help="Message prefix (default: Order)")

    args = parser.parse_args()

    if args.count < 1:
        print("--count must be >= 1", file=sys.stderr)
        return 2

    service_bus_namespace = os.getenv("SERVICE_BUS_NAMESPACE", "").strip()
    service_bus_fqdn = os.getenv("SERVICE_BUS_FQDN", "").strip()
    queue_name = os.getenv("QUEUE_NAME", "orders").strip()

    fully_qualified_namespace = ""
    if service_bus_fqdn:
        fully_qualified_namespace = service_bus_fqdn
    elif service_bus_namespace:
        fully_qualified_namespace = f"{service_bus_namespace}.servicebus.windows.net"

    if not fully_qualified_namespace:
        print("Missing SERVICE_BUS_NAMESPACE (or SERVICE_BUS_FQDN) environment variable.", file=sys.stderr)
        return 2

    if not queue_name:
        print("Missing QUEUE_NAME environment variable.", file=sys.stderr)
        return 2

    credential = DefaultAzureCredential()

    messages = [ServiceBusMessage(f"{args.prefix} {i}") for i in range(1, args.count + 1)]

    try:
        with ServiceBusClient(fully_qualified_namespace=fully_qualified_namespace, credential=credential) as client:
            with client.get_queue_sender(queue_name=queue_name) as sender:
                # Send in batches to avoid hitting max message limits.
                for batch in _chunks(messages, 100):
                    sender.send_messages(batch)

        print(f"Sent {args.count} messages to queue '{queue_name}' in '{fully_qualified_namespace}'.")
        return 0
    except Exception as exc:
        print(f"Failed to send messages: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
