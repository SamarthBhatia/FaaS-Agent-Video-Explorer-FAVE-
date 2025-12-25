import json
from stage_object_detector_service import StageObjectDetectorService

service = StageObjectDetectorService()

def handle(event, context):
    body = event.body.decode() if isinstance(event.body, (bytes, bytearray)) else event.body
    result = service.handle(body or "{}")
    return json.dumps(result)
