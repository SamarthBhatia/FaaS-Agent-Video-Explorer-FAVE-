#!/bin/bash
#
# FAVE VM Fresh Setup + Experiment
# Run on a clean VM with MicroK8s + Docker already installed.
#
set -e

cd ~/FaaS-Agent-Video-Explorer-FAVE-

echo "=========================================="
echo "FAVE VM Fresh Setup"
echo "=========================================="

# ─── Step 1: Install OpenFaaS ────────────────────────────────────────
echo ""
echo "=== Step 1: Install OpenFaaS ==="
arkade install openfaas-ce
kubectl rollout status deployment/gateway -n openfaas --timeout=5m

# ─── Step 2: Deploy MinIO with persistent storage ─────────────────────
echo ""
echo "=== Step 2: Deploy MinIO (persistent storage) ==="
kubectl delete -f manifests/minio-k8s.yaml 2>/dev/null || true
kubectl apply -f manifests/minio-persistent.yaml
kubectl rollout status deployment/minio -n default --timeout=2m

# ─── Step 3: Create secrets ───────────────────────────────────────────
echo ""
echo "=== Step 3: Create secrets ==="
kubectl create namespace openfaas-fn 2>/dev/null || true
kubectl create secret generic artifact-access-key \
    --from-literal=artifact-access-key=faveadmin -n openfaas-fn \
    --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic artifact-secret-key \
    --from-literal=artifact-secret-key=favesecret -n openfaas-fn \
    --dry-run=client -o yaml | kubectl apply -f -

# ─── Step 4: Build and push images ───────────────────────────────────
echo ""
echo "=== Step 4: Build and push images ==="
docker build -t localhost:32000/k8s/fave-base:dev base-image
docker push localhost:32000/k8s/fave-base:dev

for FUNC in orchestrator stage-ffmpeg-0 stage-ffmpeg-1 stage-ffmpeg-2 stage-ffmpeg-3 stage-librosa stage-deepspeech stage-object-detector; do
    echo "Building k8s/fave-${FUNC}..."
    docker build --build-arg BASE_IMAGE=localhost:32000/k8s/fave-base:dev \
        -t localhost:32000/k8s/fave-${FUNC}:dev functions/${FUNC}
    docker push localhost:32000/k8s/fave-${FUNC}:dev
done

# ─── Step 5: Patch and deploy functions ───────────────────────────────
echo ""
echo "=== Step 5: Deploy functions ==="
mkdir -p manifests/vm-patched
for MANIFEST in manifests/*-manual.yaml; do
    BASENAME=$(basename "$MANIFEST")
    sed -e 's|image: fave-|image: localhost:32000/k8s/fave-|g' \
        -e 's|imagePullPolicy: IfNotPresent|imagePullPolicy: Always|g' \
        "$MANIFEST" > "manifests/vm-patched/${BASENAME}"
done

kubectl apply -f manifests/vm-patched/orchestrator-manual.yaml
for f in manifests/vm-patched/stage-*-manual.yaml; do kubectl apply -f "$f"; done
for deploy in $(kubectl get deployments -n openfaas-fn -o name); do
    kubectl scale -n openfaas-fn "$deploy" --replicas=1
done
kubectl wait --for=condition=available deployment --all -n openfaas-fn --timeout=10m

# ─── Step 6: Port-forward and ingest videos ───────────────────────────
echo ""
echo "=== Step 6: Ingest videos ==="
kill $(lsof -t -i:8080 2>/dev/null) 2>/dev/null || true
kill $(lsof -t -i:9000 2>/dev/null) 2>/dev/null || true
sleep 1
kubectl port-forward -n openfaas svc/gateway 8080:8080 &>/dev/null &
kubectl port-forward -n default svc/minio 9000:9000 &>/dev/null &
sleep 5

mc alias set fave-local http://127.0.0.1:9000 faveadmin favesecret
mc mb --ignore-existing fave-local/fave-artifacts
python3 scripts/auto_ingest_videos.py --limit 3

# Verify
mc ls fave-local/fave-artifacts/input/

# ─── Step 7: Apply HPA ───────────────────────────────────────────────
echo ""
echo "=== Step 7: Apply HPA ==="
cat > /tmp/hpa-vm.yaml <<'EOF'
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
EOF

kubectl apply -f /tmp/hpa-vm.yaml
echo "Waiting 60s for HPA metrics..."
sleep 60
kubectl get hpa -n openfaas-fn

# ─── Step 8: Warm-up run ─────────────────────────────────────────────
echo ""
echo "=== Step 8: Warm-up ==="
jmeter -n \
    -t jmeter/fave-load-test.jmx \
    -l /dev/null -j /dev/null \
    -JGATEWAY_URL=127.0.0.1 -JGATEWAY_PORT=8080 \
    -JThreadGroup.num_threads=1 -JThreadGroup.ramp_time=0 \
    -JLoopController.loops=1 2>/dev/null || true
echo "Warm-up done. Waiting 30s..."
sleep 30

# ─── Step 9: Run experiment with metrics ──────────────────────────────
echo ""
echo "=== Step 9: Run experiment (3 threads x 10 loops = 30 requests) ==="
mkdir -p experiments/metrics

./scripts/collect_metrics.sh 5 experiments/metrics &
COLLECTOR_PID=$!

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
JTL="experiments/jmeter/results_vm_long_${TIMESTAMP}.jtl"

jmeter -n \
    -t jmeter/fave-load-test.jmx \
    -l "$JTL" \
    -j "experiments/jmeter/jmeter_vm_long_${TIMESTAMP}.log" \
    -JGATEWAY_URL=127.0.0.1 -JGATEWAY_PORT=8080 \
    -JThreadGroup.num_threads=3 -JThreadGroup.ramp_time=30 \
    -JLoopController.loops=10

echo "Waiting 60s for HPA final state..."
sleep 60
kill $COLLECTOR_PID 2>/dev/null || true

# ─── Summary ──────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "DONE"
echo "=========================================="
echo ""
echo "JTL: $JTL"
TOTAL=$(tail -n +2 "$JTL" | wc -l | tr -d ' ')
SUCCESS=$(grep -c ",true," "$JTL" 2>/dev/null || echo 0)
echo "Results: ${SUCCESS}/${TOTAL} successful"
echo ""
echo "Metrics:"
ls -la experiments/metrics/*.csv | tail -2
echo ""
echo "HPA:"
kubectl get hpa -n openfaas-fn
echo ""
echo "Pods:"
kubectl get pods -n openfaas-fn --no-headers | wc -l
