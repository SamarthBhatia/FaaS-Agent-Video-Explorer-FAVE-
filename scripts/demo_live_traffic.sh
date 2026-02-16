#!/bin/bash
# FAVE Live Demo Traffic Generator
# Run this during your presentation to show live metrics in Grafana

set -e

VIDEO="${1:-s3://fave-artifacts/input/classroom.mp4}"
GATEWAY="http://localhost:8080"

echo "=============================================="
echo "FAVE Live Demo Traffic Generator"
echo "=============================================="
echo ""
echo "Grafana Dashboard: http://localhost:3000/d/fave-pipeline"
echo "Video: $VIDEO"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Ensure gateway is accessible
if ! curl -s "$GATEWAY/healthz" > /dev/null 2>&1; then
    echo "ERROR: Gateway not accessible at $GATEWAY"
    echo "Run: kubectl port-forward -n openfaas svc/gateway 8080:8080"
    exit 1
fi

request_count=0

while true; do
    request_count=$((request_count + 1))
    timestamp=$(date '+%H:%M:%S')

    echo "[$timestamp] Sending request #$request_count..."

    # Send request and capture timing (use curl's built-in timing)
    response=$(curl -s -w "\n%{http_code}\n%{time_total}" -X POST "$GATEWAY/function/orchestrator" \
        -H "Content-Type: application/json" \
        -d "{\"video_uri\": \"$VIDEO\"}" 2>&1)

    http_code=$(echo "$response" | tail -2 | head -1)
    time_total=$(echo "$response" | tail -1)
    body=$(echo "$response" | sed -e '$d' -e '$d')

    # Convert seconds to milliseconds
    duration=$(echo "$time_total * 1000" | bc | cut -d. -f1)

    if [ "$http_code" = "200" ]; then
        status=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "ok")
        echo "[$timestamp] ✓ Request #$request_count completed in ${duration}ms (status: $status)"
    else
        echo "[$timestamp] ✗ Request #$request_count failed with HTTP $http_code"
    fi

    # Wait before next request (random 5-15 seconds for realistic traffic)
    sleep_time=$((5 + RANDOM % 10))
    echo "[$timestamp] Waiting ${sleep_time}s before next request..."
    echo ""
    sleep $sleep_time
done
