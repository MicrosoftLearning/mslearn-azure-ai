import os

from azure.identity import DefaultAzureCredential
from azure.messaging.webpubsubservice import WebPubSubServiceClient

from operation_store import Operation

PERSONAS = {
    "oncall": "On-call developer",
    "database": "Database specialist",
    "outsider": "Unauthorized observer",
}


def get_client(credential: DefaultAzureCredential) -> WebPubSubServiceClient:
    return WebPubSubServiceClient(
        endpoint=os.environ["WEBPUBSUB_ENDPOINT"],
        hub=os.environ["WEBPUBSUB_HUB"],
        credential=credential,
    )


def group_name(operation_id: str) -> str:
    return f"investigation-{operation_id}"


# BEGIN AUTHORIZE OPERATION ACCESS
def authorize(operation: Operation, persona: str, *, start: bool = False) -> None:
    if persona not in operation.allowed or (start and persona != operation.owner):
        raise PermissionError("This demo persona cannot access this investigation.")
# END AUTHORIZE OPERATION ACCESS


# BEGIN GENERATE CONNECTION DETAILS
def connection_details(
    client: WebPubSubServiceClient, operation: Operation, persona: str,
) -> dict[str, str]:
    authorize(operation, persona)
    group = group_name(operation.operation_id)
    token = client.get_client_access_token(
        user_id=persona,
        roles=[f"webpubsub.joinLeaveGroup.{group}"],
        minutes_to_expire=5,
    )
    return {"url": token["url"], "group": group}
# END GENERATE CONNECTION DETAILS
