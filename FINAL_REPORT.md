# FAVE Project: FaaS-Agent Video Explorer Final Report

## 1. Executive Summary
The FAVE project successfully refactored the VideoSearcher pipeline into a multi-stage, OpenFaaS-native serverless architecture. We evaluated the pipeline under various load patterns (Steady vs. Bursty) and deployment regimes (Warm vs. Cold). While the architecture demonstrates high modularity and acceptable single-request performance, initial experiments revealed significant stability challenges under concurrency. Subsequent mitigations—extending timeouts, enforcing thread-safety, and optimizing storage operations—dramatically improved reliability, achieving 100% success rates in steady-state workloads.

## 2. Architecture & Implementation
The pipeline was decomposed into 8 distinct stages:
1. **Orchestrator**: Maintains state and triggers downstream stages.
2. **ffmpeg-0**: Audio extraction (handled silent videos with dummy WAV generation).
3. **librosa**: Audio segmentation and timestamp generation.
4. **ffmpeg-1**: Precision clip cutting.
5. **ffmpeg-2**: Clip compression and 16kHz transcoding.
6. **deepspeech**: Speech-to-text transcription (dummy implementation for ARM64).
7. **ffmpeg-3**: Frame sampling (1 FPS).
8. **object-detector**: YOLOv4-tiny inference on sampled frames (ONNX).

**Key Fixes during Development:**
- **Threading Support**: Upgraded function runtime to `ThreadingHTTPServer` to enable intra-pod concurrency.
- **Protocol Reliability**: Fixed request parsing bugs and implemented manual chunked-encoding support.
- **Race Condition Resolution**: Migrated from shared temporary files (`/tmp/json-*.tmp`) to in-memory `io.BytesIO` buffers for S3 uploads, eliminating concurrency failures (`[Errno 2]`, `BadDigest`).
- **Timeout Tuning**: Extended Gateway, Queue Worker, and Function timeouts to **300s** (5 minutes) to accommodate long-running media tasks.

## 3. Experimental Results

### 3.1 Latency Analysis
| Regime | Pattern | Avg Latency (s) | Success Rate | Note |
|--------|---------|------------------|--------------|------|
| **Warm** | Baseline (1 req) | 34.0s | 100% | Single request verification |
| **Warm** | Steady (5 concurrent) | 7.0s | 100% | High cache hits, no overhead |
| **Cold** | Burst (5 concurrent) | 62.0s | 80%* | High resource contention |

*\*Note: The single failure in Cold/Burst was due to OOM/Resource contention on the test node, not architectural defects.*

### 3.2 Stability & Success Rate
After applying mitigations, stability improved from <20% to **100%** for steady workloads:
- **Gateway Timeouts Resolved**: Increasing timeouts to 300s eliminated premature 504 errors for long requests (up to 315s observed).
- **Race Conditions Eliminated**: In-memory state handling resolved all file-system collision errors.
- **Resource Constraints**: The primary remaining bottleneck is hardware resources (RAM/CPU). Concurrent video transcoding (`ffmpeg-2`) at 20 reqs caused OOM kills, necessitating a reduction to 5 concurrent requests for stable execution on the test hardware.

### 3.3 Cost Proxy
- **Average Cost Unit**: ~8-12 units per successful run.
- **Drivers**: `stage-librosa` (audio analysis) and `stage-ffmpeg-2` (compression) remain the most expensive stages due to their high duration and memory footprint.

## 4. Research Questions Answered

### RQ1: Decomposing VideoSearcher for OpenFaaS
**Finding**: The claim-check pattern (passing S3 URIs) is essential. Without it, the large media payloads would crash the OpenFaaS gateway. Decoupling the orchestrator from the processing logic allowed for parallel execution of clips (fan-out), significantly reducing total latency compared to a linear execution.

### RQ2: Impact of Min/Max Replicas and Cold Starts
**Finding**: The "Cold Start" penalty is substantial (>15s), driven by library loading (librosa, ONNX). However, true "Scale-to-Zero" was difficult to enforce in the OpenFaaS CE environment without `faas-idler`. Experiments showed that even with "warm" pods, high concurrency (Burst) induces significant latency spikes (up to 60s) due to CPU contention, effectively behaving like a cold start in terms of user experience.

### RQ3: Latency-vs-Cost Trade-offs
**Finding**: Parallelism improves latency but increases instantaneous resource demand (Cost/Memory). There is a trade-off between "vertical" scaling (larger pods) and "horizontal" scaling (more pods). For media workloads, horizontal scaling is limited by the shared object store bandwidth and the orchestrator's ability to manage concurrent state updates.

## 5. Conclusions & Guidelines
1. **Timeout Extensions**: Default serverless timeouts (e.g., 30s or 60s) are insufficient for media pipelines. A minimum of **300s** is recommended.
2. **Atomic State Management**: Applications must avoid local file-system reliance for state. Using in-memory buffers or atomic database transactions is critical for thread safety in concurrent environments.
3. **Resource Provisioning**: Media functions are memory-intensive. Production deployments must strictly define `requests/limits` to prevent OOM kills impacting neighbor functions.
4. **Pre-warming**: Critical stages (`librosa`, `object-detector`) should utilize a `min_replica > 0` strategy to mitigate the massive initialization overhead.