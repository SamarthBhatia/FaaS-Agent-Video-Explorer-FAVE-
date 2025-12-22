#!/usr/bin/env bash
set -euo pipefail

# Simple helper to run a local MinIO instance for development/testing.
# Usage: ./scripts/minio-dev.sh

MINIO_ROOT_USER=${MINIO_ROOT_USER:-faveadmin}
MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-favesecret}
MINIO_DATA_DIR=${MINIO_DATA_DIR:-$HOME/.fave/minio-data}
MINIO_PORT=${MINIO_PORT:-9000}
MINIO_CONSOLE_PORT=${MINIO_CONSOLE_PORT:-9090}

mkdir -p "${MINIO_DATA_DIR}"

docker run --rm -it \
  -p "${MINIO_PORT}:9000" \
  -p "${MINIO_CONSOLE_PORT}:9090" \
  -e MINIO_ROOT_USER="${MINIO_ROOT_USER}" \
  -e MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD}" \
  -v "${MINIO_DATA_DIR}:/data" \
  quay.io/minio/minio server /data --console-address ":${MINIO_CONSOLE_PORT}"
