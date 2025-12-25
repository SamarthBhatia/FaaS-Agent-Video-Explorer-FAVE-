# Project Status

## Summary
- **Date**: 2025-12-25
- **Current Phase**: Remediation & Re-verification
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

### Remaining / Blocked
- [ ] **Mitigation**: Update OpenFaaS Helm release for global timeouts (Blocked: No `helm`).
- [ ] Re-run `warm-steady` experiment (Blocked: No Cluster Access).
- [ ] Re-run `cold-burst` experiment (Blocked: No Cluster Access).
- [ ] Update Final Report with new data.

## Session Log

### 2025-12-25
- **Goal**: Apply mitigations (timeouts, retries) and re-run experiments to address failures identified in the final report.
- **Actions**:
    - Updated all `manifests/*-manual.yaml` files. Added `read_timeout`, `write_timeout`, `upstream_timeout`, and `exec_timeout` set to `300s` to prevent premature termination during long processing.
    - Updated `scripts/workload_generator.py` to include a retry loop (3 retries, exponential backoff) for HTTP 500/502/504 errors, improving robustness against transient gateway failures.
    - Attempted to verify cluster access via `kubectl` but failed (EOF). Cannot deploy new manifests or run experiments in the current environment.
    - Attempted to check `helm` for OpenFaaS config update but `helm` is not installed.
- **Outcome**: Mitigations applied to code/manifests. Execution blocked by environment limitations.

## Previous Findings (Legacy)
- **Cold Start Penalty**: >15 seconds.
- **Stability**: Default FaaS timeouts insufficient.
- **Race Conditions**: Parallel orchestrators revealed vulnerabilities.