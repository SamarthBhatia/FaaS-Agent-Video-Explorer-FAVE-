#!/bin/bash
#
# FAVE Scaling Experiment Runner
#
# Runs a full matrix of JMeter load tests across different thread counts
# and deployment modes (warm/cold). Captures HPA scaling events.
#
# Usage:
#   ./scripts/run_scaling_experiment.sh                    # Full matrix
#   ./scripts/run_scaling_experiment.sh --threads "5 10"   # Custom threads
#   ./scripts/run_scaling_experiment.sh --modes "warm"     # Warm only
#   ./scripts/run_scaling_experiment.sh --hpa              # Enable HPA before tests
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Defaults
THREAD_COUNTS="5 10 20 50"
MODES="warm cold"
COOLDOWN=30
ENABLE_HPA=false
SKIP_INGEST=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --threads)
            THREAD_COUNTS="$2"
            shift 2
            ;;
        --modes)
            MODES="$2"
            shift 2
            ;;
        --cooldown)
            COOLDOWN="$2"
            shift 2
            ;;
        --hpa)
            ENABLE_HPA=true
            shift
            ;;
        --skip-ingest)
            SKIP_INGEST=true
            shift
            ;;
        --help)
            echo "FAVE Scaling Experiment Runner"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --threads \"N1 N2 ...\"  Thread counts to test (default: \"5 10 20 50\")"
            echo "  --modes \"m1 m2\"        Modes to test (default: \"warm cold\")"
            echo "  --cooldown SECS        Cooldown between runs (default: 30)"
            echo "  --hpa                  Enable HPA regime before running tests"
            echo "  --skip-ingest          Skip video ingestion"
            echo "  --help                 Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

EXPERIMENT_DIR="${PROJECT_ROOT}/experiments/jmeter"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SUMMARY_FILE="${EXPERIMENT_DIR}/scaling_experiment_${TIMESTAMP}.log"

mkdir -p "$EXPERIMENT_DIR"

echo "========================================" | tee "$SUMMARY_FILE"
echo "FAVE Scaling Experiment" | tee -a "$SUMMARY_FILE"
echo "========================================" | tee -a "$SUMMARY_FILE"
echo "Thread counts: ${THREAD_COUNTS}" | tee -a "$SUMMARY_FILE"
echo "Modes:         ${MODES}" | tee -a "$SUMMARY_FILE"
echo "Cooldown:      ${COOLDOWN}s" | tee -a "$SUMMARY_FILE"
echo "HPA enabled:   ${ENABLE_HPA}" | tee -a "$SUMMARY_FILE"
echo "Started:       $(date)" | tee -a "$SUMMARY_FILE"
echo "========================================" | tee -a "$SUMMARY_FILE"
echo "" | tee -a "$SUMMARY_FILE"

# Enable HPA if requested
if [ "$ENABLE_HPA" = true ]; then
    echo "Enabling HPA regime..." | tee -a "$SUMMARY_FILE"
    "${SCRIPT_DIR}/deploy_regime.sh" hpa
    echo "" | tee -a "$SUMMARY_FILE"
fi

# Capture HPA state before tests
echo "--- HPA state before tests ---" | tee -a "$SUMMARY_FILE"
kubectl get hpa -n openfaas-fn 2>/dev/null | tee -a "$SUMMARY_FILE" || echo "(no HPA configured)" | tee -a "$SUMMARY_FILE"
echo "" | tee -a "$SUMMARY_FILE"

INGEST_FLAG=""
if [ "$SKIP_INGEST" = true ]; then
    INGEST_FLAG="--skip-ingest"
fi

RUN_COUNT=0
TOTAL_RUNS=$(echo "$THREAD_COUNTS" | wc -w)
TOTAL_RUNS=$((TOTAL_RUNS * $(echo "$MODES" | wc -w)))

for MODE in $MODES; do
    for THREADS in $THREAD_COUNTS; do
        RUN_COUNT=$((RUN_COUNT + 1))
        echo "========================================" | tee -a "$SUMMARY_FILE"
        echo "Run ${RUN_COUNT}/${TOTAL_RUNS}: ${MODE} mode, ${THREADS} threads" | tee -a "$SUMMARY_FILE"
        echo "Started: $(date)" | tee -a "$SUMMARY_FILE"
        echo "========================================" | tee -a "$SUMMARY_FILE"

        # Apply the appropriate regime for this mode (unless HPA is managing it)
        if [ "$ENABLE_HPA" = false ]; then
            "${SCRIPT_DIR}/deploy_regime.sh" "$MODE"
            # Wait for pods to stabilize
            if [ "$MODE" = "warm" ]; then
                echo "Waiting for pods to be ready..."
                kubectl wait --for=condition=available deployment --all -n openfaas-fn --timeout=5m 2>/dev/null || true
            fi
        fi

        # Snapshot pod counts before run
        echo "--- Pods before run ---" | tee -a "$SUMMARY_FILE"
        kubectl get pods -n openfaas-fn --no-headers 2>/dev/null | wc -l | xargs -I{} echo "Pod count: {}" | tee -a "$SUMMARY_FILE"

        # Run the test
        "${SCRIPT_DIR}/run_jmeter_test.sh" \
            --threads "$THREADS" \
            --"$MODE" \
            $INGEST_FLAG \
            2>&1 | tee -a "$SUMMARY_FILE"

        # Snapshot HPA and pod state after run
        echo "" | tee -a "$SUMMARY_FILE"
        echo "--- HPA state after run ---" | tee -a "$SUMMARY_FILE"
        kubectl get hpa -n openfaas-fn 2>/dev/null | tee -a "$SUMMARY_FILE" || true
        echo "" | tee -a "$SUMMARY_FILE"
        echo "--- Pod counts after run ---" | tee -a "$SUMMARY_FILE"
        kubectl get pods -n openfaas-fn --no-headers 2>/dev/null | wc -l | xargs -I{} echo "Pod count: {}" | tee -a "$SUMMARY_FILE"

        # Cooldown between runs
        if [ "$RUN_COUNT" -lt "$TOTAL_RUNS" ]; then
            echo "" | tee -a "$SUMMARY_FILE"
            echo "Cooling down for ${COOLDOWN}s..." | tee -a "$SUMMARY_FILE"
            sleep "$COOLDOWN"
        fi
    done
done

echo "" | tee -a "$SUMMARY_FILE"
echo "========================================" | tee -a "$SUMMARY_FILE"
echo "Experiment complete at $(date)" | tee -a "$SUMMARY_FILE"
echo "Summary log: ${SUMMARY_FILE}" | tee -a "$SUMMARY_FILE"
echo "========================================" | tee -a "$SUMMARY_FILE"
