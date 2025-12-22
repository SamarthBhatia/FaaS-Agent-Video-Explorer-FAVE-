from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List

from logging_helper import log_event, log_exception
from metrics_helper import compute_cost_unit, get_memory_limit_mb, stage_timer
from schemas import ArtifactRef, StagePayload, StageResult
from storage_helper import download_file, upload_file

STAGE_NAME = "stage-ffmpeg-3"
COLD_START = True


class StageFFmpeg3Service:
    """Samples frames from the clip video and uploads them individually."""

    def __init__(self) -> None:
        self.bucket = os.getenv("ARTIFACT_BUCKET", "fave-artifacts")
        self.frame_filter = os.getenv("FRAME_VF", "fps=12/60")
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
            archive_path = tmp_path / "bundle.tar.gz"
            download_file(payload.input_uri, archive_path)

            self._run_tar(["-xzf", str(archive_path)], cwd=tmp_path)

            video_path = tmp_path / "clip_compressed.mp4"
            if not video_path.exists():
                # fallback if archive uses different name
                candidates = list(tmp_path.glob("*.mp4"))
                if not candidates:
                    raise FileNotFoundError("No mp4 video found in archive for frame sampling")
                video_path = candidates[0]

            frame_prefix = tmp_path / "frame"
            output_pattern = f"{frame_prefix}-%04d.jpg"
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-vf",
                self.frame_filter,
                output_pattern,
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            clip_name = Path(payload.input_uri).stem
            outputs: List[ArtifactRef] = []
            for frame_file in sorted(tmp_path.glob("frame-*.jpg")):
                frame_index = frame_file.stem.split("-")[-1]
                target_uri = (
                    f"s3://{self.bucket}/requests/{payload.request_id}/{payload.stage}/{clip_name}/frame_{frame_index}.jpg"
                )
                upload_file(frame_file, target_uri, extra_args={"ContentType": "image/jpeg"})
                outputs.append(
                    ArtifactRef(
                        type="image",
                        uri=target_uri,
                        metadata={"clip": clip_name, "frame_index": int(frame_index)},
                    )
                )

            log_event(STAGE_NAME, "completed", request_id=payload.request_id, frames=len(outputs))
            return outputs

    @staticmethod
    def _run_tar(args, cwd: Path):
        subprocess.run(["tar"] + args, check=True, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _is_cold_start(self) -> bool:
        global COLD_START  # pylint: disable=global-statement
        if COLD_START:
            COLD_START = False
            return True
        return False
