from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from logging_helper import log_event, log_exception
from metrics_helper import compute_cost_unit, get_memory_limit_mb, stage_timer
from schemas import ArtifactRef, OrchestratorRequest, StagePayload, StageResult
from state_helper import append_stage_entry, save_state, update_state
from storage_helper import copy_object, upload_file


class OrchestratorService:
    """
    Coordinates VideoSearcher pipeline stages.
    Currently supports a sequential pipeline definition with optional dry-run mode.
    """

    def __init__(self) -> None:
        self.gateway_url = os.getenv("GATEWAY_URL", "http://gateway.openfaas:8080")
        self.bucket = os.getenv("ARTIFACT_BUCKET", "fave-artifacts")
        self.dry_run = os.getenv("ORCHESTRATOR_DRY_RUN", "true").lower() in {"1", "true", "yes"}
        self.pipeline = [
            "stage-ffmpeg-0",
            "stage-librosa",
            "stage-ffmpeg-1",
            "stage-ffmpeg-2",
            "stage-deepspeech",
            "stage-ffmpeg-3",
            "stage-object-detector",
        ]
        self.memory_limit_mb = get_memory_limit_mb()

    def handle(self, raw_body: str) -> Dict[str, Any]:
        """Entry point invoked by handler."""
        try:
            req = OrchestratorRequest.model_validate_json(raw_body)
        except ValidationError as exc:
            log_event("orchestrator", "invalid_request", error=str(exc))
            return {"status": "error", "message": exc.errors()}

        request_id = str(uuid.uuid4())
        log_event("orchestrator", "accepted", request_id=request_id, profile=req.profile)

        state = {
            "request_id": request_id,
            "profile": req.profile,
            "status": "ACCEPTED",
            "stages": [],
        }
        save_state(request_id, state)

        try:
            input_uri = self._ensure_input_artifact(req.video_uri, request_id)
            update_state(request_id, input_uri=input_uri)
            result = self._run_pipeline(request_id, input_uri, req)
            return {"status": "ok", "request_id": request_id, "result": result}
        except Exception as exc:  # pylint: disable=broad-except
            log_exception("orchestrator", request_id, exc)
            update_state(request_id, status="FAILED", error=str(exc))
            return {"status": "error", "request_id": request_id, "message": str(exc)}

    def _ensure_input_artifact(self, source_uri: str, request_id: str) -> str:
        """
        Copy or upload the input video under the request namespace.
        Supports S3 URIs, HTTP URLs, or local filesystem paths.
        """
        parsed = urlparse(source_uri)
        suffix = Path(parsed.path).suffix or ".mp4"
        target_uri = f"s3://{self.bucket}/requests/{request_id}/input/original{suffix}"

        log_event("orchestrator", "import_input", request_id=request_id, source=source_uri, target=target_uri)

        if parsed.scheme in {"s3", "s3a", "s3n"}:
            copy_object(source_uri, target_uri)
            return target_uri

        if parsed.scheme in {"http", "https"}:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp_path = Path(tmp.name)
                with httpx.stream("GET", source_uri, timeout=None) as resp:
                    resp.raise_for_status()
                    for chunk in resp.iter_bytes():
                        tmp.write(chunk)
            try:
                upload_file(tmp_path, target_uri)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
            return target_uri

        local_path = Path(source_uri)
        if local_path.exists():
            upload_file(local_path, target_uri)
            return target_uri

        raise ValueError(f"Unsupported video_uri: {source_uri}")

    def _run_pipeline(self, request_id: str, input_uri: str, req: OrchestratorRequest) -> Dict[str, Any]:
        """
        Run the configured pipeline. If dry_run=True, synthesize stage outputs
        without invoking downstream functions.
        """
        current_input = input_uri
        stage_results: List[Dict[str, Any]] = []

        for stage_name in self.pipeline:
            payload = StagePayload(
                request_id=request_id,
                stage=stage_name,
                input_uri=current_input,
                config={"profile": req.profile},
            )

            if self.dry_run:
                result = self._simulate_stage(payload)
            else:
                result = self._invoke_stage(stage_name, payload)

            stage_entry = {
                "stage": stage_name,
                "outputs": [output.model_dump() for output in result.outputs],
                "metrics": result.metrics.model_dump(),
                "status": result.status,
            }
            append_stage_entry(request_id, stage_entry)
            stage_results.append(stage_entry)

            if result.outputs:
                current_input = result.outputs[-1].uri

        update_state(request_id, status="COMPLETED")
        return {"stages": stage_results}

    def _simulate_stage(self, payload: StagePayload) -> StageResult:
        """Generate a placeholder StageResult for environments without downstream functions."""
        with stage_timer() as elapsed:
            pass
        duration_ms = elapsed()
        metrics = {
            "duration_ms": duration_ms,
            "memory_limit_mb": self.memory_limit_mb,
            "cold_start": False,
            "cost_unit": compute_cost_unit(duration_ms, self.memory_limit_mb),
        }
        fake_output = ArtifactRef(
            type="reference",
            uri=f"s3://{self.bucket}/requests/{payload.request_id}/{payload.stage}/placeholder.txt",
            metadata={},
        )
        return StageResult(
            request_id=payload.request_id,
            stage=payload.stage,
            outputs=[fake_output],
            metrics=metrics,
            status="simulated",
            message="Stage simulation placeholder",
        )

    def _invoke_stage(self, stage_name: str, payload: StagePayload) -> StageResult:
        """Call the OpenFaaS function for a given stage and parse the response."""
        url = f"{self.gateway_url}/function/{stage_name}"
        with httpx.Client(timeout=None) as client:
            response = client.post(url, json=json.loads(payload.model_dump_json()))
            response.raise_for_status()
        return StageResult.model_validate_json(response.text)
