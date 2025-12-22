from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, List

from logging_helper import log_event, log_exception
from metrics_helper import compute_cost_unit, get_memory_limit_mb, stage_timer
from schemas import ArtifactRef, StagePayload, StageResult
from storage_helper import download_file, upload_file

STAGE_NAME = "stage-ffmpeg-1"
COLD_START = True


class StageFFmpeg1Service:
    """Splits the video into clips based on timestamps."""

    def __init__(self) -> None:
        self.bucket = os.getenv("ARTIFACT_BUCKET", "fave-artifacts")
        self.memory_limit_mb = get_memory_limit_mb()

    def handle(self, raw_body: str) -> dict:
        try:
            payload = StagePayload.model_validate_json(raw_body)
        except Exception as exc:  # pylint: disable=broad-except
            log_exception(STAGE_NAME, None, exc)
            return {"status": "error", "message": str(exc)}

        with stage_timer() as elapsed:
            outputs = self._process(payload)

        duration_ms = elapsed()
        metrics = {
            "duration_ms": duration_ms,
            "memory_limit_mb": self.memory_limit_mb,
            "cold_start": self._is_cold_start(),
            "cost_unit": compute_cost_unit(duration_ms, self.memory_limit_mb),
        }
        result = StageResult(
            request_id=payload.request_id,
            stage=payload.stage,
            outputs=outputs,
            metrics=metrics,
            status="success",
        )
        return json.loads(result.model_dump_json())

    def _process(self, payload: StagePayload) -> List[ArtifactRef]:
        log_event(STAGE_NAME, "start", request_id=payload.request_id, input_uri=payload.input_uri)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            archive_path = tmp_path / "segments.tar.gz"
            download_file(payload.input_uri, archive_path)
            self._run_tar(["-xzf", str(archive_path)], cwd=tmp_path)

            timestamps_path = tmp_path / "timestamps.txt"
            video_path = tmp_path / "video.mp4"

            with timestamps_path.open() as fp:
                lines = [line.strip() for line in fp if line.strip()]

            outputs: List[ArtifactRef] = []
            for idx, line in enumerate(lines):
                start_ts, end_ts = line.split()
                clip_name = f"clip_{idx:03d}.mp4"
                clip_path = tmp_path / clip_name
                cmd = ["ffmpeg", "-y", "-ss", start_ts, "-to", end_ts, "-i", str(video_path), "-c", "copy", str(clip_path)]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                uri = f"s3://{self.bucket}/requests/{payload.request_id}/{payload.stage}/{clip_name}"
                upload_file(clip_path, uri, extra_args={"ContentType": "video/mp4"})
                outputs.append(ArtifactRef(type="video", uri=uri, metadata={"clip_index": idx}))

            log_event(STAGE_NAME, "completed", request_id=payload.request_id, clips=len(outputs))
            return outputs

    def _run_tar(self, args, cwd: Path):
        cmd = ["tar"] + args
        subprocess.run(cmd, check=True, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _is_cold_start(self) -> bool:
        global COLD_START  # pylint: disable=global-statement
        if COLD_START:
            COLD_START = False
            return True
        return False
