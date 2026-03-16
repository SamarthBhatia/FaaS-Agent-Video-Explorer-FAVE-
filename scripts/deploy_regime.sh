#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

REGIME=${1:-cold}

ensure_metrics_server() {
    if kubectl get deployment metrics-server -n kube-system &>/dev/null; then
        echo "metrics-server already installed."
        return
    fi
    echo "Installing metrics-server..."
    kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

    # On Docker Desktop, metrics-server needs --kubelet-insecure-tls
    kubectl patch deployment metrics-server -n kube-system \
        --type='json' \
        -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--kubelet-insecure-tls"}]' \
        2>/dev/null || true

    echo "Waiting for metrics-server to be ready..."
    kubectl rollout status deployment/metrics-server -n kube-system --timeout=2m
}

case ${REGIME} in
  cold)
    MIN_REPLICAS=0
    MAX_REPLICAS=5
    ;;
  warm)
    MIN_REPLICAS=1
    MAX_REPLICAS=5
    ;;
  burst-ready)
    MIN_REPLICAS=3
    MAX_REPLICAS=10
    ;;
  hpa)
    MIN_REPLICAS=1
    MAX_REPLICAS=10
    ;;
  *)
    echo "Unknown regime: ${REGIME}"
    echo "Usage: $0 {cold|warm|burst-ready|hpa}"
    exit 1
    ;;
esac

echo "Deploying regime: ${REGIME} (min=${MIN_REPLICAS}, max=${MAX_REPLICAS})"

for deploy in $(kubectl get deployments -n openfaas-fn -o name); do
    echo "Patching $deploy"
    kubectl scale -n openfaas-fn "$deploy" --replicas=${MIN_REPLICAS}
done

if [ "${REGIME}" = "hpa" ]; then
    ensure_metrics_server
    echo "Applying HPA manifests..."
    kubectl apply -f "${PROJECT_ROOT}/manifests/hpa.yaml"
    echo ""
    echo "HPA status:"
    kubectl get hpa -n openfaas-fn
fi

echo "Regime ${REGIME} applied."
