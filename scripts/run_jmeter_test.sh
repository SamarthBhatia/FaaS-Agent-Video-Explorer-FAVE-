#!/bin/bash
#
# FAVE JMeter Load Test Runner
#
# Prerequisites:
#   brew install jmeter
#
# Usage:
#   ./scripts/run_jmeter_test.sh              # Run default warm test
#   ./scripts/run_jmeter_test.sh --cold       # Run cold burst test
#   ./scripts/run_jmeter_test.sh --threads 10 # Custom thread count
#   ./scripts/run_jmeter_test.sh --gui        # Open JMeter GUI
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
JMETER_PLAN="${PROJECT_ROOT}/jmeter/fave-load-test.jmx"
RESULTS_DIR="${PROJECT_ROOT}/experiments/jmeter"
DATASETS_DIR="${PROJECT_ROOT}/datasets"

# Default values
THREADS=5
RAMP_TIME=5
LOOPS=1
GATEWAY_URL="127.0.0.1"
GATEWAY_PORT="8080"
TEST_MODE="warm"
GUI_MODE=false
INGEST_VIDEOS=true

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --threads)
            THREADS="$2"
            shift 2
            ;;
        --ramp)
            RAMP_TIME="$2"
            shift 2
            ;;
        --loops)
            LOOPS="$2"
            shift 2
            ;;
        --gateway)
            GATEWAY_URL="$2"
            shift 2
            ;;
        --port)
            GATEWAY_PORT="$2"
            shift 2
            ;;
        --cold)
            TEST_MODE="cold"
            RAMP_TIME=0
            shift
            ;;
        --warm)
            TEST_MODE="warm"
            shift
            ;;
        --gui)
            GUI_MODE=true
            shift
            ;;
        --skip-ingest)
            INGEST_VIDEOS=false
            shift
            ;;
        --help)
            echo "FAVE JMeter Load Test Runner"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --threads N     Number of concurrent threads (default: 5)"
            echo "  --ramp N        Ramp-up time in seconds (default: 5)"
            echo "  --loops N       Number of loop iterations (default: 1)"
            echo "  --gateway HOST  Gateway hostname (default: 127.0.0.1)"
            echo "  --port PORT     Gateway port (default: 8080)"
            echo "  --cold          Cold burst test (ramp=0, all threads start immediately)"
            echo "  --warm          Warm steady test (default)"
            echo "  --gui           Open JMeter GUI instead of CLI"
            echo "  --skip-ingest   Skip video ingestion step"
            echo "  --help          Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check if JMeter is installed
if ! command -v jmeter &> /dev/null; then
    echo "ERROR: JMeter is not installed."
    echo ""
    echo "Install with Homebrew:"
    echo "  brew install jmeter"
    echo ""
    echo "Or download from:"
    echo "  https://jmeter.apache.org/download_jmeter.cgi"
    exit 1
fi

# Create results directory
mkdir -p "$RESULTS_DIR"

# Generate timestamp for results
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_FILE="${RESULTS_DIR}/results_${TEST_MODE}_${THREADS}t_${TIMESTAMP}.jtl"
LOG_FILE="${RESULTS_DIR}/jmeter_${TEST_MODE}_${TIMESTAMP}.log"

echo "========================================"
echo "FAVE JMeter Load Test"
echo "========================================"
echo "Test Mode:    ${TEST_MODE}"
echo "Threads:      ${THREADS}"
echo "Ramp Time:    ${RAMP_TIME}s"
echo "Loops:        ${LOOPS}"
echo "Gateway:      http://${GATEWAY_URL}:${GATEWAY_PORT}"
echo "Results:      ${RESULTS_FILE}"
echo "========================================"
echo ""

# Step 1: Ingest videos (if not skipped)
if [ "$INGEST_VIDEOS" = true ]; then
    echo "Step 1: Ingesting videos to MinIO..."
    python3 "${SCRIPT_DIR}/auto_ingest_videos.py" --limit 3
    echo ""
else
    echo "Step 1: Skipping video ingestion"
    echo ""
fi

# Check if JMeter videos CSV exists
if [ ! -f "${DATASETS_DIR}/jmeter_videos.csv" ]; then
    echo "ERROR: JMeter videos CSV not found. Run video ingestion first."
    echo "  python3 scripts/auto_ingest_videos.py"
    exit 1
fi

# Step 2: Run JMeter
if [ "$GUI_MODE" = true ]; then
    echo "Step 2: Opening JMeter GUI..."
    jmeter -t "$JMETER_PLAN" \
        -JGATEWAY_URL="$GATEWAY_URL" \
        -JGATEWAY_PORT="$GATEWAY_PORT"
else
    echo "Step 2: Running JMeter CLI test..."
    echo ""

    jmeter -n \
        -t "$JMETER_PLAN" \
        -l "$RESULTS_FILE" \
        -j "$LOG_FILE" \
        -JGATEWAY_URL="$GATEWAY_URL" \
        -JGATEWAY_PORT="$GATEWAY_PORT" \
        -JThreadGroup.num_threads="$THREADS" \
        -JThreadGroup.ramp_time="$RAMP_TIME" \
        -JLoopController.loops="$LOOPS"

    echo ""
    echo "========================================"
    echo "Test Complete!"
    echo "========================================"
    echo "Results: ${RESULTS_FILE}"
    echo "Log:     ${LOG_FILE}"
    echo ""

    # Step 3: Convert JTL to JSON for analysis
    echo "Step 3: Converting results to JSON..."
    python3 - << 'PYTHON_SCRIPT'
import csv
import json
import sys
from pathlib import Path

results_dir = Path("experiments/jmeter")
jtl_files = sorted(results_dir.glob("*.jtl"), key=lambda p: p.stat().st_mtime, reverse=True)

if not jtl_files:
    print("No JTL files found")
    sys.exit(0)

latest_jtl = jtl_files[0]
print(f"Converting: {latest_jtl}")

results = []
with open(latest_jtl, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        results.append({
            "timestamp": row.get("timeStamp", ""),
            "duration_ms": int(row.get("elapsed", 0)),
            "status": "success" if row.get("success", "").lower() == "true" else "failure",
            "response_code": row.get("responseCode", ""),
            "label": row.get("label", ""),
            "thread_name": row.get("threadName", ""),
            "latency_ms": int(row.get("Latency", 0)),
            "connect_time_ms": int(row.get("Connect", 0)),
            "bytes": int(row.get("bytes", 0)),
        })

json_file = latest_jtl.with_suffix(".json")
with open(json_file, 'w') as f:
    json.dump(results, f, indent=2)

print(f"JSON output: {json_file}")

# Print summary
total = len(results)
successes = sum(1 for r in results if r["status"] == "success")
durations = [r["duration_ms"] for r in results]
avg_duration = sum(durations) / len(durations) if durations else 0

print(f"\nSummary:")
print(f"  Total requests: {total}")
print(f"  Successes: {successes} ({successes/total*100:.1f}%)")
print(f"  Average duration: {avg_duration:.0f}ms")
PYTHON_SCRIPT

fi

echo ""
echo "Done!"
