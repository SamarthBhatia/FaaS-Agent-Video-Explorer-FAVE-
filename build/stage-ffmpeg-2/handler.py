import json

from stage_ffmpeg2_service import StageFFmpeg2Service

service = StageFFmpeg2Service()


def handle(event, context):  # type: ignore[override]
    body = event.body.decode() if isinstance(event.body, (bytes, bytearray)) else event.body
    result = service.handle(body or "{}")
    return json.dumps(result)
