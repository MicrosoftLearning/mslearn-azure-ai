import json
from copy import deepcopy
import threading
from types import SimpleNamespace

from azure.core.exceptions import AzureError, ResourceExistsError, ResourceModifiedError, ResourceNotFoundError


class MemoryContainer:
    """Test double for the Blob SDK, never used by the application."""

    def __init__(self):
        self.blobs = {}
        self.lock = threading.Lock()
        self.fail_writes = False

    def get_blob_client(self, name):
        container = self

        class Blob:
            def upload_blob(self, data, *, overwrite=False, etag=None, **options):
                with container.lock:
                    if container.fail_writes:
                        raise AzureError("Injected storage failure")
                    existing = container.blobs.get(name)
                    if etag is not None and (not existing or existing[1] != etag):
                        raise ResourceModifiedError("ETag mismatch")
                    if existing and not overwrite:
                        raise ResourceExistsError("Already exists")
                    version = int(existing[1]) + 1 if existing else 1
                    container.blobs[name] = (data.encode(), str(version))
                    return {"etag": str(version)}

            def download_blob(self):
                with container.lock:
                    if name not in container.blobs:
                        raise ResourceNotFoundError("Not found")
                    content, version = container.blobs[name]
                return SimpleNamespace(
                    readall=lambda: content, properties=SimpleNamespace(etag=version),
                )

        return Blob()

    def list_blobs(self, *, name_starts_with):
        return [SimpleNamespace(name=name) for name in list(self.blobs) if name.startswith(name_starts_with)]


class FakePubSub:
    def __init__(self):
        self.events = []
        self.token_requests = []
        self.fail_publish = False

    def get_client_access_token(self, **kwargs):
        self.token_requests.append(kwargs)
        return {"url": "wss://example.invalid/client/hubs/test?access_token=test-only"}

    def send_to_group(self, *, group, message, content_type):
        if self.fail_publish:
            raise AzureError("Injected publishing failure")
        self.events.append((group, json.loads(message) if isinstance(message, str) else deepcopy(message), content_type))
