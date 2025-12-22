# FAVE Architecture Notes

## 1. Baseline VideoSearcher Pipeline
References: `VideoSearcherPaper.pdf` (OSCAR-P study) and the scripts under `VideoSearcher-src/`.

| Stage | Source Folder | Purpose | Inputs | Outputs |
|-------|---------------|---------|--------|---------|
| `ffmpeg-0` | `VideoSearcher-src/ffmpeg-0` | Split raw video into audio + video, package as `.tar.gz`. | Original video file. | Archive containing `video.mp4` and `audio.wav`. |
| `librosa` | `VideoSearcher-src/librosa` | Analyze audio for speech segments, emit timestamps, re-pack with video. | Archive from `ffmpeg-0`. | Archive with `video.mp4` + `timestamps.txt`. |
| `ffmpeg-1` | `VideoSearcher-src/ffmpeg-1` | Use timestamps to cut individual audio/video clips. | Archive with timestamps/video. | Multiple clip files (`clip_i.mp4`). |
| `ffmpeg-2` | `VideoSearcher-src/ffmpeg-2` | Transcode clips into compressed video + 16 kHz audio, archive. | Raw clip (`clip.mp4`). | Archive with `clip.wav` and `clip.mp4`. |
| `deepspeech` | `VideoSearcher-src/deepspeech` | Generate transcript for a clip, package transcript with video. | Archive from `ffmpeg-2`. | Archive with `transcript.txt` + `video.mp4`. |
| `ffmpeg-3` | `VideoSearcher-src/ffmpeg-3` | Sample frames (12 FPS) from a video segment. | Archive containing compressed video. | JPEG frames for downstream CV workloads. |
| `object-detector` | `VideoSearcher-src/object-detector` | Run YOLOv4 ONNX on a frame to annotate objects. | Individual frame. | Annotated frame + metadata (bounding boxes). |

Today these scripts are orchestrated manually or via OSCAR-P. We will reorganize them into serverless stages coordinated by an orchestrator.

## 2. Target FAVE Architecture
1. **Shared Object Store (Claim-Check Pattern)**  
   - Use MinIO/S3 bucket `fave-artifacts` (configurable) reachable from all OpenFaaS functions.  
   - Every payload between functions is a small JSON descriptor pointing to URIs inside the bucket, never raw binary data.
2. **Functions**  
   - `orchestrator`: accepts a request (`video_uri`, `query`), writes orchestration record, triggers downstream stages sequentially (or fan-out), monitors completion, aggregates output summary. Implementation lives in `functions/orchestrator/` and currently supports a dry-run mode until all stages are ready.  
   - Processing stages (`stage-ffmpeg-0`, `stage-librosa`, `stage-ffmpeg-1`, `stage-ffmpeg-2`, `stage-deepspeech`, `stage-ffmpeg-3`, `stage-object-detector`). Each stage:  
     - Downloads required artifacts to `/tmp`.  
     - Executes its transformation (ffmpeg/librosa/deepspeech/ONNX).  
     - Uploads results to `fave-artifacts/requests/{request_id}/{stage}/`.  
     - Returns metadata JSON: `{request_id, stage, output_uri, metrics}`.
     - `stage-ffmpeg-0` has been ported under `functions/stage-ffmpeg-0/`, following the original script’s logic to extract audio with ffmpeg, package it with a video copy, and upload `media.tar.gz`.  
     - `stage-librosa` has been implemented under `functions/stage-librosa/`, replicating the timestamp extraction logic to produce `segments.tar.gz` containing `timestamps.txt` + `video.mp4`.
3. **Data Flow**  
   ```
   Client -> orchestrator -> stage-ffmpeg-0 -> stage-librosa -> stage-ffmpeg-1 -> 
   [for each clip] stage-ffmpeg-2 -> stage-deepspeech -> stage-ffmpeg-3 -> stage-object-detector
   ```
   - The orchestrator keeps a per-request state file: `requests/{id}/state.json`.
   - For fan-out sections (per clip), orchestrator spawns asynchronous invocations and aggregates results when all child stages complete.
