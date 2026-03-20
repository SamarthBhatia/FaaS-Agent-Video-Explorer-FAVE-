#!/bin/bash
#
# FAVE VM Experiment — Full run with metrics collection
# Generates data for all 4 professor-requested plots
#
# Usage: ./scripts/run_vm_experiment.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=========================================="
echo "FAVE VM Experiment"
echo "=========================================="

# Step 1: Clean up any existing HPAs
echo ""
echo "=== Step 1: Clean up ==="
kubectl delete hpa --all -n openfaas-fn 2>/dev/null || true
for deploy in $(kubectl get deployments -n openfaas-fn -o name); do
    kubectl scale -n openfaas-fn "$deploy" --replicas=1
done

echo "Waiting for pods to be ready..."
kubectl wait --for=condition=available deployment --all -n openfaas-fn --timeout=5m

# Step 2: Ensure port-forwards are alive
echo ""
echo "=== Step 2: Port-forwards ==="
# Kill stale port-forwards
kill $(lsof -t -i:8080 2>/dev/null) 2>/dev/null || true
kill $(lsof -t -i:9000 2>/dev/null) 2>/dev/null || true
sleep 1
kubectl port-forward -n openfaas svc/gateway 8080:8080 &>/dev/null &
kubectl port-forward -n default svc/minio 9000:9000 &>/dev/null &
sleep 3

# Verify gateway
if curl -s http://127.0.0.1:8080/healthz > /dev/null 2>&1; then
    echo "Gateway: OK"
else
    echo "Gateway: FAILED - aborting"
    exit 1
fi

# Step 3: Create VM-appropriate HPA (max 3 replicas)
echo ""
echo "=== Step 3: Apply HPA (max 3 replicas) ==="
cat > /tmp/hpa-vm.yaml << 'HPAEOF'
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: hpa-stage-ffmpeg-0
  namespace: openfaas-fn
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: stage-ffmpeg-0
  minReplicas: 1
  maxReplicas: 3
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: hpa-stage-librosa
  namespace: openfaas-fn
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: stage-librosa
  minReplicas: 1
  maxReplicas: 3
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: hpa-stage-object-detector
  namespace: openfaas-fn
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: stage-object-detector
  minReplicas: 1
  maxReplicas: 3
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: hpa-stage-ffmpeg-3
  namespace: openfaas-fn
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: stage-ffmpeg-3
  minReplicas: 1
  maxReplicas: 3
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: hpa-stage-deepspeech
  namespace: openfaas-fn
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: stage-deepspeech
  minReplicas: 1
  maxReplicas: 3
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
HPAEOF

kubectl apply -f /tmp/hpa-vm.yaml

echo "Waiting 60s for metrics-server to populate HPA targets..."
sleep 60

echo "HPA status:"
kubectl get hpa -n openfaas-fn

# Step 4: Start metrics collector
echo ""
echo "=== Step 4: Start metrics collector ==="
mkdir -p experiments/metrics
./scripts/collect_metrics.sh 5 experiments/metrics &
COLLECTOR_PID=$!
echo "Collector PID: $COLLECTOR_PID"
sleep 5

# Step 5: Run JMeter tests
echo ""
echo "=== Step 5: Running JMeter tests ==="

# Warm-up run (1 thread, 1 loop) to prime the pipeline
echo "--- Warm-up run ---"
jmeter -n \
    -t jmeter/fave-load-test.jmx \
    -l /dev/null \
    -j /dev/null \
    -JGATEWAY_URL=127.0.0.1 \
    -JGATEWAY_PORT=8080 \
    -JThreadGroup.num_threads=1 \
    -JThreadGroup.ramp_time=0 \
    -JLoopController.loops=1 2>/dev/null || true
echo "Warm-up complete, waiting 30s..."
sleep 30

# Main test: 5 threads x 3 loops = 15 requests
echo "--- Main test: 5 threads x 3 loops ---"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_FILE="experiments/jmeter/results_vm_main_${TIMESTAMP}.jtl"
LOG_FILE="experiments/jmeter/jmeter_vm_main_${TIMESTAMP}.log"

jmeter -n \
    -t jmeter/fave-load-test.jmx \
    -l "$RESULTS_FILE" \
    -j "$LOG_FILE" \
    -JGATEWAY_URL=127.0.0.1 \
    -JGATEWAY_PORT=8080 \
    -JThreadGroup.num_threads=5 \
    -JThreadGroup.ramp_time=5 \
    -JLoopController.loops=3

echo ""
echo "Results: $RESULTS_FILE"

# Wait a bit for HPA to react, keep collecting
echo "Waiting 60s for HPA scaling to stabilize..."
sleep 60

# Step 6: Stop collector
echo ""
echo "=== Step 6: Stop metrics collector ==="
kill $COLLECTOR_PID 2>/dev/null || true
sleep 2

# Step 7: Summary
echo ""
echo "=========================================="
echo "Experiment complete!"
echo "=========================================="
echo ""
echo "JTL results:"
ls -la experiments/jmeter/results_vm_main_*.jtl 2>/dev/null
echo ""
echo "Metrics:"
ls -la experiments/metrics/*.csv 2>/dev/null
echo ""
echo "HPA final state:"
kubectl get hpa -n openfaas-fn
echo ""
echo "Pod counts:"
kubectl get pods -n openfaas-fn --no-headers | wc -l
echo ""
echo "Next: copy files to local machine and generate plots"
