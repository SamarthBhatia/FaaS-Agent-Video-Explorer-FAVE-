#!/bin/bash
#
# FAVE Project — GKE Cluster Teardown
#
# Deletes the GKE cluster and Artifact Registry to stop billing.
#
# Usage:
#   export GCP_PROJECT=your-project-id
#   ./scripts/teardown-gke.sh
#

set -e

RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

GCP_PROJECT="${GCP_PROJECT:-}"
GKE_CLUSTER="${GKE_CLUSTER:-fave-cluster}"
GKE_ZONE="${GKE_ZONE:-us-central1-a}"
GAR_LOCATION="${GAR_LOCATION:-us-central1}"
GAR_REPO="${GAR_REPO:-fave}"

if [ -z "$GCP_PROJECT" ]; then
    echo -e "${RED}ERROR: GCP_PROJECT not set.${NC}"
    exit 1
fi

gcloud config set project "$GCP_PROJECT"

echo -e "${BOLD}FAVE GKE Teardown${NC}"
echo "=========================================="
echo "Project:  ${GCP_PROJECT}"
echo "Cluster:  ${GKE_CLUSTER} (${GKE_ZONE})"
echo "Registry: ${GAR_LOCATION}/${GAR_REPO}"
echo "=========================================="
echo ""

read -p "This will DELETE the cluster and registry. Continue? (y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo "Deleting GKE cluster..."
gcloud container clusters delete "$GKE_CLUSTER" \
    --zone="$GKE_ZONE" \
    --quiet || echo "Cluster not found or already deleted."

echo "Deleting Artifact Registry..."
gcloud artifacts repositories delete "$GAR_REPO" \
    --location="$GAR_LOCATION" \
    --quiet || echo "Repository not found or already deleted."

# Clean up patched manifests
rm -rf "$(dirname "${BASH_SOURCE[0]}")/../manifests/gke-patched"

echo ""
echo "Teardown complete. Switch kubectl back to local:"
echo "  kubectl config use-context docker-desktop"
