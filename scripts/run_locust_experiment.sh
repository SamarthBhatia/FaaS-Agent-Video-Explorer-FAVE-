#!/bin/bash
#
# FAVE Locust Experiment — Sinusoidal workload with HPA (max 6 replicas)
# Adapted from Samuele's thesis workload generator
#
# Usage: ./scripts/run_locust_experiment.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

DURATION=${1:-3600}

echo "=========================================="
echo "FAVE Locust Experiment (${DURATION}s)"
echo "=========================================="

# Step 1: Clean up
echo ""
echo "=== Step 1: Clean up ==="
kubectl delete hpa --all -n openfaas-fn 2>/dev/null || true
for deploy in $(kubectl get deployments -n openfaas-fn -o name); do
    kubectl scale -n openfaas-fn "$deploy" --replicas=1
done

echo "Waiting for pods to be ready..."
kubectl wait --for=condition=available deployment --all -n openfaas-fn --timeout=5m

# Step 2: Port-forwards
echo ""
echo "=== Step 2: Port-forwards ==="
kill $(lsof -t -i:8080 2>/dev/null) 2>/dev/null || true
kill $(lsof -t -i:9000 2>/dev/null) 2>/dev/null || true
sleep 1
kubectl port-forward -n openfaas svc/gateway 8080:8080 &>/dev/null &
kubectl port-forward -n default svc/minio 9000:9000 &>/dev/null &
sleep 3

if curl -s http://127.0.0.1:8080/healthz > /dev/null 2>&1; then
    echo "Gateway: OK"
else
    echo "Gateway: FAILED - aborting"
    exit 1
fi

# Step 3: Apply HPA (max 6 replicas per professor's instruction)
echo ""
echo "=== Step 3: Apply HPA (max 6 replicas) ==="
cat > /tmp/hpa-locust.yaml << 'HPAEOF'
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
  maxReplicas: 6
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
  name: hpa-stage-ffmpeg-1
  namespace: openfaas-fn
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: stage-ffmpeg-1
  minReplicas: 1
  maxReplicas: 6
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
  name: hpa-stage-ffmpeg-2
  namespace: openfaas-fn
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: stage-ffmpeg-2
  minReplicas: 1
  maxReplicas: 6
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
  maxReplicas: 6
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
  maxReplicas: 6
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
  maxReplicas: 6
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
  maxReplicas: 6
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
HPAEOF

kubectl apply -f /tmp/hpa-locust.yaml

echo "Waiting 60s for metrics-server to populate HPA targets..."
sleep 60

echo "HPA status:"
kubectl get hpa -n openfaas-fn

# Step 4: Start metrics collector
echo ""
echo "=== Step 4: Start metrics collector ==="
mkdir -p experiments/metrics
./scripts/collect_metrics.sh 6 experiments/metrics &
COLLECTOR_PID=$!
echo "Collector PID: $COLLECTOR_PID"
sleep 5

# Step 5: Warm-up
echo ""
echo "=== Step 5: Warm-up request ==="
curl -s -X POST http://127.0.0.1:8080/function/orchestrator \
    -H "Content-Type: application/json" \
    -d '{"video_uri": "s3://fave-artifacts/input/classroom.mp4", "profile": "locust-warm"}' \
    --max-time 300 > /dev/null 2>&1 || echo "Warm-up failed (non-critical)"
echo "Warm-up done, waiting 30s..."
sleep 30

# Step 6: Run Locust experiment
echo ""
echo "=== Step 6: Running Locust experiment (${DURATION}s) ==="
mkdir -p experiments/locust
python3 locust/locust_fave.py \
    --gateway http://127.0.0.1:8080 \
    --duration "$DURATION" \
    --output experiments/locust \
    --videos-csv datasets/jmeter_videos.csv \
    --seed 22222121

# Step 7: Wait for HPA scale-down
echo ""
echo "=== Step 7: Waiting 120s for HPA scale-down metrics ==="
sleep 120

# Step 8: Stop collector
echo ""
echo "=== Step 8: Stop metrics collector ==="
kill $COLLECTOR_PID 2>/dev/null || true
sleep 2

# Step 9: Summary
echo ""
echo "=========================================="
echo "Experiment complete!"
echo "=========================================="
echo ""
echo "Locust results:"
ls -la experiments/locust/results_locust_*.jtl 2>/dev/null
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
echo "  scp vm-k8s:~/FaaS-Agent-Video-Explorer-FAVE-/experiments/locust/*.csv experiments/locust/"
echo "  scp vm-k8s:~/FaaS-Agent-Video-Explorer-FAVE-/experiments/metrics/*.csv experiments/metrics/"
