# FAVE Project Plan

## 1. Objectives
- **Primary goal**: Refactor the VideoSearcher toy app into an agentic, multi-stage pipeline on OpenFaaS, then study how cold-start-aware configurations impact latency and cost proxy.
- **Research questions**:
  1. How should VideoSearcher be decomposed into OpenFaaS-friendly stages plus an orchestrator?
  2. How do variations in min/max replicas and scale-to-zero timeouts influence end-to-end latency and cold-start frequency?
  3. What latency-vs-cost trade-offs emerge, and which guidelines can we derive for similar workloads?
- **Out of scope**: Custom autoscaler implementations, GPU-based LLM deployments, or full AWS replication (optional miniature Lambda test only).

## 2. Milestones & Timeline (2.5 weeks)
1. **Assets & Environment (Days 1-2)**  
   Retrieve VideoSearcher sources/datasets, prepare OpenFaaS gateway, container registry, shared object storage, and logging stack.
2. **Architecture Finalization (Days 3-5)**  
   Define orchestrator responsibilities, stage boundaries, storage conventions, and payload schemas; document claim-check data flow.
3. **Function Development (Days 6-9)**  
   Build base image, implement orchestrator + processing functions with storage + telemetry hooks.
4. **Instrumentation & Workloads (Days 10-12)**  
   Add cost proxy logging, develop workload generator, and script deployment regimes.
5. **Experiments (Days 13-15)**  
   Run steady/bursty workloads under cold/warm/burst-ready configurations; save raw traces.
6. **Analysis & Reporting (Days 16-19)**  
   Aggregate data, compute latency/cost metrics, craft visualizations, and draft findings (optional Lambda mini-test if time permits).
7. **Buffer & Polish (Day 20)**  
   Final QA, documentation touch-ups, submission prep.

## 3. Architecture Blueprint
1. **Shared storage (claim-check)**  
   - Object store (MinIO/S3) stores original video, intermediate artifacts, metadata JSON.  
   - Each function accepts URIs instead of bulky payloads; only small JSON (<100 KB) flows through HTTP.
2. **Functions**  
   - `orchestrator`: OpenFaaS function acting as director—ingests request, writes orchestration record, triggers downstream stages, aggregates responses.  
   - `audio-extractor`: pulls video, extracts audio, uploads results.  
   - `frame-sampler`: reads video/audio, stores sampled frames/clips metadata.  
   - `feature-embedder`: generates embeddings/features per sampled frame.  
   - `explanation-agent`: uses hosted LLM or synthetic CPU task to produce textual summaries.  
   - Additional helper tasks as needed (e.g., search/query stage).  
3. **Data contracts**  
   - Common envelope: `{ "request_id": "...", "input_uri": "...", "output_uri": "...", "stage": "...", "config": { ... } }`.  
   - Metadata stored alongside results to enable resume/replay.  
4. **Observability**  
   - Each function logs JSON lines with timestamps, container cold-start flag, duration_ms, memory_limit_mb.  
   - Logs shipped to storage or Loki; metrics exported via Prometheus where feasible.

## 4. Detailed Tasks
### 4.1 Baseline & Environment
- Pull VideoSearcher code + clips; document dependencies.  
- Stand up MinIO/S3 bucket with lifecycle policies for temporary artifacts.  
- Configure OpenFaaS CLI, gateway access, and container registry credentials.  
- Verify ffmpeg + Python media libs inside dev container.

### 4.2 Architecture & Contracts
- Draft sequence diagrams showing orchestrator interactions and storage reads/writes.  
- Specify naming conventions for storage keys (e.g., `requests/{request_id}/stage/output.ext`).  
- Decide on idempotency/retry behavior and error reporting payloads.  
- Record choices in `docs/architecture.md` (to be created later).

### 4.3 Base Image & Shared Library
- Construct a Python base image with ffmpeg, boto3/minio, and shared logging/helpers.  
- Publish image to registry, note version tags for reproducible deployments.  
- Provide sample `requirements.txt` for individual functions referencing shared libs.

### 4.4 Function Implementations
- Build orchestrator OpenFaaS function with asynchronous triggering of downstream stages (REST calls via gateway).  
- Implement processing functions with modular code, reading configs from env.  
- Ensure each function writes outputs to storage and returns metadata references only.  
- Add unit-style smoke tests executable locally via `faas-cli invoke`.

### 4.5 Telemetry & Cost Proxy
- Embed logging helper capturing `duration_ms`, `memory_limit_mb`, `cold_start` flag, and `stage`.  
- Define cost proxy: `cost_unit = (duration_ms / 1000) * (memory_limit_mb / 1024)`.  
- Ensure orchestrator aggregates downstream metrics for holistic view.  
- Optionally expose Prometheus metrics for automated scraping.

### 4.6 Workload Generator & Deployment Scripts
- Create Python CLI to invoke orchestrator with configured load patterns (steady, bursty, moderate).  
- Parameterize runtime (duration, concurrency, think time) for repeatable runs.  
- Write deployment scripts (Makefile or bash) to apply OpenFaaS `stack.yml` per regime:  
  - `cold`: minReplicas=0, aggressive scale-to-zero.  
  - `warm`: minReplicas>=1 for orchestrator + hot stages.  
  - `burst-ready`: higher min/max replicas, extended idle timeout.  
- Include validation commands that confirm functions can access storage.

### 4.7 Experiment Execution
- For each regime/load combo:  
  - Warm up functions.  
  - Execute workload generator, capture orchestrator outputs, and archive logs under `experiments/{regime}/{load}/`.  
  - Record gateway metrics and storage usage snapshots.  
- Document anomalies (failures, timeouts) for later discussion.

### 4.8 Analysis & Reporting
- Build notebooks/scripts to parse logs, compute latency percentiles, cold-start frequency, and total cost proxy.  
- Visualize trade-offs (e.g., latency boxplots vs. cost bars).  
- Summarize findings per RQ2/RQ3, including recommendations on minReplica/maxReplica tuning for similar workloads.  
- Optional: run a reduced Lambda test for a single stage and document qualitative differences.  
- Assemble final write-up referencing methodology, results, and lessons learned.

## 5. Dependencies & Risks
- **Dependencies**: OpenFaaS cluster availability, shared storage credentials, access to sample videos, optional LLM API keys.  
- **Risks**: Time overruns due to complex media processing, gateway limits on payload size, storage performance bottlenecks, inability to simulate AWS comparison.  
- **Mitigations**: Use synthetic workload/CPU tasks where data is scarce; keep payloads reference-based; prioritize OpenFaaS experiments before optional AWS tasks.

## 6. Deliverables
- Source code for orchestrator + functions with Dockerfiles.  
- Deployment manifests (`stack.yml`) for each regime.  
- Workload generator scripts.  
- Experiment log archives + analysis notebooks.  
- Final report summarizing methodology, experiments, and conclusions.

## 7. Next Immediate Actions
1. Locate/import VideoSearcher baseline assets.  
2. Stand up shared storage + verify access credentials.  
3. Draft architecture diagrams and storage conventions based on the above plan.  
4. Update `status.md` after each concrete step is completed.
