#!/bin/bash
#
# Collects K8s metrics at regular intervals during an experiment.
# Outputs CSV files for pod counts, CPU utilization, and pod states.
#
# Usage:
#   ./scripts/collect_metrics.sh &          # Start in background
#   COLLECTOR_PID=$!
#   # ... run experiment ...
#   kill $COLLECTOR_PID                      # Stop collection
#

INTERVAL=${1:-5}
OUTPUT_DIR="${2:-experiments/metrics}"
mkdir -p "$OUTPUT_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
POD_COUNT_FILE="${OUTPUT_DIR}/pod_counts_${TIMESTAMP}.csv"
CPU_UTIL_FILE="${OUTPUT_DIR}/cpu_util_${TIMESTAMP}.csv"

echo "timestamp,function,replicas,ready,pods_running,pods_pending" > "$POD_COUNT_FILE"
echo "timestamp,pod,function,cpu_millicores,memory_mib" > "$CPU_UTIL_FILE"

echo "Metrics collector started (interval=${INTERVAL}s)"
echo "  Pod counts: ${POD_COUNT_FILE}"
echo "  CPU util:   ${CPU_UTIL_FILE}"

while true; do
    NOW=$(date +%s)

    # Pod counts per deployment
    kubectl get deployments -n openfaas-fn --no-headers 2>/dev/null | while read -r line; do
        NAME=$(echo "$line" | awk '{print $1}')
        READY=$(echo "$line" | awk '{print $2}')
        READY_COUNT=$(echo "$READY" | cut -d/ -f1)
        DESIRED=$(echo "$READY" | cut -d/ -f2)
        RUNNING=$(kubectl get pods -n openfaas-fn -l app="$NAME" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
        PENDING=$(kubectl get pods -n openfaas-fn -l app="$NAME" --field-selector=status.phase=Pending --no-headers 2>/dev/null | wc -l | tr -d ' ')
        echo "${NOW},${NAME},${DESIRED},${READY_COUNT},${RUNNING},${PENDING}" >> "$POD_COUNT_FILE"
    done

    # CPU utilization per pod
    kubectl top pods -n openfaas-fn --no-headers 2>/dev/null | while read -r line; do
        POD=$(echo "$line" | awk '{print $1}')
        CPU=$(echo "$line" | awk '{print $2}' | sed 's/m//')
        MEM=$(echo "$line" | awk '{print $3}' | sed 's/Mi//')
        # Extract function name from pod name (remove hash suffixes)
        FUNC=$(echo "$POD" | sed 's/-[a-z0-9]*-[a-z0-9]*$//')
        echo "${NOW},${POD},${FUNC},${CPU},${MEM}" >> "$CPU_UTIL_FILE"
    done

    sleep "$INTERVAL"
done
