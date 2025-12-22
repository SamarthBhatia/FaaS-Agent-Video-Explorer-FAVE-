import json

from orchestrator_service import OrchestratorService

service = OrchestratorService()


def handle(event, context):  # type: ignore[override]
    """
    OpenFaaS entrypoint.
    `event.body` contains the raw JSON payload from the client.
    """
    body = event.body.decode() if isinstance(event.body, (bytes, bytearray)) else event.body
    result = service.handle(body or "{}")
    return json.dumps(result)
