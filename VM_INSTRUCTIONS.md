# FAVE VM Experiment Instructions

## Goal
Run JMeter load tests on the VM with K8s HPA autoscaling and collect 4 plots for the professor:
1. Throughput (JMeter) vs time
2. Total number of pods per function vs time
3. Response time vs time
4. CPU utilization per function vs time

## Current VM State
- **MicroK8s** is running with 8 function pods (1 replica each)
- **MinIO** has persistent storage with 3 videos already ingested
- **OpenFaaS** gateway is running
- **Prometheus** is scaled to 0 (saves resources)
- All function images are in local registry at `localhost:32000/k8s/fave-*:dev`
- HPA manifests are at `/tmp/hpa-vm.yaml`

## Network Details (ClusterIPs — no port-forwards needed for JMeter)
- Gateway: `10.152.183.246:8080`
- MinIO: `10.152.183.247:9000`
- For scripts that need `127.0.0.1:9000` (like auto_ingest_videos.py), start: `kubectl port-forward -n default svc/minio 9000:9000 &`

## Step-by-Step Experiment

### 1. Verify everything is running
```bash
kubectl get pods -n openfaas-fn
curl -s http://10.152.183.246:8080/healthz && echo " gateway OK"
```
All 8 pods should be Running. If not, scale up:
```bash
for deploy in $(kubectl get deployments -n openfaas-fn -o name); do kubectl scale -n openfaas-fn "$deploy" --replicas=1; done
kubectl wait --for=condition=available deployment --all -n openfaas-fn --timeout=5m
```

### 2. Verify MinIO has videos
```bash
mc alias set fave-local http://10.152.183.247:9000 faveadmin favesecret
mc ls fave-local/fave-artifacts/input/
```
Should show 3 videos. If not, re-ingest:
```bash
kubectl port-forward -n default svc/minio 9000:9000 &
sleep 2
mc mb --ignore-existing fave-local/fave-artifacts
python3 scripts/auto_ingest_videos.py --limit 3
```

### 3. Test pipeline manually
```bash
curl -s -X POST http://10.152.183.246:8080/function/orchestrator -H "Content-Type: application/json" -d '{"video_uri": "s3://fave-artifacts/input/classroom.mp4", "profile": "test"}' | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['status'])"
```
Must print `ok`. If it prints `error`, check MinIO bucket exists.

### 4. Apply HPA
```bash
kubectl apply -f /tmp/hpa-vm.yaml
sleep 60
kubectl get hpa -n openfaas-fn
```
All targets should show `cpu: X%/60%` (not `<unknown>`). Max replicas is 3 per function (VM resource limit).

### 5. Start metrics collector
```bash
mkdir -p experiments/metrics
./scripts/collect_metrics.sh 5 experiments/metrics &
COLLECTOR_PID=$!
```

### 6. Run JMeter test
**IMPORTANT**: Use ClusterIP `10.152.183.246` not `127.0.0.1` for the gateway.
```bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
jmeter -n \
    -t jmeter/fave-load-test.jmx \
    -l "experiments/jmeter/results_vm_long_${TIMESTAMP}.jtl" \
    -j "experiments/jmeter/jmeter_vm_long_${TIMESTAMP}.log" \
    -JGATEWAY_URL=10.152.183.246 \
    -JGATEWAY_PORT=8080 \
    -JThreadGroup.num_threads=2 \
    -JThreadGroup.ramp_time=10 \
    -JLoopController.loops=10
```
This sends 20 requests (2 threads x 10 loops). Should get >80% success rate.

### 7. Wait for HPA scaling and stop collector
```bash
sleep 60
kill $COLLECTOR_PID 2>/dev/null
```

### 8. Check results
```bash
TOTAL=$(tail -n +2 "experiments/jmeter/results_vm_long_${TIMESTAMP}.jtl" | wc -l | tr -d ' ')
SUCCESS=$(grep -c ",true," "experiments/jmeter/results_vm_long_${TIMESTAMP}.jtl" 2>/dev/null || echo 0)
echo "Results: ${SUCCESS}/${TOTAL} successful"
kubectl get hpa -n openfaas-fn
kubectl get pods -n openfaas-fn --no-headers | wc -l
```

### 9. Copy files to local machine (run on LOCAL Mac, not VM)
```bash
scp "vm-k8s:~/FaaS-Agent-Video-Explorer-FAVE-/experiments/jmeter/results_vm_long_TIMESTAMP.jtl" experiments/jmeter/
scp "vm-k8s:~/FaaS-Agent-Video-Explorer-FAVE-/experiments/metrics/cpu_util_TIMESTAMP.csv" experiments/metrics/
scp "vm-k8s:~/FaaS-Agent-Video-Explorer-FAVE-/experiments/metrics/pod_counts_TIMESTAMP.csv" experiments/metrics/
```
Replace TIMESTAMP with actual value.

### 10. Generate plots (run on LOCAL Mac)
```bash
python3 scripts/generate_scaling_plots.py \
    --jtl experiments/jmeter/results_vm_long_TIMESTAMP.jtl \
    --pod-counts experiments/metrics/pod_counts_TIMESTAMP.csv \
    --cpu-util experiments/metrics/cpu_util_TIMESTAMP.csv \
    --output experiments/reports/prof
```

### 11. Generate JMeter dashboard (run on LOCAL Mac)
```bash
jmeter -g experiments/jmeter/results_vm_long_TIMESTAMP.jtl -o experiments/jmeter-dashboard/vm-final
open experiments/jmeter-dashboard/vm-final/index.html
```

## Troubleshooting

### Gateway is DOWN
```bash
kubectl get pods -n openfaas | grep gateway
kubectl rollout restart deployment/gateway -n openfaas
kubectl rollout status deployment/gateway -n openfaas --timeout=3m
```

### Pods are Evicted
VM ran out of resources. Clean up:
```bash
kubectl delete pods --all-namespaces --field-selector=status.phase=Failed
kubectl delete pods --all-namespaces --field-selector=status.phase=Succeeded
kubectl scale deployment prometheus -n openfaas --replicas=0
```

### MinIO bucket missing
```bash
mc alias set fave-local http://10.152.183.247:9000 faveadmin favesecret
mc mb --ignore-existing fave-local/fave-artifacts
kubectl port-forward -n default svc/minio 9000:9000 &
sleep 2
python3 scripts/auto_ingest_videos.py --limit 3
```

### JMeter shows 0ms responses / connection refused
Gateway IP may have changed. Re-check:
```bash
kubectl get svc -n openfaas gateway -o jsonpath='{.spec.clusterIP}' && echo ""
```
Use the new IP in the `-JGATEWAY_URL=` parameter.

### Too many errors during test
- Scale down HPA: `kubectl delete hpa --all -n openfaas-fn`
- Reset pods: scale to 0 then back to 1
- Use fewer threads (1-2) and fewer loops (5-10)
- The VM is a single node with limited resources — concurrent load causes contention

## VM Connection
```bash
ssh vm-k8s
# Passwords: gatehwayd2025-73, gatehwayd2025-73, [your password]
screen -r 517267.fave
cd ~/FaaS-Agent-Video-Explorer-FAVE-
```

## Clean Shutdown (before disconnecting)
```bash
kubectl delete hpa --all -n openfaas-fn
for deploy in $(kubectl get deployments -n openfaas-fn -o name); do kubectl scale -n openfaas-fn "$deploy" --replicas=0; done
# Ctrl+A then D to detach screen
# exit exit exit to disconnect SSH
```
