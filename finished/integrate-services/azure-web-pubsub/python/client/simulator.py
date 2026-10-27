import time
from collections.abc import Iterator

STAGES = (
    ("Inspecting application logs", (
        "Application logs show a rise in request latency. ",
        "Timeouts began after the latest deployment. ",
        "The API remains healthy but requests wait for database connections.\n",
    )),
    ("Inspecting database connections", (
        "Database CPU is normal. ",
        "The connection pool is exhausted. ",
        "Several request handlers retain idle connections. ",
        "A missing cleanup path explains the growing queue.\n",
    )),
    ("Preparing the investigation result", (
        "The likely cause is a connection leak in the new request handler. ",
        "Recommended next steps: review connection cleanup, ",
        "compare pool metrics before and after the deployment, ",
        "and validate a fix in a non-production environment.\n",
    )),
)

EXPECTED_TEXT = "".join(fragment for _, fragments in STAGES for fragment in fragments)
FRAGMENT_COUNT = sum(len(fragments) for _, fragments in STAGES)


def simulate(delay: float = 1.0) -> Iterator[tuple[str, str, int]]:
    emitted = 0
    for stage, fragments in STAGES:
        for fragment in fragments:
            time.sleep(delay)
            emitted += 1
            yield stage, fragment, emitted * 95 // FRAGMENT_COUNT
