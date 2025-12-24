# Project Status

## Summary
- **Date**: 2025-12-24
- **Current Phase**: Instrumentation & Workloads (Completed), Experiments (Blocked)
- **Upcoming Phase**: Experiments (Resumption)

## Completed Tasks
- [x] Locate/import VideoSearcher baseline assets.
- [x] Stand up shared storage (MinIO) + verify access credentials.
- [x] Create base Docker image with shared dependencies (Python 3.9, ffmpeg, helpers).
- [x] Implement orchestrator and all pipeline stages (ffmpeg-0, librosa, ffmpeg-1, ffmpeg-2, deepspeech*, ffmpeg-3, object-detector).
- [x] Verify build of all function images.
- [x] Fix cross-architecture build issues (ARM64 support for base image, placeholder for DeepSpeech).
- [x] Add cost proxy logging and metrics to all functions.
- [x] Develop workload generator script (`scripts/workload_generator.py`).
- [x] Script deployment regimes (`scripts/deploy_regime.sh`).
- [x] Add per-stage telemetry/cost logging and structured state tracking.
- [x] Create and pass local smoke tests for `stage-ffmpeg-3` and `stage-object-detector` logic (`tests/smoke_test_stages.py`).
- [x] Attempt to bootstrap OpenFaaS on Docker Swarm (failed due to `faas-swarm` compatibility).

## Notes
- `stage-deepspeech` uses a dummy implementation if the `deepspeech` library is missing (due to no ARM64 wheels).
- `stage-object-detector` uses placeholder model files during build; real inference requires mounting/downloading models.
- All functions now emit structured JSON logs with `duration_ms`, `memory_limit_mb`, and `cost_unit`.
- Deployment regimes (cold, warm, burst-ready) can be applied via `scripts/deploy_regime.sh`.
- **Blocker**: Local OpenFaaS environment is not operational. Docker Swarm setup with `faas-swarm` failed due to API incompatibility (Error response from daemon). Kubernetes (Docker Desktop) is not enabled/configured.
- Smoke tests passed for import/logic verification of final stages.

## Next Steps
1. **Unblock Environment**: Enable Kubernetes in Docker Desktop and install OpenFaaS via `arkade`, or troubleshoot `faas-swarm` container.
2. **Experiments**:
   - Use `scripts/deploy_regime.sh` to apply cold/warm/burst-ready regimes.
   - Run steady/burst workloads via `scripts/workload_generator.py` and archive results under `experiments/`.
   - Monitor function logs/state.json for anomalies and cold-start markers.
3. **Analysis & Reporting**:
   - Aggregate run data (latency percentiles, cold-start frequency, cost proxy).
   - Produce plots/tables answering RQ2/RQ3 and draft the report.