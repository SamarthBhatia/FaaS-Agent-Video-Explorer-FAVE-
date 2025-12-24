from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

from logging_helper import log_event, log_exception
from metrics_helper import compute_cost_unit, get_memory_limit_mb, stage_timer
from schemas import ArtifactRef, StagePayload, StageResult
from storage_helper import download_file, upload_file

STAGE_NAME = "stage-ffmpeg-0"
COLD_START = True


class StageFFmpeg0Service:
    """Implements the ffmpeg-0 stage (audio extraction + media archive packaging)."""

    def __init__(self) -> None:
        self.bucket = os.getenv("ARTIFACT_BUCKET", "fave-artifacts")
        self.memory_limit_mb = get_memory_limit_mb()

    def handle(self, raw_body: str) -> Dict[str, Any]:
        try:
            payload = StagePayload.model_validate_json(raw_body)
        except Exception as exc:  # pylint: disable=broad-except
            log_exception(STAGE_NAME, None, exc)
            return {"status": "error", "message": str(exc)}

        with stage_timer() as elapsed:
            result_uri = self._process(payload)

        duration_ms = elapsed()
        metrics = {
            "duration_ms": duration_ms,
            "memory_limit_mb": self.memory_limit_mb,
            "cold_start": self._is_cold_start(),
            "cost_unit": compute_cost_unit(duration_ms, self.memory_limit_mb),
        }
        log_event(STAGE_NAME, "metrics", request_id=payload.request_id, **metrics)
        outputs = [ArtifactRef(type="archive", uri=result_uri, metadata={})]
        stage_result = StageResult(
            request_id=payload.request_id,
            stage=payload.stage,
            outputs=outputs,
            metrics=metrics,
            status="success",
        )
        return json.loads(stage_result.model_dump_json())

    def _process(self, payload: StagePayload) -> str:
        """Download the video, split audio, package artifacts, and upload the archive."""
        log_event(STAGE_NAME, "start", request_id=payload.request_id, input_uri=payload.input_uri)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            video_path = tmp_path / "input_video"
            download_file(payload.input_uri, video_path)

            audio_path = tmp_path / "audio.wav"
            video_copy = tmp_path / "video.mp4"
            shutil.copy(video_path, video_copy)

            self._run_ffmpeg(["-i", str(video_path), "-map", "0:a", str(audio_path)])

            archive_path = tmp_path / "media.tar.gz"
            self._run_tar(archive_path, ["video.mp4", "audio.wav"], cwd=tmp_path)

            output_uri = (
                f"s3://{self.bucket}/requests/{payload.request_id}/{payload.stage}/media.tar.gz"
            )
            upload_file(archive_path, output_uri, extra_args={"ContentType": "application/gzip"})
            log_event(STAGE_NAME, "completed", request_id=payload.request_id, output_uri=output_uri)
            return output_uri

    def _run_ffmpeg(self, args):
        cmd = ["ffmpeg", "-y"] + args
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _run_tar(self, archive_path: Path, members, cwd: Path):
        cmd = ["tar", "-czf", str(archive_path)] + members
        subprocess.run(cmd, check=True, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _is_cold_start(self) -> bool:
        global COLD_START  # pylint: disable=global-statement
        if COLD_START:
            COLD_START = False
            return True
        return False
