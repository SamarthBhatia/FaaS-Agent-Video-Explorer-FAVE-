#!/bin/bash
set -e

# Usage: ./scripts/test_custom_video.sh <VIDEO_URL_OR_PATH> [warm|cold]
# Example: ./scripts/test_custom_video.sh https://example.com/video.mp4 cold

VIDEO_SOURCE=$1
MODE=${2:-cold} # Default to cold

if [ -z "$VIDEO_SOURCE" ]; then
    echo "Usage: $0 <VIDEO_URL_OR_PATH> [warm|cold]"
    echo "Example: $0 https://github.com/intel-iot-devkit/sample-videos/raw/master/face-demographics-walking-and-pause.mp4 cold"
    exit 1
fi

FILENAME=$(basename "$VIDEO_SOURCE")
# Ensure filename has extension, otherwise defaulting to .mp4 for safety
if [[ "$FILENAME" != *.* ]]; then
    FILENAME="${FILENAME}.mp4"
fi

echo "=== FAVE Custom Video Tester ==="
echo "Target Video: $FILENAME"
echo "Mode: $MODE"

# 1. Setup Network Access (Port Forwards)
echo ">>> Establishing network tunnels to Cluster..."
kubectl port-forward -n openfaas svc/gateway 8080:8080 > /dev/null 2>&1 &
GATEWAY_PID=$!
kubectl port-forward -n default svc/minio 9000:9000 > /dev/null 2>&1 &
MINIO_PID=$!

cleanup() {
    echo ">>> Cleaning up network tunnels..."
    kill $GATEWAY_PID 2>/dev/null || true
    kill $MINIO_PID 2>/dev/null || true
}
trap cleanup EXIT

# Wait for ports to be open
echo ">>> Waiting for connections..."
sleep 5

# 2. Prepare Video
echo ">>> Preparing video..."
if [[ "$VIDEO_SOURCE" == http* ]]; then
    echo "Downloading from URL..."
    curl -L -o "$FILENAME" "$VIDEO_SOURCE"
else
    if [ ! -f "$VIDEO_SOURCE" ]; then
        echo "Error: Local file $VIDEO_SOURCE not found."
        exit 1
    fi
    # Only copy if source and destination are different
    if [ "$VIDEO_SOURCE" != "$FILENAME" ]; then
        cp "$VIDEO_SOURCE" "$FILENAME"
    fi
fi

# 3. Upload to MinIO
echo ">>> Uploading to MinIO Storage..."
# Configure mc (MinIO Client) - assuming default credentials from project setup
mc alias set fave-local http://127.0.0.1:9000 faveadmin favesecret > /dev/null
# Ensure bucket exists
mc mb --ignore-existing fave-local/fave-artifacts > /dev/null
# Copy video
mc cp "$FILENAME" "fave-local/fave-artifacts/input/$FILENAME"

# 4. Trigger Workload
echo ">>> Triggering Pipeline..."
echo "Video URI: s3://fave-artifacts/input/$FILENAME"

if [ "$MODE" == "warm" ]; then
    echo "--- WARM MODE SELECTED ---"
    echo "Sending a pre-warming request first..."
    python3 scripts/workload_generator.py \
        --gateway http://127.0.0.1:8080 \
        --video "s3://fave-artifacts/input/$FILENAME" \
        --pattern steady --requests 1 --rps 1 > /dev/null
    echo "Warm-up complete. Running measured test..."
fi

# Run the actual test
python3 scripts/workload_generator.py \
    --gateway http://127.0.0.1:8080 \
    --video "s3://fave-artifacts/input/$FILENAME" \
    --pattern steady --requests 1 --rps 1

echo ">>> Test Complete!"
# Cleanup of downloaded file if it was a URL
if [[ "$VIDEO_SOURCE" == http* ]]; then
    rm "$FILENAME"
fi
