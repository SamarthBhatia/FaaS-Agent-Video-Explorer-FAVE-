from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import librosa
import numpy as np

from logging_helper import log_event, log_exception
from metrics_helper import compute_cost_unit, get_memory_limit_mb, stage_timer
from schemas import ArtifactRef, StagePayload, StageResult
from storage_helper import download_file, upload_file

STAGE_NAME = "stage-librosa"
COLD_START = True


class StageLibrosaService:
    """Audio segmentation stage using librosa to produce timestamps."""

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
            archive_path = tmp_path / "input.tar.gz"
            download_file(payload.input_uri, archive_path)

            self._run_tar(["-xzf", str(archive_path)], cwd=tmp_path)
            audio_path = tmp_path / "audio.wav"
            video_path = tmp_path / "video.mp4"

            audio, _ = librosa.load(audio_path, sr=22050, mono=True)
            duration = librosa.get_duration(audio)

            min_len = 6
            max_len = 30
            min_clips = max(1, duration / max_len)
            max_clips = max(1, duration / min_len)

            clips = []
            for threshold_db in range(24, 50):
                clips = librosa.effects.split(audio, top_db=threshold_db)
                if min_clips <= len(clips) <= max_clips:
                    break

            timestamps_path = tmp_path / "timestamps.txt"
            with timestamps_path.open("w") as fp:
                last_end = 0
                last_ts = "00:00:00"
                for start, end in clips:
                    start_sec = last_end
                    start_ts = last_ts
                    end_ts, end_sec = self._samples_to_timestamp(end, False)
                    clip_len = end_sec - start_sec
                    if clip_len > min_len:
                        fp.write(f"{start_ts} {end_ts}\n")
                        last_end = end_sec
                        last_ts = end_ts

            package_path = tmp_path / "segments.tar.gz"
            self._run_tar(["-czf", str(package_path), "timestamps.txt", "video.mp4"], cwd=tmp_path)

            output_uri = (
                f"s3://{self.bucket}/requests/{payload.request_id}/{payload.stage}/segments.tar.gz"
            )
            upload_file(package_path, output_uri, extra_args={"ContentType": "application/gzip"})
            log_event(STAGE_NAME, "completed", request_id=payload.request_id, output_uri=output_uri)
            return output_uri

    @staticmethod
    def _samples_to_timestamp(sample: int, is_start: bool) -> tuple[str, int]:
        seconds = sample / 22050
        seconds = int(np.floor(seconds) if is_start else np.ceil(seconds))
        hh = seconds // 3600
        mm = (seconds % 3600) // 60
        ss = seconds % 60
        return f"{hh:02d}:{mm:02d}:{ss:02d}", seconds

    def _run_tar(self, args, cwd: Path):
        cmd = ["tar"] + args
        subprocess.run(cmd, check=True, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _is_cold_start(self) -> bool:
        global COLD_START  # pylint: disable=global-statement
        if COLD_START:
            COLD_START = False
            return True
        return False
