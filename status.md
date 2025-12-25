# Project Status

## Summary
- **Date**: 2025-12-25
- **Current Phase**: Remediation & Verification (Completed)
- **Upcoming Phase**: Final Report Update

## Task List
### Completed
- [x] Locate/import VideoSearcher baseline assets.
- [x] Stand up shared storage (MinIO) + verify access credentials.
- [x] Create base Docker image with shared dependencies (Python 3.9, ffmpeg, helpers).
- [x] Implement orchestrator and all pipeline stages.
- [x] Verify build of all function images.
- [x] Fix cross-architecture build issues.
- [x] Add cost proxy logging and telemetry.
- [x] Develop workload generator script.
- [x] Script deployment regimes.
- [x] Unblock Environment (OpenFaaS on K8s).
- [x] Fix Function Runtime (ThreadingHTTPServer).
- [x] End-to-End Verification.
- [x] Initial Experiments (`warm-steady`, `warm-burst`, `cold-steady`, `cold-burst`).
- [x] Initial Analysis & Reporting (`FINAL_REPORT.md`).
- [x] **Mitigation**: Increase function timeouts to 300s (Manifests updated).
- [x] **Mitigation**: Add retry logic to workload generator.
- [x] **Mitigation**: Fix Gateway discovery using Function CRD (`manifests/orchestrator-crd.yaml`).
- [x] **Re-run Experiment**: `warm-steady` with high concurrency (verified timeouts > 30s work).

### Remaining
- [ ] Investigate S3 `BadDigest` and `No such file` errors under high concurrency (Race conditions in Orchestrator?).
- [ ] Update `FINAL_REPORT.md` with new findings.

## Session Log

### 2025-12-25 (Session 2)
- **Goal**: Apply mitigations (timeouts, retries) and re-run experiments.
- **Actions**:
    - Updated all `manifests/*-manual.yaml` files with 300s timeouts.
    - Updated `scripts/workload_generator.py` with retry logic.
    - Patched OpenFaaS Gateway and Queue Worker to 300s timeouts.
    - **Debugged Gateway 404s**: Discovered that `direct_functions` bypass was failing in Gateway 0.27.10.
    - **Solution**: Created `manifests/orchestrator-crd.yaml` to register the function with `faas-netes` provider using `fprocess` wrapper for secret injection (bypassing the need for `valueFrom` which CRDs lack).
    - Executed `warm-verify` (1 req) successfully (34s duration).
    - Executed `warm-steady` (20 reqs, 1.0 RPS).
- **Results**:
    - **Success**: Functions no longer timeout at 20s. Long-running requests (up to ~315s) completed.
    - **New Issues**: High concurrency caused S3 upload errors (`BadDigest`) and local file race conditions (`/tmp/json-XX.tmp`), likely due to thread-safety issues in the Orchestrator's temp file handling.
    - **Conclusion**: Timeouts are fixed. Concurrency stability needs work.
