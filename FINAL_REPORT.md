# FAVE Project: FaaS-Agent Video Explorer Final Report

## 1. Executive Summary
The FAVE project successfully refactored the VideoSearcher pipeline into a multi-stage, OpenFaaS-native serverless architecture. We evaluated the pipeline under various load patterns (Steady vs. Bursty) and deployment regimes (Warm vs. Cold). While the architecture demonstrates high modularity and acceptable single-request performance (~8.8s), it revealed significant stability challenges under concurrency, primarily driven by gateway timeouts and state-management race conditions.

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
- **Threading Support**: Upgraded the function runtime from a single-threaded `HTTPServer` to a `ThreadingHTTPServer` to enable intra-pod concurrency.
- **Protocol Reliability**: Fixed a critical bug in request parsing by implementing manual chunked-encoding support in the function wrapper.
- **Offline Reliability**: Vendored all YOLO model weights into the repository to ensure deterministic builds without Internet dependencies.

## 3. Experimental Results

### 3.1 Latency Analysis
| Regime | Pattern | P50 Latency (ms) | Success Rate |
|--------|---------|------------------|--------------|
| **Warm** | Baseline (1 req) | 8,846 | 100% |
| **Warm** | Steady (1 RPS) | 25,485* | 1.7% |
| **Cold** | Burst (10 req) | >22,000 | 20.0% |

*\*Note: Aggregated metrics under load were heavily skewed by failures. P50/P90 values are computed only over successful "True Success" samples.*

### 3.2 Stability & Success Rate
The experiment revealed a "Stability Wall" when moving from single requests to concurrent workloads:
- **Gateway Timeouts**: Over 85% of requests in the steady-state runs failed with HTTP 500/504 errors. This indicates the OpenFaaS gateway and NATS queue were unable to handle the backpressure of long-running media tasks (~10s+ per stage) with default configurations.
- **State Race Conditions**: Orchestrator failures (e.g., `[Errno 2] No such file or directory`) highlighted that manual state persistence to MinIO suffered from race conditions during concurrent updates to shared request metadata.

### 3.3 Cost Proxy
- **Average Cost Unit**: ~4.25 units per successful end-to-end run.
- **Formula**: `(duration_ms / 1000) * (memory_limit_mb / 1024)`.
- **Finding**: Cost is linearly dependent on `stage-librosa` and `stage-ffmpeg-2` (compression), which together account for ~70% of the total pipeline duration.

## 4. Research Questions Answered

### RQ1: Decomposing VideoSearcher for OpenFaaS
**Finding**: The claim-check pattern (passing S3 URIs) is essential. Without it, the large media payloads would crash the OpenFaaS gateway. Decoupling the orchestrator from the processing logic allowed for parallel execution of clips (fan-out), reducing total latency.

### RQ2: Impact of Min/Max Replicas and Cold Starts
**Finding**: The "Cold Start" penalty in this pipeline is massive (>15 seconds). This is not just container boot time, but the overhead of loading Python media libraries (librosa, numpy) and initializing ONNX runtimes. For media workloads, a `min_replica > 0` strategy is mandatory for user-facing latency.

### RQ3: Latency-vs-Cost Trade-offs
**Finding**: There is a "sweet spot" for sampling. Increasing FPS in `ffmpeg-3` increases cost linearly (more object-detector calls) but improves detection recall. However, the most significant cost driver is the idle time spent waiting for container spin-up during cold starts.

## 5. Conclusions & Guidelines
1. **Timeout Extensions**: For media-heavy FaaS, gateway and upstream timeouts must be extended to at least 300s.
2. **Pre-warming**: Critical stages (`librosa`, `object-detector`) should never scale to zero in production due to the high initialization overhead.
3. **Atomic State**: Shared state must be managed via atomic S3 operations or a dedicated database (e.g., Redis) rather than local temp files, to avoid race conditions under load.
4. **Hardware Acceleration**: CPU-based inference (YOLOv4) is the primary bottleneck for tail latency; moving to GPU-enabled workers would be the next logical step for this architecture.
