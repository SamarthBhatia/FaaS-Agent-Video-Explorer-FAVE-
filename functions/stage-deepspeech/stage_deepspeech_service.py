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

STAGE_NAME = "stage-deepspeech"
COLD_START = True


class StageDeepSpeechService:
    """Runs Mozilla DeepSpeech on the provided clip archive."""

    def __init__(self) -> None:
        self.bucket = os.getenv("ARTIFACT_BUCKET", "fave-artifacts")
        self.model_path = os.getenv("DEEPSPEECH_MODEL", "/opt/models/deepspeech-0.9.3-models.pbmm")
        self.scorer_path = os.getenv("DEEPSPEECH_SCORER", "/opt/models/deepspeech-0.9.3-models.scorer")
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
            archive_path = tmp_path / "clip_bundle.tar.gz"
            download_file(payload.input_uri, archive_path)

            self._run_tar(["-xzf", str(archive_path)], cwd=tmp_path)

            audio_path = tmp_path / "clip.wav"
            video_path = tmp_path / "clip_compressed.mp4"
            transcript_path = tmp_path / "transcript.txt"

            self._run_deepspeech(audio_path, transcript_path)

            output_archive = tmp_path / "transcript_bundle.tar.gz"
            self._run_tar(
                ["-czf", str(output_archive), transcript_path.name, video_path.name],
                cwd=tmp_path,
            )

            clip_name = Path(payload.input_uri).stem
            output_uri = (
                f"s3://{self.bucket}/requests/{payload.request_id}/{payload.stage}/{clip_name}.tar.gz"
            )
            upload_file(output_archive, output_uri, extra_args={"ContentType": "application/gzip"})
            log_event(STAGE_NAME, "completed", request_id=payload.request_id, output_uri=output_uri)
            return output_uri

    def _run_deepspeech(self, audio_path: Path, transcript_path: Path) -> None:
        try:
            import deepspeech
            import numpy as np
            import wave

            ds = deepspeech.Model(self.model_path)
            ds.enableExternalScorer(self.scorer_path)

            with wave.open(str(audio_path), "rb") as wf:
                if wf.getframerate() != 16000 or wf.getnchannels() != 1:
                    raise ValueError("Audio must be 16kHz mono before deepspeech stage")
                frames = wf.getnframes()
                buffer = wf.readframes(frames)
                audio = np.frombuffer(buffer, dtype=np.int16)

            text = ds.stt(audio)
            transcript_path.write_text(text.strip() + "\n")
            
        except ImportError:
            log_event(STAGE_NAME, "warning", message="DeepSpeech module not found, using dummy transcript")
            transcript_path.write_text("Dummy transcript: DeepSpeech library not available.\n")

    @staticmethod
    def _run_tar(args, cwd: Path):
        subprocess.run(["tar"] + args, check=True, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _is_cold_start(self) -> bool:
        global COLD_START  # pylint: disable=global-statement
        if COLD_START:
            COLD_START = False
            return True
        return False
