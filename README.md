# FAVE – FaaS-Agent Video Explorer

FAVE is a serverless refactor of the VideoSearcher pipeline. It decomposes the original toy app into an eight-stage OpenFaaS workflow that extracts audio, segments clips, performs transcription, samples frames, and runs YOLO-based detection—all using a claim-check pattern atop MinIO/S3 storage.

## Highlights

- **Agentic pipeline**: Orchestrator + 7 processing stages (ffmpeg, librosa, deepspeech, detector).
- **Serverless-first**: OpenFaaS functions, MinIO-backed artifacts, telemetry with duration/cost metrics.
- **Monitoring**: Prometheus metrics collection + Grafana dashboard with 24 panels for live monitoring.
- **Load Testing**: JMeter-based automated video ingestion and load testing.
- **Analysis**: Experiments for warm vs. cold behavior, cost trade-offs, and cold-start penalties.

---

## Architecture Overview

1.  **orchestrator** – stateful coordinator driving downstream stages and fan-out.
2.  **stage-ffmpeg-0** – audio extraction + silent-track fallback.
3.  **stage-librosa** – speech segmentation via librosa.
4.  **stage-ffmpeg-1** – precise clip cutting based on timestamps.
5.  **stage-ffmpeg-2** – clip compression + 16 kHz audio packaging.
6.  **stage-deepspeech** – transcript generation (dummy fallback for local runs).
7.  **stage-ffmpeg-3** – frame sampling (configurable rate).
8.  **stage-object-detector** – YOLOv4-tiny inference on sampled frames.

All stages read/write artifacts in MinIO under `requests/<id>/<stage>/…`, keeping HTTP payloads lightweight.

---

## Repository Layout

- `functions/` – OpenFaaS functions (Dockerfiles, services, handlers).
- `manifests/` – Kubernetes manifests (functions, MinIO, Grafana).
- `scripts/` – Workload generator, JMeter runner, video ingestion, deployment tools, analysis scripts.
- `base-image/` – Shared Python base image (ffmpeg, boto3, helpers).
- `datasets/` – Video source configs and JMeter CSV data.
- `jmeter/` – JMeter test plan for load testing.
- `docs/` – Architecture and design notes.
- `experiments/` – Raw data, charts, and logs from performance experiments.
- `tests/` – Smoke tests for logic verification.

---

## Prerequisites

Install on macOS:

```bash
# Kubernetes: Enable in Docker Desktop → Settings → Kubernetes → Enable Kubernetes

# MinIO client
brew install minio/stable/mc

# arkade (OpenFaaS installer)
curl -sLS https://get.arkade.dev | sh

# faas-cli (OpenFaaS CLI)
arkade get faas-cli

# JMeter (load testing)
brew install jmeter

# Python dependencies (for video ingestion and workload generator)
pip3 install httpx boto3 requests
```

---

## Setup & Run Guide

### Step 1: Install OpenFaaS (includes Prometheus)

```bash
arkade install openfaas-ce
kubectl rollout status deployment/gateway -n openfaas --timeout=5m

# Verify Prometheus is running (deployed automatically with OpenFaaS CE)
kubectl rollout status deployment/prometheus -n openfaas --timeout=2m
```

### Step 2: Deploy MinIO

```bash
kubectl apply -f manifests/minio-k8s.yaml
kubectl rollout status deployment/minio -n default --timeout=2m
```

### Step 3: Deploy Grafana

```bash
kubectl apply -f manifests/grafana.yaml
kubectl rollout status deployment/grafana -n openfaas --timeout=2m
```

### Step 4: Port-forward all services

```bash
# Kill any existing port-forwards first
lsof -i :8080 -t | xargs kill -9 2>/dev/null
lsof -i :9000 -t | xargs kill -9 2>/dev/null
lsof -i :9090 -t | xargs kill -9 2>/dev/null
lsof -i :3000 -t | xargs kill -9 2>/dev/null

kubectl port-forward -n openfaas svc/gateway 8080:8080 &
kubectl port-forward -n default svc/minio 9000:9000 &
kubectl port-forward -n openfaas svc/prometheus 9090:9090 &
kubectl port-forward -n openfaas svc/grafana 3000:3000 &
sleep 3
```

