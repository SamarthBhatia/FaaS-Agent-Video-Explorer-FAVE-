# Orchestrator Design

## Responsibilities
1. Accept incoming requests (`video_uri`, `query`, optional config profile).
2. Generate `request_id`, create initial state file in storage, and enqueue first stage.
3. Invoke downstream OpenFaaS functions sequentially or via fan-out while tracking dependencies.
4. Persist per-stage progress, metrics, and errors to `metadata/state.json`.
5. Return aggregated result (e.g., list of clip transcripts, detected objects) to caller.

## Invocation Flow
1. Client calls `orchestrator` OpenFaaS function with payload:
   ```json
   {
     "video_uri": "s3://input-bucket/sample.mp4",
     "query": "find scenes with cars",
     "profile": "cold"
   }
   ```
2. Orchestrator (`functions/orchestrator/`):
   - Downloads or copies source video into `fave-artifacts/requests/{id}/input/`.
   - Writes `state.json` with status `INIT`.
   - Invokes the real stages in order: linear stages (`stage-ffmpeg-0`, `stage-librosa`), fan-out stage (`stage-ffmpeg-1`), then per-clip pipelines (`stage-ffmpeg-2` → `stage-deepspeech` → `stage-ffmpeg-3`). Object detection is currently an optional stub controlled via the `ENABLE_OBJECT_DETECTOR` flag.
3. Each synchronous stage returns output URIs; orchestrator updates state and triggers the next stage with the correct artifact reference.
4. For clip-based parallelism:
   - After `stage-ffmpeg-1`, iterate over the returned clip URIs (no async fan-out yet; clips are processed sequentially to simplify debugging).
   - Include `fanout.clip_index` metadata in every payload so downstream logs are traceable.
   - Until YOLO/ONNX is implemented, the orchestrator records a “skipped” object-detection stage so manifests stay consistent.
5. Final output (per-stage summaries + per-clip manifests) is stored under `metadata/state.json` and returned in the HTTP response.

## Implementation Notes
- Use `httpx` or `requests` to call OpenFaaS gateway: `POST http://gateway/function/{function_name}` with JSON payload.
- All payloads/returns conform to schemas defined in `common/schemas.py`.
- Orchestrator should be idempotent where possible: check `state.json` on startup to resume interrupted workflows.
- Logging: use `logging_helper.log_event(stage="orchestrator", event="invoke", details=...)`.
- Error handling: if a stage fails, mark request status `FAILED`, log stack trace, and optionally retry according to policy.

## Configuration
- Environment variables:
  - `GATEWAY_URL` (e.g., `http://gateway.openfaas:8080`).
  - Storage credentials (same as other functions).
  - `ORCHESTRATOR_DRY_RUN` (defaults to `false` now that real stages exist).
  - `ENABLE_OBJECT_DETECTOR` (defaults to `false`; flip to `true` once the YOLO/ONNX stage is ready).
- Timeout management: orchestrator enforces per-stage max duration via config; if exceeded, it aborts the workflow and records failure.

## Pseudocode Outline
```
def handle(req):
    payload = parse(req)
    request_id = uuid4()
    persist_state(request_id, status="INIT")
    input_uri = ensure_input(payload["video_uri"], request_id)
    context = {"request_id": request_id, "profile": payload.get("profile", "default")}

    # Linear stages
    stage_out = invoke_stage("stage-ffmpeg-0", input_uri, context)
    stage_out = invoke_stage("stage-librosa", stage_out, context)
    clips = invoke_stage("stage-ffmpeg-1", stage_out, context)["clips"]

    # Fan-out for each clip
    futures = []
    for clip in clips:
        futures.append(invoke_stage_async("stage-ffmpeg-2", clip, context))
    wait_for_all(futures)

    # Continue with transcripts, frames, detection
    ...

    persist_state(request_id, status="COMPLETED", result=result)
    return result
```

## Next Steps
1. Implement `common/schemas.py` (request/response models).
2. Create orchestrator handler (`handler.py`) using base image and helper modules.
3. Add resume logic reading `state.json`.
4. Build and deploy orchestrator function first (`functions/orchestrator/`), relying on dry-run only when debugging. In the current repo, dry-run is disabled by default so the orchestrator exercises the implemented stages end-to-end.
