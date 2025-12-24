from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from logging_helper import log_event, log_exception
from metrics_helper import compute_cost_unit, get_memory_limit_mb, stage_timer
from schemas import ArtifactRef, StagePayload, StageResult
from storage_helper import download_file, upload_file

STAGE_NAME = "stage-ffmpeg-2"
COLD_START = True


class StageFFmpeg2Service:
    """Compress clip, extract 16kHz mono audio, package both for downstream."""

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
            output_uri = self._process(payload)

        duration_ms = elapsed()
        metrics = {
            "duration_ms": duration_ms,
            "memory_limit_mb": self.memory_limit_mb,
            "cold_start": self._is_cold_start(),
            "cost_unit": compute_cost_unit(duration_ms, self.memory_limit_mb),
        }
        log_event(STAGE_NAME, "metrics", request_id=payload.request_id, **metrics)
        result = StageResult(
            request_id=payload.request_id,
            stage=payload.stage,
            outputs=[ArtifactRef(type="archive", uri=output_uri, metadata={})],
            metrics=metrics,
            status="success",
        )
        return json.loads(result.model_dump_json())

    def _process(self, payload: StagePayload) -> str:
        log_event(STAGE_NAME, "start", request_id=payload.request_id, input_uri=payload.input_uri)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            clip_path = tmp_path / "clip.mp4"
            download_file(payload.input_uri, clip_path)

            raw_audio = tmp_path / "tmp_raw.wav"
            audio_path = tmp_path / "clip.wav"
            compressed_video = tmp_path / "clip_compressed.mp4"
            archive_path = tmp_path / "clip_bundle.tar.gz"

            self._run_ffmpeg(["-i", str(clip_path), "-map", "0:a", str(raw_audio)])
            self._run_ffmpeg(["-i", str(raw_audio), "-vn", "-ar", "16000", "-ac", "1", str(audio_path)])
            self._run_ffmpeg(["-i", str(clip_path), "-vcodec", "libx264", "-crf", "30", str(compressed_video)])

            self._run_tar(
                ["-czf", str(archive_path), audio_path.name, compressed_video.name, clip_path.name],
                cwd=tmp_path,
            )

            clip_name = Path(payload.input_uri).stem
            output_uri = (
                f"s3://{self.bucket}/requests/{payload.request_id}/{payload.stage}/{clip_name}.tar.gz"
            )
            upload_file(archive_path, output_uri, extra_args={"ContentType": "application/gzip"})
            log_event(STAGE_NAME, "completed", request_id=payload.request_id, output_uri=output_uri)
            return output_uri

    @staticmethod
    def _run_ffmpeg(args):
        cmd = ["ffmpeg", "-y"] + args
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    @staticmethod
    def _run_tar(args, cwd: Path):
        cmd = ["tar"] + args
        subprocess.run(cmd, check=True, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _is_cold_start(self) -> bool:
        global COLD_START  # pylint: disable=global-statement
        if COLD_START:
            COLD_START = False
            return True
        return False