### Step 5: Create secrets

```bash
kubectl create namespace openfaas-fn 2>/dev/null || true

kubectl create secret generic artifact-access-key \
  --from-literal=artifact-access-key=faveadmin -n openfaas-fn \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic artifact-secret-key \
  --from-literal=artifact-secret-key=favesecret -n openfaas-fn \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Step 6: Build all Docker images

```bash
# Build base image (shared dependencies — takes ~2 min first time)
./scripts/build-base-image.sh

# Build all 8 function images
faas-cli build -f functions/stack.yml
```

### Step 7: Deploy all functions

```bash
# Deploy orchestrator and all stages
kubectl apply -f manifests/orchestrator-manual.yaml
for f in manifests/stage-*-manual.yaml; do kubectl apply -f "$f"; done

# Scale all functions to 1 replica (warm regime)
./scripts/deploy_regime.sh warm

# Wait for all pods to be running
kubectl get pods -n openfaas-fn -w
# >>> Press Ctrl+C once all 8 pods show "Running 1/1", then continue to Step 8
```

### Step 8: Setup MinIO bucket and ingest videos

```bash
# Configure MinIO client
mc alias set fave-local http://127.0.0.1:9000 faveadmin favesecret

# Create bucket
mc mb --ignore-existing fave-local/fave-artifacts

# Ingest sample videos from datasets/video_sources.csv into MinIO
# (downloads videos and generates datasets/jmeter_videos.csv for JMeter)
python3 scripts/auto_ingest_videos.py --limit 3

# Verify videos are in MinIO
python3 scripts/auto_ingest_videos.py --list
```

### Step 9: Run load test with JMeter

```bash
# Default warm test (5 threads, 5s ramp-up)
./scripts/run_jmeter_test.sh --skip-ingest

# Cold burst test (all threads fire simultaneously)
./scripts/run_jmeter_test.sh --cold --skip-ingest

# Custom thread count
./scripts/run_jmeter_test.sh --threads 10 --skip-ingest

# Open JMeter GUI to inspect or modify the test plan
./scripts/run_jmeter_test.sh --gui

# JMeter results are saved as .jtl and .json in experiments/jmeter/
```

### Step 10: Monitor with Prometheus & Grafana

```bash
# Grafana dashboard (pre-provisioned with FAVE Pipeline Dashboard):
open http://localhost:3000/d/fave-pipeline
# Login: admin / fave2024 (or browse anonymously)
```

The dashboard shows 24 panels across 4 sections:
- **Live Metrics**: invocation rate, latency percentiles, success rate, active replicas
- **Cold vs Warm Analysis**: cold start detection, latency distribution, replica scaling
- **Cost & Resource Monitoring**: estimated cost units, cost rate, duration/invocation breakdown
- **Error tracking**: error rate by function

Prometheus raw metrics are available at http://localhost:9090 for ad-hoc queries.

Run JMeter while watching Grafana to see live metrics — JMeter shows client-side performance (end-to-end latency), Grafana shows server-side performance (per-function latency, cold starts, scaling).

### Step 11: Analyze results (optional)

```bash
python3 scripts/final_analysis.py
# Generates charts and regime_statistics.csv in experiments/
```

---

## HPA Autoscaling Experiment (VM / Server)

The pipeline was deployed on a university VM running MicroK8s and tested with Kubernetes Horizontal Pod Autoscaler (HPA) to demonstrate auto-scaling under load.

**Setup:**
- Single-node MicroK8s cluster with 8 function pods
- HPA configured on 5 CPU-intensive functions (target: 60% CPU utilization, max 3 replicas)
- JMeter load test: 2 threads x 10 loops = 20 pipeline requests

**Results (19/20 successful, 95% success rate):**
- HPA scaled `stage-librosa`, `stage-object-detector`, `stage-ffmpeg-0`, `stage-ffmpeg-3` from 1 to 3 replicas
- `stage-deepspeech` scaled to 2 replicas
- `stage-librosa` peaked at ~1500m CPU, `stage-object-detector` at ~930m CPU
- Response times: 9.5–12s per end-to-end pipeline invocation

Plots in `experiments/reports/prof/`:
1. `1_throughput_vs_time.png` – JMeter throughput over time
2. `2_pods_per_function_vs_time.png` – Pod scaling per function
3. `3_response_time_vs_time.png` – End-to-end response time
4. `4_cpu_utilization_vs_time.png` – CPU usage per function

JMeter HTML dashboard in `experiments/jmeter-dashboard/vm-final/`.

**Generating plots from raw data:**
```bash
python3 scripts/generate_scaling_plots.py \
    --jtl experiments/jmeter/results_vm_long_20260324_160219.jtl \
    --pod-counts experiments/metrics/pod_counts_20260324_160024.csv \
    --cpu-util experiments/metrics/cpu_util_20260324_160024.csv \
    --output experiments/reports/prof
