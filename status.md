# Project Status

## Summary
- **Date**: 2025-12-24
- **Current Phase**: Experiments (In Progress)
- **Upcoming Phase**: Analysis & Reporting

## Completed Tasks
- [x] Locate/import VideoSearcher baseline assets.
- [x] Stand up shared storage (MinIO) + verify access credentials.
- [x] Create base Docker image with shared dependencies (Python 3.9, ffmpeg, helpers).
- [x] Implement orchestrator and all pipeline stages (ffmpeg-0, librosa, ffmpeg-1, ffmpeg-2, deepspeech*, ffmpeg-3, object-detector).
- [x] Verify build of all function images.
- [x] Fix cross-architecture build issues (ARM64 support for base image, placeholder for DeepSpeech).
- [x] Add cost proxy logging, structured telemetry, and state tracking across all functions.
- [x] Develop workload generator script (`scripts/workload_generator.py`).
- [x] Script deployment regimes (`scripts/deploy_regime.sh`).
- [x] **Unblock Environment**: Setup OpenFaaS on Kubernetes (Docker Desktop) and bypass "Community Edition" image restrictions using manual manifests and local image tagging.
- [x] **Fix Function Runtime**: Implemented an HTTP server wrapper (`index.py`) for all functions to handle chunked encoding and missing headers properly.
- [x] **Smoke Test (E2E)**: Successfully ran a dry-run orchestrator request confirming full connectivity between Gateway, Orchestrator, and MinIO.

## Notes
- `stage-deepspeech` uses a dummy implementation if the `deepspeech` library is missing (due to no ARM64 wheels).
- `stage-object-detector` uses real TinyYOLOv4 model downloaded from HuggingFace during build.
- Deployment regimes (cold, warm, burst-ready) are managed via manual manifests in `openfaas-fn` namespace.
- Bypassed OpenFaaS CE registry restriction by creating standard K8s Deployments/Services manually.

## Next Steps
1. **Experiments**:
   - Use `scripts/deploy_regime.sh` (adapted for manual manifests if needed) to apply cold/warm/burst-ready regimes.
   - Run steady/burst workloads via `scripts/workload_generator.py` and archive results under `experiments/`.
2. **Analysis & Reporting**:
   - Aggregate run data (latency percentiles, cold-start frequency, cost proxy).
   - Produce plots/tables answering RQ2/RQ3 and draft the report.