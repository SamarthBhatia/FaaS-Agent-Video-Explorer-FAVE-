# FAVE – FaaS-Agent Video Explorer

  FAVE is a serverless refactor of the VideoSearcher pipeline. It decomposes the original toy app into an eight-stage OpenFaaS workflow that extracts audio, segments
  clips, performs transcription, samples frames, and runs YOLO-based detection—all using a claim-check pattern atop MinIO/S3 storage.

  ## Highlights

  - Agentic pipeline: Orchestrator + 7 processing stages (ffmpeg, librosa, deepspeech, detector).
  - Serverless-first: OpenFaaS functions, MinIO-backed artifacts, telemetry with duration/cost metrics.
  - Instrumentation: Workload generator, deployment regime script, and experiments for warm vs. cold behavior.
  - Analysis: Comprehensive report (FINAL_REPORT.md) with findings on cold-start penalties, success rates, and cost trade-offs.

  ———

  ## Architecture Overview

  1. orchestrator – stateful coordinator driving downstream stages and fan-out.
  2. stage-ffmpeg-0 – audio extraction + silent-track fallback.
  3. stage-librosa – speech segmentation via librosa.
  4. stage-ffmpeg-1 – precise clip cutting based on timestamps.
  5. stage-ffmpeg-2 – clip compression + 16 kHz audio packaging.
  6. stage-deepspeech – transcript generation (dummy fallback for local runs).
  7. stage-ffmpeg-3 – frame sampling (configurable rate).
  8. stage-object-detector – YOLOv4-tiny inference on sampled frames.

  All stages read/write artifacts in MinIO under requests/<id>/<stage>/…, keeping HTTP payloads lightweight.

  ———

  ## Repository Layout

  functions/                # OpenFaaS functions (Dockerfiles, services, index.py wrapper)
  scripts/                  # Workload & deployment tooling
  base-image/               # Shared Python base image (ffmpeg, boto3, helpers)
  docs/                     # Architecture/storage/base-image notes
  experiments/              # JSON logs from workloads
  tests/                    # Smoke tests for final stages
  FINAL_REPORT.md           # Full analysis of experiments
  status.md                 # Project tracker (completed)

  ———

  ## Prerequisites

  - Docker Desktop (with Kubernetes enabled) or another Kubernetes cluster.
  - arkade, kubectl, faas-cli, mc (MinIO client).
  - Python 3.9+ for scripts.
  - Optional: poetry/pip for local dependencies if you run tests.

  ———

  ## Quick Start

  1. Clone & build base image

     git clone <repo> && cd FAVE
     ./scripts/build-base-image.sh
  2. Start MinIO locally

     ./scripts/minio-dev.sh        # keep it running
     ./scripts/minio-bootstrap.sh  # create bucket + alias
  3. Install OpenFaaS

     arkade install openfaas
     kubectl -n openfaas port-forward svc/gateway 8080:8080 >/tmp/gateway.log &
     faas-cli login --gateway http://127.0.0.1:8080 -u admin --password <password>
  4. Create secrets

     export ARTIFACT_ACCESS_KEY=faveadmin
     export ARTIFACT_SECRET_KEY=favesecret
     printf "%s" "$ARTIFACT_ACCESS_KEY" | faas-cli secret create artifact-access-key --from-stdin
     printf "%s" "$ARTIFACT_SECRET_KEY" | faas-cli secret create artifact-secret-key --from-stdin
  5. Deploy functions

     faas-cli deploy -f functions/stack.yml
  6. Run a smoke request

     python scripts/workload_generator.py \
       --gateway http://127.0.0.1:8080 \
       --video s3://fave-artifacts/requests/sample.mp4 \
       --pattern steady --requests 1 --rps 1

  ———

  ## Running Experiments

  1. Apply regime (cold/warm/burst-ready):

     ./scripts/deploy_regime.sh warm
  2. Run workload:

     python scripts/workload_generator.py \
       --gateway http://127.0.0.1:8080 \
       --video s3://fave-artifacts/... \
       --pattern steady --requests 60 --rps 1 --output experiments
  3. Switch to bursty:

     python scripts/workload_generator.py \
       --pattern burst --requests 10 --profile warm --output experiments
  4. Analyze:

     python final_analysis.py
     python failure_analysis.py

  All experiment JSON logs land under experiments/. Final summaries and plots are captured in FINAL_REPORT.md.

  ———

  ## Results at a Glance

  | Regime | Pattern | P50 Latency (successes only) | Success Rate |
  |--------|---------|------------------------------|--------------|
  | Warm   | Baseline (1 req) | ~8.8 s | 100% |
  | Warm   | Steady (1 RPS)   | ~25 s* | 1.7% |
  | Cold   | Burst (10 req)   | >22 s  | 20% |

  *High failure rate; see report for details.

  Key findings:

  - Cold starts add 15–20 s due to heavy Python/ONNX initialization.
  - Default OpenFaaS timeouts are insufficient for multi-stage media pipelines.
  - Atomic state management (or a dedicated DB) is essential once orchestrations run in parallel.

  ———

  ## Troubleshooting & Notes

  - All functions rely on the bundled index.py wrapper (ThreadingHTTPServer) to handle chunked requests and concurrency.
  - stage-deepspeech runs a dummy path when real models aren’t available; swap in actual models if you need true transcripts.
  - You can run tests/smoke_test_stages.py locally to validate ffmpeg/object detector logic without hitting OpenFaaS.

  ———

  ## License & Acknowledgments

  The FAVE project was built as part of the Cloud Computing course at Politecnico di Milano. See FINAL_REPORT.md for the full narrative and references.

  Enjoy exploring video workloads on FaaS—and feel free to extend the pipeline, tweak sampling rates, or port it onto other serverless platforms.
