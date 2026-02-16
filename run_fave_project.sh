#!/bin/bash

# Clean up from previous runs
echo "Cleaning up previous OpenFaaS and MinIO installations..."
kubectl delete namespace openfaas openfaas-fn || true
rm -rf functions/dummy-orchestrator || true # Remove dummy orchestrator files if they exist

# Build Base Image
echo "Building base Docker image..."
./scripts/build-base-image.sh

# Install OpenFaaS & MinIO
echo "Installing OpenFaaS and MinIO..."
arkade install openfaas-ce
kubectl apply -f manifests/minio-k8s.yaml

# Wait for core OpenFaaS components to be ready
echo "Waiting for OpenFaaS core components to be ready..."
kubectl rollout status deployment/gateway -n openfaas --timeout=5m
kubectl rollout status deployment/prometheus -n openfaas --timeout=5m
kubectl rollout status deployment/nats -n openfaas --timeout=5m
kubectl rollout status deployment/queue-worker -n openfaas --timeout=5m

# Port-forward the gateway in the background
echo "Starting OpenFaaS gateway port-forward (PID will be stored in GATEWAY_PID)..."
kubectl port-forward -n openfaas svc/gateway 8080:8080 &
GATEWAY_PID=$!
sleep 5 # Give it a moment to establish

# Configure Credentials
echo "Configuring Kubernetes secrets for MinIO access..."
kubectl create namespace openfaas-fn || true
kubectl create secret generic artifact-access-key \
  --from-literal=artifact-access-key=faveadmin -n openfaas-fn
kubectl create secret generic artifact-secret-key \
  --from-literal=artifact-secret-key=favesecret -n openfaas-fn

# Login to OpenFaaS via the port-forward
echo "Logging into OpenFaaS CLI..."
PASSWORD=$(kubectl get secret -n openfaas basic-auth -o jsonpath="{.data.basic-auth-password}" | base64 --decode; echo)
echo -n "$PASSWORD" | faas-cli login --username admin --password-stdin --gateway http://127.0.0.1:8080

# Build Functions
echo "Building OpenFaaS function images..."
faas-cli build -f functions/stack.yml

# Deploy Functions using manual manifests
echo "Deploying OpenFaaS functions using manual manifests..."
kubectl apply -f manifests/orchestrator-manual.yaml
for f in manifests/stage-*-manual.yaml; do kubectl apply -f "$f"; done

# Wait for function deployments to be ready
echo "Waiting for all function deployments to be ready..."
kubectl rollout status deployment/orchestrator -n openfaas-fn --timeout=5m
kubectl rollout status deployment/stage-deepspeech -n openfaas-fn --timeout=5m
kubectl rollout status deployment/stage-ffmpeg-0 -n openfaas-fn --timeout=5m
kubectl rollout status deployment/stage-ffmpeg-1 -n openfaas-fn --timeout=5m
kubectl rollout status deployment/stage-ffmpeg-2 -n openfaas-fn --timeout=5m
kubectl rollout status deployment/stage-ffmpeg-3 -n openfaas-fn --timeout=5m
kubectl rollout status deployment/stage-librosa -n openfaas-fn --timeout=5m
kubectl rollout status deployment/stage-object-detector -n openfaas-fn --timeout=5m

# Run a Smoke Test
echo "Setting up MinIO for the smoke test..."
# Port-Forward MinIO (run in background, then sleep to allow it to establish)
echo "Starting MinIO port-forward (PID will be stored in MINIO_PID)..."
kubectl port-forward -n default svc/minio 9000:9000 &
MINIO_PID=$!
sleep 5

# Create Bucket & Upload Video
echo "Creating MinIO bucket and uploading sample video..."

mc alias set fave-local http://127.0.0.1:9000 faveadmin favesecret
mc mb --ignore-existing fave-local/fave-artifacts
curl -L -o sample.mp4 https://github.com/intel-iot-devkit/sample-videos/raw/master/classroom.mp4
mc cp sample.mp4 fave-local/fave-artifacts/input/sample.mp4

# Trigger the Pipeline
echo "Triggering the video processing pipeline (smoke test)..."
python3 scripts/workload_generator.py \
  --gateway http://127.0.0.1:8080 \
  --video s3://fave-artifacts/input/sample.mp4 \
  --pattern steady --requests 1 --rps 1

# Killing the port-forward processes
echo "Cleaning up background port-forward processes..."
kill "$GATEWAY_PID" || true
kill "$MINIO_PID" || true

echo "FAVE project setup and smoke test completed successfully!"
