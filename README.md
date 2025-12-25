# FAVE – FaaS-Agent Video Explorer

FAVE is a serverless refactor of the VideoSearcher pipeline. It decomposes the original toy app into an eight-stage OpenFaaS workflow that extracts audio, segments clips, performs transcription, samples frames, and runs YOLO-based detection—all using a claim-check pattern atop MinIO/S3 storage.

## Highlights

- **Agentic pipeline**: Orchestrator + 7 processing stages (ffmpeg, librosa, deepspeech, detector).
- **Serverless-first**: OpenFaaS functions, MinIO-backed artifacts, telemetry with duration/cost metrics.
- **Instrumentation**: Workload generator, deployment regime script, and experiments for warm vs. cold behavior.
- **Analysis**: Comprehensive report (`FINAL_REPORT.md`) with findings on cold-start penalties, success rates, and cost trade-offs.

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

- `functions/`: OpenFaaS functions (Dockerfiles, services, handlers).
- `manifests/`: Kubernetes manifests for manual deployment (bypasses CE restrictions).
- `scripts/`: Workload generator, deployment tools, and analysis scripts.
- `base-image/`: Shared Python base image (ffmpeg, boto3, helpers).
- `docs/`: Architecture and design notes.
- `experiments/`: Raw data and logs from performance experiments.
- `tests/`: Smoke tests for logic verification.
- `FINAL_REPORT.md`: Full analysis of experimental results.

---

## Prerequisites

- **Docker Desktop** (Kubernetes enabled) or a standard Kubernetes cluster.
- **Tools**: `kubectl`, `faas-cli`, `mc` (MinIO client), `python3` (3.9+).
- **Optional**: `arkade` (for easy OpenFaaS installation).

---

## Quick Start

### 1. Setup Environment

Clone the repository:
```bash
git clone <repo_url> && cd FAVE
```

Build the base image:
```bash
./scripts/build-base-image.sh
```

### 2. Install Infrastructure (Kubernetes)

Use `arkade` or Helm to install OpenFaaS and MinIO:
```bash
# Install OpenFaaS
arkade install openfaas

# Install MinIO
kubectl apply -f manifests/minio-k8s.yaml
```

**Port-forward services** (keep these running in background terminals):
```bash
# OpenFaaS Gateway (8080)
kubectl port-forward -n openfaas svc/gateway 8080:8080 &

# MinIO API (9000)
kubectl port-forward -n default svc/minio 9000:9000 &
```

### 3. Configure Credentials

Create the required secrets in the `openfaas-fn` namespace (where the functions run):
```bash
kubectl create namespace openfaas-fn || true

# Access keys for the local dev MinIO
kubectl create secret generic artifact-access-key \
  --from-literal=artifact-access-key=faveadmin -n openfaas-fn
kubectl create secret generic artifact-secret-key \
  --from-literal=artifact-secret-key=favesecret -n openfaas-fn
```

Retrieve the OpenFaaS admin password and log in:
```bash
PASSWORD=$(kubectl get secret -n openfaas basic-auth -o jsonpath="{.data.basic-auth-password}" | base64 --decode; echo)
echo -n $PASSWORD | faas-cli login --username admin --password-stdin
```

### 4. Deploy Functions

**Manual Manifests (Bypass CE Registry Restrictions)**
Build the images locally:
```bash
faas-cli build -f functions/stack.yml
```

Apply the manifests:
```bash
kubectl apply -f manifests/orchestrator-manual.yaml
for f in manifests/stage-*-manual.yaml; do kubectl apply -f $f; done
```


**Option B: Standard Deployment**
*Requires pushing images to a public registry (Docker Hub/GHCR).*
```bash
faas-cli up -f functions/stack.yml
```

### 5. Run a Smoke Test

Download a sample video and upload it to the local MinIO bucket:
```bash
# Setup bucket alias
mc alias set fave-local http://127.0.0.1:9000 faveadmin favesecret
mc mb --ignore-existing fave-local/fave-artifacts

# Download sample
curl -L -o sample.mp4 https://github.com/intel-iot-devkit/sample-videos/raw/master/classroom.mp4
mc cp sample.mp4 fave-local/fave-artifacts/input/sample.mp4
```

Trigger the pipeline:
```bash
python3 scripts/workload_generator.py \
  --gateway http://127.0.0.1:8080 \
  --video s3://fave-artifacts/input/sample.mp4 \
  --pattern steady --requests 1 --rps 1
```

---

## Running Experiments

We provide tools to simulate different deployment regimes (Warm vs. Cold) and traffic patterns.

1.  **Apply a Regime**:
    ```bash
    # Scales functions to 1 replica (Warm) or 0/low resources (Cold)
    ./scripts/deploy_regime.sh warm
    ```

2.  **Run Workload**:
    ```bash
    # Steady state (1 req/sec for 60s)
    python3 scripts/workload_generator.py \
      --pattern steady --requests 60 --rps 1 --profile warm-steady

    # Burst (10 concurrent requests)
    python3 scripts/workload_generator.py \
      --pattern burst --requests 10 --profile warm-burst
    ```

3.  **Analyze Results**:
    ```bash
    python3 scripts/final_analysis.py
    ```

---

## Key Results

| Regime | Pattern | Latency (P50) | Notes |
|--------|---------|---------------|-------|
| Warm   | Baseline| ~8.8 s        | Full pipeline success |
| Cold   | Burst   | >22.0 s       | Heavy initialization penalty |

See `FINAL_REPORT.md` for detailed graphs and findings.

---

## Troubleshooting

- **500 Internal Server Error**: Often due to timeouts on the gateway. The default is 60s, which is short for video processing.
- **ImagePullBackOff**: Ensure you've built the images locally (`faas-cli build`) and that your Kubernetes cluster can see them (Docker Desktop shares the image cache automatically).
- **"Community Edition" Error**: Use the **Option A** deployment method (manual manifests) to bypass registry checks.

---

## License

This project is part of the Cloud Computing course at Politecnico di Milano.