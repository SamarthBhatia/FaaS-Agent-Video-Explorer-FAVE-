#!/bin/bash
#
# FAVE Project — Teardown Script
#
# Removes all FAVE resources from the cluster.
#
# Usage:
#   ./teardown.sh
#

set -e

echo "FAVE Teardown"
echo "=========================================="

# Stop port-forwards
echo "Stopping port-forwards..."
for PORT in 8080 9000 9090 3000; do
    lsof -i :$PORT -t 2>/dev/null | xargs kill -9 2>/dev/null || true
done

# Delete function deployments
echo "Deleting function deployments..."
kubectl delete -f manifests/orchestrator-manual.yaml 2>/dev/null || true
for f in manifests/stage-*-manual.yaml; do kubectl delete -f "$f" 2>/dev/null || true; done

# Delete Grafana
echo "Deleting Grafana..."
kubectl delete -f manifests/grafana.yaml 2>/dev/null || true

# Delete MinIO
echo "Deleting MinIO..."
kubectl delete -f manifests/minio-k8s.yaml 2>/dev/null || true

# Delete OpenFaaS namespaces (removes Prometheus too)
echo "Deleting OpenFaaS..."
kubectl delete namespace openfaas 2>/dev/null || true
kubectl delete namespace openfaas-fn 2>/dev/null || true

echo ""
echo "Teardown complete."
echo ""
echo "(Optional) Disable Kubernetes entirely:"
echo "  Docker Desktop → Settings → Kubernetes → Uncheck 'Enable Kubernetes'"