4. **Configuration Profiles**  
   - Each function declares `fprocess=python3 handler.py`, `memory_limit` (256–1024 MB), and environment variables:  
     - `ARTIFACT_BUCKET`: bucket name.  
     - `ARTIFACT_REGION` / `ENDPOINT`: S3 endpoint URL (MinIO).  
     - `STAGE_TIMEOUT_SECONDS`: max runtime for the stage (used by orchestrator).

## 3. Storage & Payload Conventions
- Bucket root: `s3://fave-artifacts/`
  ```
  requests/
    {request_id}/
      input/
        original.mp4
      stage-ffmpeg-0/
        media.tar.gz
      stage-librosa/
        segments.tar.gz
      stage-ffmpeg-1/
        clip_{i}.mp4
      stage-ffmpeg-2/
        clip_{i}.tar.gz
      stage-deepspeech/
        clip_{i}.tar.gz
      stage-ffmpeg-3/
        frame_{i}_{j}.jpg
      stage-object-detector/
        frame_{i}_{j}.json
      metadata/
        state.json
        logs/
          {stage}-{timestamp}.jsonl
  ```
- Message schema (shared JSON envelope):
  ```json
  {
    "request_id": "uuid",
    "stage": "stage-ffmpeg-0",
    "input_uri": "s3://fave-artifacts/requests/.../input/original.mp4",
    "config": {
      "threshold_db": 30,
      "frame_rate": 12
    },
    "fanout": {
      "clip_index": 2
    }
  }
  ```
- Stage response schema:
  ```json
  {
    "request_id": "uuid",
    "stage": "stage-ffmpeg-0",
    "output": [
      {"type": "archive", "uri": "s3://.../stage-ffmpeg-0/media.tar.gz"}
    ],
    "metrics": {
      "duration_ms": 5230,
      "memory_limit_mb": 512,
      "cold_start": false
    }
  }
  ```

## 4. Function Responsibilities & Dependencies
| Function | Dependencies | Notes |
|----------|--------------|-------|
| `stage-ffmpeg-0` | ffmpeg, boto3/minio client | Handles initial split. |
| `stage-librosa` | librosa, numpy, ffmpeg | Requires CPU-friendly container, may need `librosa` model weights. |
| `stage-ffmpeg-1` | ffmpeg | Loops through timestamps file to generate clip files. |
| `stage-ffmpeg-2` | ffmpeg | Compress audio/video and package. |
| `stage-deepspeech` | Mozilla DeepSpeech binaries, language model | Might be substituted with hosted API or synthetic CPU if runtime is too heavy. |
| `stage-ffmpeg-3` | ffmpeg | Frame sampling; may be parallelized per clip. |
| `stage-object-detector` | onnxruntime, numpy, OpenCV | For now uses YOLOv4 ONNX; we can placeholder with CPU-friendly detector. |
| `orchestrator` | Python (requests/httpx), boto3/minio | Maintains state machine, triggers functions via OpenFaaS gateway. |

## 5. Telemetry & Cost Proxy
- Each function writes structured logs (JSON lines) to `stdout` and optionally uploads them to `metadata/logs/`.
- Log fields: `timestamp`, `request_id`, `stage`, `event` (`start`, `end`, `error`), `duration_ms`, `memory_limit_mb`, `cold_start`, `config_profile`.
- Cost proxy computed post-hoc: `cost_unit = (duration_ms / 1000) * (memory_limit_mb / 1024)`.
- Orchestrator aggregates per-request metrics into `state.json` for quick inspection.

## 6. Next Steps
1. Finalize storage endpoint (likely MinIO) credentials and update `.env` templates.
2. Create base Docker image with ffmpeg, librosa, boto3/minio, and logging helper.
3. Implement orchestrator skeleton referencing the schemas above.
4. Build individual stage functions incrementally, validating with sample media from `VideoSearcher-src/`.
