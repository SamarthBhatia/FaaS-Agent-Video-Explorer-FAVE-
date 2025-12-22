# Base Image Plan

## Goals
- Provide a reproducible container base for all FAVE OpenFaaS functions.
- Include common dependencies (Python 3.11+, ffmpeg, librosa stack, boto3/minio client, OpenCV, onnxruntime, Mozilla DeepSpeech binaries).
- Bake in shared helper modules (logging, storage utilities) to reduce duplication.

## Image Layout
- **Base**: `python:3.11-slim` (or Debian-based) for smaller footprint.
- **Packages**:
  - System: `ffmpeg`, `libgl1`, `libglib2.0-0`, `libsndfile1`, `build-essential`, `wget`, `tar`.
  - Python libs (shared): `boto3`, `minio`, `numpy`, `librosa`, `soundfile`, `opencv-python-headless`, `onnxruntime`, `scipy`, `pydantic` (for schemas), `httpx`.
  - Optional: `deepspeech==0.9.3`, `webrtcvad`, `torch` (if placeholder LLM).
- **Shared modules** (placed in `/opt/fave_common`):
  - `storage.py`: wrapper around boto3/minio for upload/download/list.
  - `logging.py`: structured logging helper (`log_event(stage, event, **kwargs)`).
  - `metrics.py`: utilities for measuring runtime, memory limit retrieval.

## Build Steps
1. Base Dockerfile lives at `base-image/Dockerfile`:
   ```Dockerfile
   FROM python:3.11-slim
   ...
   COPY requirements.txt /tmp/requirements.txt
   RUN pip install --no-cache-dir -r /tmp/requirements.txt
   COPY common/ /opt/fave_common/
   ENV PYTHONPATH=/opt/fave_common:${PYTHONPATH}
   ```
2. Install dependencies via `base-image/requirements.txt`:
   ```
   boto3==1.35.0
   minio==7.2.15
   numpy==2.1.3
   librosa==0.10.2
   soundfile==0.12.1
   httpx==0.27.0
   opencv-python-headless==4.10.0
   onnxruntime==1.19.2
   scipy==1.11.4
   pydantic==2.8.0
   deepspeech==0.9.3
   ```
3. Shared helper modules in `base-image/common/`:
   - `storage_helper.py`
   - `logging_helper.py`
   - `metrics_helper.py`
   - `schemas.py` (pydantic models for payload/response)

## Publishing
- Build locally: `docker build -t fave-base:dev base-image/`.
- Push to registry accessible by OpenFaaS cluster.
- Note digest/tag in documentation for deterministic deployments.

## Usage in Functions
- Function Dockerfiles should `FROM ghcr.io/<user>/fave-base:0.1`.
- Each function only copies stage-specific code and requirements (if any) to minimize duplication.
- Example `handler.py` can import helper modules: `from storage_helper import download_to_tmp`.

## Next Steps
1. Create `base-image/` directory with Dockerfile, requirements, and helpers.
2. Implement helper modules as described.
3. Build + push initial image, document tag in deployment guide.
4. Validate by running a sample stage locally using the base image.
5. Update `functions/orchestrator/Dockerfile` (and future stage Dockerfiles) to reference the published base image tag via the `BASE_IMAGE` build argument.