```

---

## Running Experiments

Tools to simulate different deployment regimes (Warm vs. Cold) and traffic patterns:

1.  **Apply a Regime**:
    ```bash
    ./scripts/deploy_regime.sh warm   # Scale functions to 1 replica
    ./scripts/deploy_regime.sh cold   # Scale down to 0
    ```

2.  **Run Workload** (alternative to JMeter):
    ```bash
    # Single request
    python3 scripts/workload_generator.py \
      --gateway http://localhost:8080 \
      --video s3://fave-artifacts/input/classroom.mp4 \
      --pattern steady --requests 1 --rps 1 --profile warm-test

    # Burst (5 concurrent requests)
    python3 scripts/workload_generator.py \
      --gateway http://localhost:8080 \
      --video s3://fave-artifacts/input/classroom.mp4 \
      --pattern burst --requests 5 --profile burst-test
    ```

3.  **Analyze Results**:
    ```bash
    python3 scripts/final_analysis.py
    ```

---

## Teardown

```bash
# Stop port-forwards
lsof -i :8080 -t | xargs kill -9 2>/dev/null
lsof -i :9000 -t | xargs kill -9 2>/dev/null
lsof -i :9090 -t | xargs kill -9 2>/dev/null
lsof -i :3000 -t | xargs kill -9 2>/dev/null

# Delete all function deployments
kubectl delete -f manifests/orchestrator-manual.yaml
for f in manifests/stage-*-manual.yaml; do kubectl delete -f "$f"; done

# Delete Grafana
kubectl delete -f manifests/grafana.yaml

# Delete MinIO
kubectl delete -f manifests/minio-k8s.yaml

# Delete OpenFaaS (also removes Prometheus)
kubectl delete namespace openfaas openfaas-fn

# (Optional) Disable Kubernetes entirely in Docker Desktop:
# Docker Desktop → Settings → Kubernetes → Uncheck "Enable Kubernetes"
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Port already in use | `lsof -i :<port> -t \| xargs kill -9` then re-run port-forward |
| Secrets already exist | The `--dry-run=client` commands handle this automatically |
| MinIO bucket not found | Re-run Step 8 (`mc mb` + `auto_ingest_videos.py`) |
| Pods stuck in Pending | Wait for Docker Desktop Kubernetes to settle, check `kubectl get events -n openfaas-fn` |
| 502/503 from gateway | Wait 30s for pods to warm up, then retry |
| `kubectl get pods -w` hangs | That's normal — press Ctrl+C once all pods show Running |
| JMeter not found | `brew install jmeter` |
| `jmeter_videos.csv` missing | Run `python3 scripts/auto_ingest_videos.py --limit 3` |
| Grafana shows "No data" | Ensure Prometheus is running: `kubectl get pods -n openfaas -l app=prometheus` |
| Grafana login | admin / fave2024, or browse anonymously (read-only) |
| ImagePullBackOff | Ensure you've built images locally (`faas-cli build`); Docker Desktop shares the image cache |

---

## License

This project is part of the Cloud Computing course at Politecnico di Milano.
