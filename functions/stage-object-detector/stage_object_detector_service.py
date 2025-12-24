from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import cv2
import numpy as np
import onnxruntime as ort

from logging_helper import log_event, log_exception
from metrics_helper import compute_cost_unit, get_memory_limit_mb, stage_timer
from schemas import ArtifactRef, StagePayload, StageResult
from storage_helper import download_file, upload_file, write_json

STAGE_NAME = "stage-object-detector"
COLD_START = True


class StageObjectDetectorService:
    """
    Runs Object Detection (Tiny YOLOv4) on the input frame.
    """

    def __init__(self) -> None:
        self.bucket = os.getenv("ARTIFACT_BUCKET", "fave-artifacts")
        self.model_path = os.getenv("MODEL_PATH", "/opt/models/model.onnx")
        self.label_path = os.getenv("LABEL_PATH", "/opt/models/coco.names")
        self.memory_limit_mb = get_memory_limit_mb()
        
        # Load labels
        self.labels = []
        if os.path.exists(self.label_path):
            with open(self.label_path, "r") as f:
                self.labels = [line.strip() for line in f.readlines()]

        # Initialize session (lazy loading could be an option, but we do it here for cold start measurement)
        try:
            self.sess = ort.InferenceSession(self.model_path)
            self.input_name = self.sess.get_inputs()[0].name
        except Exception as e:
            log_exception(STAGE_NAME, "init_model", e)
            self.sess = None

    def handle(self, raw_body: str) -> dict:
        try:
            payload = StagePayload.model_validate_json(raw_body)
        except Exception as exc:
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
        
        # We output a reference to the JSON result
        outputs = [ArtifactRef(type="json", uri=output_uri, metadata={})]
        
        result = StageResult(
            request_id=payload.request_id,
            stage=payload.stage,
            outputs=outputs,
            metrics=metrics,
            status="success",
        )
        return json.loads(result.model_dump_json())

    def _process(self, payload: StagePayload) -> str:
        log_event(STAGE_NAME, "start", request_id=payload.request_id, input_uri=payload.input_uri)
        
        if not self.sess:
             raise RuntimeError("Model not initialized")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            image_path = tmp_path / "input.jpg"
            download_file(payload.input_uri, image_path)

            # Preprocess
            img = cv2.imread(str(image_path))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = cv2.resize(img, (416, 416))
            img = img.astype(np.float32) / 255.0
            img = img.transpose(2, 0, 1)
            img = np.expand_dims(img, axis=0)

            # Inference
            detections = self.sess.run(None, {self.input_name: img})

            # Postprocess (Simplified: just count detections > threshold)
            # Tiny YOLO output depends on version, usually [boxes, scores, indices] or similar
            # For this 'tiny-yolov4-11.onnx', outputs are 'boxes' and 'confs'.
            # We will just dump the raw shape or a summary for now to avoid complex parsing logic in this snippet.
            
            summary = {
                "model": "tiny-yolov4",
                "raw_output_shapes": [str(d.shape) for d in detections],
                "note": "Full post-processing skipped for prototype"
            }

            output_uri = f"s3://{self.bucket}/requests/{payload.request_id}/{payload.stage}/result.json"
            write_json(summary, output_uri)
            
            log_event(STAGE_NAME, "completed", request_id=payload.request_id, output_uri=output_uri)
            return output_uri

    def _is_cold_start(self) -> bool:
        global COLD_START
        if COLD_START:
            COLD_START = False
            return True
        return False
