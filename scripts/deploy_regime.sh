#!/usr/bin/env bash
set -euo pipefail

REGIME=${1:-cold}
STACK_FILE=${2:-functions/stack.yml}

case ${REGIME} in
  cold)
    MIN_REPLICAS=0
    MAX_REPLICAS=5
    FACTOR=20
    ;;
  warm)
    MIN_REPLICAS=1
    MAX_REPLICAS=5
    FACTOR=20
    ;;
  burst-ready)
    MIN_REPLICAS=3
    MAX_REPLICAS=10
    FACTOR=10
    ;;
  *)
    echo "Unknown regime: ${REGIME}"
    exit 1
    ;;
esac

echo "Deploying regime: ${REGIME} (min=${MIN_REPLICAS}, max=${MAX_REPLICAS})"

# Create a temporary stack file with labels added
TEMP_STACK=$(mktemp /tmp/stack-XXXX.yml)
cp "${STACK_FILE}" "${TEMP_STACK}"

# Ensure PyYAML is available
if ! python3 -c "import yaml" &> /dev/null; then
    echo "PyYAML not found. Installing..."
    pip3 install pyyaml
fi

# Use a simple python snippet to inject labels into each function
python3 - <<EOF
import yaml
import sys

with open("${TEMP_STACK}", 'r') as f:
    data = yaml.safe_load(f)

for func_name, func_config in data['functions'].items():
    labels = func_config.get('labels', {})
    labels['com.openfaas.scale.min'] = "${MIN_REPLICAS}"
    labels['com.openfaas.scale.max'] = "${MAX_REPLICAS}"
    func_config['labels'] = labels

with open("${TEMP_STACK}", 'w') as f:
    yaml.dump(data, f)
EOF

faas-cli deploy -f "${TEMP_STACK}"

rm "${TEMP_STACK}"
echo "Regime ${REGIME} applied."
