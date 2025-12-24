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
from schemas import ArtifactRef, OrchestratorRequest, StagePayload, StageResult, StageMetrics
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
        self.dry_run = os.getenv("ORCHESTRATOR_DRY_RUN", "false").lower() in {"1", "true", "yes"}
        self.enable_object_detector = os.getenv("ENABLE_OBJECT_DETECTOR", "false").lower() in {"1", "true", "yes"}
        self.linear_stages = [
            "stage-ffmpeg-0",
            "stage-librosa",
        ]
        self.clip_pipeline = [
            "stage-ffmpeg-2",
            "stage-deepspeech",
            "stage-ffmpeg-3",
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
            
            with stage_timer() as elapsed:
                result = self._run_pipeline(request_id, input_uri, req)
            
            duration_ms = elapsed()
            metrics = {
                "duration_ms": duration_ms,
                "memory_limit_mb": self.memory_limit_mb,
                "cold_start": False, # Orchestrator cold start is handled at container level
                "cost_unit": compute_cost_unit(duration_ms, self.memory_limit_mb),
            }
            log_event("orchestrator", "metrics", request_id=request_id, **metrics)
            
            update_state(request_id, status="COMPLETED", result=result, metrics=metrics)
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
        initial_results: List[Dict[str, Any]] = []
        for stage_name in self.linear_stages:
            result = self._execute_stage(stage_name, current_input, request_id, req.profile, {})
            initial_results.append(self._summarize_result(result))
            current_input = self._next_input_uri(result, current_input)

        ffmpeg1_result = self._execute_stage("stage-ffmpeg-1", current_input, request_id, req.profile, {})
        initial_results.append(self._summarize_result(ffmpeg1_result))
        clip_refs = ffmpeg1_result.outputs

        clip_results: List[Dict[str, Any]] = []
        for idx, clip_ref in enumerate(clip_refs):
            clip_uri = clip_ref.uri
            clip_stage_entries = []
            
            # 1. Clip Compression (ffmpeg-2)
            res_ffmpeg2 = self._execute_stage("stage-ffmpeg-2", clip_uri, request_id, req.profile, {"clip_index": idx})
            clip_stage_entries.append(self._summarize_result(res_ffmpeg2, extra={"clip_index": idx}))
            
            # 2. Transcription (deepspeech)
            uri_ds_in = self._next_input_uri(res_ffmpeg2, clip_uri)
            res_ds = self._execute_stage("stage-deepspeech", uri_ds_in, request_id, req.profile, {"clip_index": idx})
            clip_stage_entries.append(self._summarize_result(res_ds, extra={"clip_index": idx}))
            
            # 3. Frame Sampling (ffmpeg-3)
            uri_ff3_in = self._next_input_uri(res_ds, uri_ds_in)
            res_ff3 = self._execute_stage("stage-ffmpeg-3", uri_ff3_in, request_id, req.profile, {"clip_index": idx})
            clip_stage_entries.append(self._summarize_result(res_ff3, extra={"clip_index": idx}))
            
            # 4. Object Detection (per frame)
            frame_refs = res_ff3.outputs
            if self.enable_object_detector and frame_refs:
                for f_idx, frame_ref in enumerate(frame_refs):
                    # frame_ref.metadata might contain "frame_index"
                    frame_meta = frame_ref.metadata or {}
                    fanout_info = {"clip_index": idx, "frame_index": frame_meta.get("frame_index", f_idx)}
                    
                    od_result = self._execute_stage(
                        "stage-object-detector",
                        frame_ref.uri,
                        request_id,
                        req.profile,
                        fanout_info,
                    )
                    clip_stage_entries.append(self._summarize_result(od_result, extra=fanout_info))
            elif not self.enable_object_detector:
                od_result = self._object_detector_stub(request_id, idx)
                clip_stage_entries.append(self._summarize_result(od_result, extra={"clip_index": idx}))

            clip_results.append(
                {
                    "clip_index": idx,
                    "input_uri": clip_ref.uri,
                    "stages": clip_stage_entries,
                }
            )

        return {"linear": initial_results, "clips": clip_results}

    def _execute_stage(
        self,
        stage_name: str,
        input_uri: str,
        request_id: str,
        profile: str,
        fanout: Dict[str, Any],
    ) -> StageResult:
        payload = StagePayload(
            request_id=request_id,
            stage=stage_name,
            input_uri=input_uri,
            config={"profile": profile},
            fanout=fanout,
        )

        if self.dry_run:
            result = self._simulate_stage(payload)
        else:
            result = self._invoke_stage(stage_name, payload)

        append_stage_entry(
            request_id,
            {
                "stage": stage_name,
                "request_id": request_id,
                "fanout": fanout,
                "outputs": [output.model_dump() for output in result.outputs],
                "metrics": result.metrics.model_dump(),
                "status": result.status,
                "message": result.message,
            },
        )
        return result

    @staticmethod
    def _next_input_uri(result: StageResult, fallback: str) -> str:
        return result.outputs[-1].uri if result.outputs else fallback

    @staticmethod
    def _summarize_result(result: StageResult, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        summary = {
            "stage": result.stage,
            "status": result.status,
            "message": result.message,
            "outputs": [output.model_dump() for output in result.outputs],
            "metrics": result.metrics.model_dump(),
        }
        if extra:
            summary.update(extra)
        return summary

    def _object_detector_stub(self, request_id: str, clip_index: int) -> StageResult:
        metrics = StageMetrics(
            duration_ms=0,
            memory_limit_mb=self.memory_limit_mb,
            cold_start=False,
            cost_unit=0.0,
        )
        return StageResult(
            request_id=request_id,
            stage="stage-object-detector",
            outputs=[],
            metrics=metrics,
            status="skipped",
            message=f"Object detector disabled for clip {clip_index}",
        )

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
