#!/bin/bash
#
# FAVE Project — GKE Multi-Node Cluster Setup
#
# Creates a GKE cluster, pushes images to Artifact Registry,
# and deploys the full FAVE pipeline with HPA.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - A GCP project with billing enabled
#   - Docker running locally with all FAVE images built
#
# Usage:
#   export GCP_PROJECT=your-project-id
#   ./scripts/setup-gke.sh
#

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

step() { echo -e "\n${GREEN}${BOLD}=== Step $1: $2 ===${NC}\n"; }
warn() { echo -e "${YELLOW}WARNING: $1${NC}"; }
fail() { echo -e "${RED}ERROR: $1${NC}"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Configuration
GCP_PROJECT="${GCP_PROJECT:-}"
GKE_CLUSTER="${GKE_CLUSTER:-fave-cluster}"
GKE_ZONE="${GKE_ZONE:-us-central1-a}"
GKE_MACHINE="${GKE_MACHINE:-e2-standard-4}"
GKE_NODES="${GKE_NODES:-3}"
GAR_LOCATION="${GAR_LOCATION:-us-central1}"
GAR_REPO="${GAR_REPO:-fave}"

if [ -z "$GCP_PROJECT" ]; then
    fail "GCP_PROJECT not set. Export it first:\n  export GCP_PROJECT=your-project-id"
fi

GAR_PREFIX="${GAR_LOCATION}-docker.pkg.dev/${GCP_PROJECT}/${GAR_REPO}"

FAVE_IMAGES=(
    "fave-orchestrator"
    "fave-stage-ffmpeg-0"
    "fave-stage-ffmpeg-1"
    "fave-stage-ffmpeg-2"
    "fave-stage-ffmpeg-3"
    "fave-stage-librosa"
    "fave-stage-deepspeech"
    "fave-stage-object-detector"
)

echo -e "${BOLD}FAVE GKE Setup${NC}"
echo "=========================================="
echo "Project:    ${GCP_PROJECT}"
echo "Cluster:    ${GKE_CLUSTER}"
echo "Zone:       ${GKE_ZONE}"
echo "Nodes:      ${GKE_NODES} x ${GKE_MACHINE}"
echo "Registry:   ${GAR_PREFIX}"
echo "=========================================="

# Pre-flight checks
command -v gcloud &>/dev/null || fail "gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install"
command -v kubectl &>/dev/null || fail "kubectl not found"
command -v docker &>/dev/null || fail "docker not found"

gcloud config set project "$GCP_PROJECT"

# ─── Step 1: Create Artifact Registry ────────────────────────────────

step 1 "Create Artifact Registry repository"

if gcloud artifacts repositories describe "$GAR_REPO" --location="$GAR_LOCATION" &>/dev/null; then
    echo "Repository ${GAR_REPO} already exists, skipping."
else
    gcloud artifacts repositories create "$GAR_REPO" \
        --repository-format=docker \
        --location="$GAR_LOCATION" \
        --description="FAVE function images"
fi

gcloud auth configure-docker "${GAR_LOCATION}-docker.pkg.dev" --quiet

# ─── Step 2: Tag and push images ─────────────────────────────────────

step 2 "Tag and push Docker images to Artifact Registry"

for IMG in "${FAVE_IMAGES[@]}"; do
    LOCAL_TAG="${IMG}:dev"
    REMOTE_TAG="${GAR_PREFIX}/${IMG}:dev"

    echo "Pushing ${IMG}..."
    docker tag "$LOCAL_TAG" "$REMOTE_TAG"
    docker push "$REMOTE_TAG"
done

echo "All images pushed."

# ─── Step 3: Create GKE cluster ──────────────────────────────────────

step 3 "Create GKE cluster"

if gcloud container clusters describe "$GKE_CLUSTER" --zone="$GKE_ZONE" &>/dev/null; then
    echo "Cluster ${GKE_CLUSTER} already exists, skipping."
else
    gcloud container clusters create "$GKE_CLUSTER" \
        --zone="$GKE_ZONE" \
        --num-nodes="$GKE_NODES" \
        --machine-type="$GKE_MACHINE" \
        --enable-autoscaling \
        --min-nodes=1 \
        --max-nodes="$GKE_NODES" \
        --scopes="https://www.googleapis.com/auth/devstorage.read_only"
fi

gcloud container clusters get-credentials "$GKE_CLUSTER" --zone="$GKE_ZONE"

echo "Cluster nodes:"
kubectl get nodes

# ─── Step 4: Patch manifests for cloud registry ──────────────────────

step 4 "Patch manifests for Artifact Registry images"

PATCHED_DIR="${PROJECT_ROOT}/manifests/gke-patched"
mkdir -p "$PATCHED_DIR"

for MANIFEST in "${PROJECT_ROOT}"/manifests/*-manual.yaml; do
    BASENAME=$(basename "$MANIFEST")
    PATCHED="${PATCHED_DIR}/${BASENAME}"

    cp "$MANIFEST" "$PATCHED"

    # Replace local image refs with GAR refs
    for IMG in "${FAVE_IMAGES[@]}"; do
        sed -i.bak "s|image: ${IMG}:dev|image: ${GAR_PREFIX}/${IMG}:dev|g" "$PATCHED"
    done

    # Switch pull policy to Always for cloud
    sed -i.bak 's|imagePullPolicy: IfNotPresent|imagePullPolicy: Always|g' "$PATCHED"

    rm -f "${PATCHED}.bak"
done

echo "Patched manifests written to ${PATCHED_DIR}/"

# ─── Step 5: Install OpenFaaS ────────────────────────────────────────

step 5 "Install OpenFaaS on GKE"

if kubectl get namespace openfaas &>/dev/null; then
    echo "OpenFaaS already installed, skipping."
else
    command -v arkade &>/dev/null || fail "arkade not found. Install: curl -sLS https://get.arkade.dev | sh"
    arkade install openfaas-ce
fi

kubectl rollout status deployment/gateway -n openfaas --timeout=5m

# ─── Step 6: Deploy MinIO ────────────────────────────────────────────

step 6 "Deploy MinIO"

kubectl apply -f "${PROJECT_ROOT}/manifests/minio-k8s.yaml"
kubectl rollout status deployment/minio -n default --timeout=2m

# ─── Step 7: Create secrets and deploy functions ─────────────────────

step 7 "Create secrets and deploy functions"

kubectl create namespace openfaas-fn 2>/dev/null || true

kubectl create secret generic artifact-access-key \
    --from-literal=artifact-access-key=faveadmin -n openfaas-fn \
    --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic artifact-secret-key \
    --from-literal=artifact-secret-key=favesecret -n openfaas-fn \
    --dry-run=client -o yaml | kubectl apply -f -

# Deploy patched manifests
kubectl apply -f "${PATCHED_DIR}/orchestrator-manual.yaml"
for f in "${PATCHED_DIR}"/stage-*-manual.yaml; do
    kubectl apply -f "$f"
done

# ─── Step 8: Enable HPA ──────────────────────────────────────────────

step 8 "Enable HPA (metrics-server is pre-installed on GKE)"

# Set initial replicas to 1
for deploy in $(kubectl get deployments -n openfaas-fn -o name); do
    kubectl scale -n openfaas-fn "$deploy" --replicas=1
done

kubectl apply -f "${PROJECT_ROOT}/manifests/hpa.yaml"

echo "Waiting for pods to be ready..."
kubectl wait --for=condition=available deployment --all -n openfaas-fn --timeout=5m

echo ""
echo "HPA status:"
kubectl get hpa -n openfaas-fn

# ─── Step 9: Port-forward gateway ────────────────────────────────────

step 9 "Port-forward gateway"

kubectl port-forward -n openfaas svc/gateway 8080:8080 &>/dev/null &
kubectl port-forward -n default svc/minio 9000:9000 &>/dev/null &
sleep 3

# ─── Done ─────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}${BOLD}=========================================="
echo "  FAVE GKE Setup Complete!"
echo "==========================================${NC}"
echo ""
echo -e "${BOLD}Cluster info:${NC}"
echo "  Nodes: $(kubectl get nodes --no-headers | wc -l)"
echo "  Pods:  $(kubectl get pods -n openfaas-fn --no-headers | wc -l)"
echo ""
echo -e "${BOLD}Run scaling experiment:${NC}"
echo "  ./scripts/run_scaling_experiment.sh --hpa --skip-ingest"
echo ""
echo -e "${BOLD}Monitor HPA:${NC}"
echo "  watch kubectl get hpa -n openfaas-fn"
echo ""
echo -e "${BOLD}Teardown (important to avoid charges!):${NC}"
echo "  ./scripts/teardown-gke.sh"
