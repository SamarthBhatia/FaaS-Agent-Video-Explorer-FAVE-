import json

from stage_ffmpeg3_service import StageFFmpeg3Service

service = StageFFmpeg3Service()


def handle(event, context):  # type: ignore[override]
    body = event.body.decode() if isinstance(event.body, (bytes, bytearray)) else event.body
    result = service.handle(body or "{}")
    return json.dumps(result)
