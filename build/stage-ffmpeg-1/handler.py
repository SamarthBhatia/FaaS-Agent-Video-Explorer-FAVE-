import json

from stage_ffmpeg1_service import StageFFmpeg1Service

service = StageFFmpeg1Service()


def handle(event, context):  # type: ignore[override]
    body = event.body.decode() if isinstance(event.body, (bytes, bytearray)) else event.body
    result = service.handle(body or "{}")
    return json.dumps(result)
