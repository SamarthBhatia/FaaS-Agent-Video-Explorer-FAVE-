import json

from stage_ffmpeg0_service import StageFFmpeg0Service

service = StageFFmpeg0Service()


def handle(event, context):  # type: ignore[override]
    body = event.body.decode() if isinstance(event.body, (bytes, bytearray)) else event.body
    result = service.handle(body or "{}")
    return json.dumps(result)
