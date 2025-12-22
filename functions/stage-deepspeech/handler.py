import json

from stage_deepspeech_service import StageDeepSpeechService

service = StageDeepSpeechService()


def handle(event, context):  # type: ignore[override]
    body = event.body.decode() if isinstance(event.body, (bytes, bytearray)) else event.body
    result = service.handle(body or "{}")
    return json.dumps(result)
