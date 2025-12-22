#!/usr/bin/env bash
set -euo pipefail

# Bootstrap the MinIO bucket and alias after running scripts/minio-dev.sh
# Requires the 'mc' (MinIO client) binary installed locally.

ENDPOINT=${ENDPOINT:-http://localhost:9000}
ACCESS_KEY=${ACCESS_KEY:-faveadmin}
SECRET_KEY=${SECRET_KEY:-favesecret}
ALIAS=${ALIAS:-fave}
BUCKET=${BUCKET:-fave-artifacts}

mc alias set "${ALIAS}" "${ENDPOINT}" "${ACCESS_KEY}" "${SECRET_KEY}"
mc mb --ignore-existing "${ALIAS}/${BUCKET}"
mc anonymous set download "${ALIAS}/${BUCKET}" >/dev/null 2>&1 || true
echo "Bucket ${BUCKET} ready under alias ${ALIAS}"
