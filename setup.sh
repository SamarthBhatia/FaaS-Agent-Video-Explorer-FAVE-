#!/bin/bash
#
# FAVE Project — One-Time Setup Script
#
# Run this once to set up the entire FAVE pipeline.
# After setup completes, use the commands printed at the end
# to run tests and open monitoring dashboards.
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
#

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

step() {
    echo ""
    echo -e "${GREEN}${BOLD}=== Step $1: $2 ===${NC}"
    echo ""
}

warn() {
    echo -e "${YELLOW}WARNING: $1${NC}"
}

fail() {
    echo -e "${RED}ERROR: $1${NC}"
    exit 1
}

# ─── Pre-flight checks ───────────────────────────────────────────────

echo -e "${BOLD}FAVE Project Setup${NC}"
echo "=========================================="

MISSING=""
command -v kubectl &>/dev/null || MISSING="$MISSING kubectl"
command -v docker &>/dev/null  || MISSING="$MISSING docker"
command -v faas-cli &>/dev/null || MISSING="$MISSING faas-cli"
command -v mc &>/dev/null      || MISSING="$MISSING mc(minio-client)"
command -v arkade &>/dev/null  || MISSING="$MISSING arkade"
command -v python3 &>/dev/null || MISSING="$MISSING python3"
command -v jmeter &>/dev/null  || MISSING="$MISSING jmeter"

if [ -n "$MISSING" ]; then
    fail "Missing tools:$MISSING\n\nInstall them first (see README.md Prerequisites section)."
fi

# Check Kubernetes is running
kubectl cluster-info &>/dev/null || fail "Kubernetes is not running. Enable it in Docker Desktop → Settings → Kubernetes."

echo "All prerequisites found."

# ─── Step 1: Install OpenFaaS (includes Prometheus) ──────────────────

step 1 "Install OpenFaaS (includes Prometheus)"

if kubectl get namespace openfaas &>/dev/null; then
    echo "OpenFaaS already installed, skipping."
else
    arkade install openfaas-ce
fi

echo "Waiting for gateway..."
kubectl rollout status deployment/gateway -n openfaas --timeout=5m

echo "Waiting for Prometheus..."
kubectl rollout status deployment/prometheus -n openfaas --timeout=2m

# Install metrics-server if not present (required for HPA)
if ! kubectl get deployment metrics-server -n kube-system &>/dev/null; then
    echo "Installing metrics-server (required for HPA)..."
    kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
    # Docker Desktop needs --kubelet-insecure-tls
    kubectl patch deployment metrics-server -n kube-system \
        --type='json' \
        -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--kubelet-insecure-tls"}]' \
        2>/dev/null || true
    kubectl rollout status deployment/metrics-server -n kube-system --timeout=2m
else
    echo "metrics-server already installed."
fi

# ─── Step 2: Deploy MinIO ────────────────────────────────────────────

step 2 "Deploy MinIO"

kubectl apply -f manifests/minio-k8s.yaml
kubectl rollout status deployment/minio -n default --timeout=2m

# ─── Step 3: Deploy Grafana ──────────────────────────────────────────

step 3 "Deploy Grafana"

kubectl apply -f manifests/grafana.yaml
kubectl rollout status deployment/grafana -n openfaas --timeout=2m

# ─── Step 4: Port-forward all services ───────────────────────────────

step 4 "Port-forward all services"

# Kill existing port-forwards
for PORT in 8080 9000 9090 3000; do
    lsof -i :$PORT -t 2>/dev/null | xargs kill -9 2>/dev/null || true
done

kubectl port-forward -n openfaas svc/gateway 8080:8080 &>/dev/null &
kubectl port-forward -n default svc/minio 9000:9000 &>/dev/null &
kubectl port-forward -n openfaas svc/prometheus 9090:9090 &>/dev/null &
kubectl port-forward -n openfaas svc/grafana 3000:3000 &>/dev/null &
sleep 3

echo "Port-forwards active:"
echo "  Gateway:    http://localhost:8080"
echo "  MinIO:      http://localhost:9000"
echo "  Prometheus: http://localhost:9090"
echo "  Grafana:    http://localhost:3000"

# ─── Step 5: Create secrets ──────────────────────────────────────────

step 5 "Create secrets"

kubectl create namespace openfaas-fn 2>/dev/null || true

kubectl create secret generic artifact-access-key \
  --from-literal=artifact-access-key=faveadmin -n openfaas-fn \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic artifact-secret-key \
  --from-literal=artifact-secret-key=favesecret -n openfaas-fn \
  --dry-run=client -o yaml | kubectl apply -f -

# ─── Step 6: Build Docker images ─────────────────────────────────────

step 6 "Build Docker images"

echo "Building base image..."
./scripts/build-base-image.sh

echo "Building all 8 function images..."
faas-cli build -f functions/stack.yml

# ─── Step 7: Deploy functions ────────────────────────────────────────

step 7 "Deploy all functions"

kubectl apply -f manifests/orchestrator-manual.yaml
for f in manifests/stage-*-manual.yaml; do kubectl apply -f "$f"; done

./scripts/deploy_regime.sh warm

echo "Waiting for function pods to be ready..."
kubectl wait --for=condition=available deployment --all -n openfaas-fn --timeout=5m

# ─── Step 8: Setup MinIO bucket and ingest videos ────────────────────

step 8 "Setup MinIO bucket and ingest videos"

mc alias set fave-local http://127.0.0.1:9000 faveadmin favesecret
mc mb --ignore-existing fave-local/fave-artifacts

echo "Ingesting sample videos into MinIO..."
python3 scripts/auto_ingest_videos.py --limit 3

# ─── Done ─────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}${BOLD}=========================================="
echo "  FAVE Setup Complete!"
echo "==========================================${NC}"
echo ""
echo -e "${BOLD}Run load tests:${NC}"
echo "  ./scripts/run_jmeter_test.sh --skip-ingest              # Warm test (5 threads)"
echo "  ./scripts/run_jmeter_test.sh --cold --skip-ingest       # Cold burst test"
echo "  ./scripts/run_jmeter_test.sh --threads 10 --skip-ingest # Custom threads"
echo "  ./scripts/run_jmeter_test.sh --gui                      # Open JMeter GUI"
echo ""
echo -e "${BOLD}Open monitoring dashboards:${NC}"
echo "  open http://localhost:3000/d/fave-pipeline   # Grafana (admin / fave2024)"
echo "  open http://localhost:9090   # Prometheus"
echo ""
echo -e "${BOLD}Analyze results:${NC}"
echo "  python3 scripts/final_analysis.py"
echo ""
echo -e "${BOLD}Teardown (when done):${NC}"
echo "  ./teardown.sh"
