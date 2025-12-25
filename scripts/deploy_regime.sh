#!/usr/bin/env bash
set -euo pipefail

REGIME=${1:-cold}

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
  *)
    echo "Unknown regime: ${REGIME}"
    exit 1
    ;;
esac

echo "Deploying regime: ${REGIME} (min=${MIN_REPLICAS}, max=${MAX_REPLICAS})"

# Note: Since we are using manual manifests to bypass CE restrictions,
# we update the deployments directly via kubectl.

for deploy in $(kubectl get deployments -n openfaas-fn -o name); do
    echo "Patching $deploy"
    # We use min replicas as the target for now since CE doesn't have a built-in autoscaler
    # that we can easily trigger without the Pro features or external setup.
    # In a real OpenFaaS install, the autoscaler would use labels.
    kubectl scale -n openfaas-fn "$deploy" --replicas=${MIN_REPLICAS}
done

echo "Regime ${REGIME} applied."