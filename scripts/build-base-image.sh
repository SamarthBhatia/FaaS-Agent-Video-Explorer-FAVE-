#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME=${IMAGE_NAME:-fave-base}
IMAGE_TAG=${IMAGE_TAG:-dev}
IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

echo "Building ${IMAGE}..."
docker build -t "${IMAGE}" base-image

if [[ -n "${PUSH_TARGET:-}" ]]; then
  docker tag "${IMAGE}" "${PUSH_TARGET}"
  docker push "${PUSH_TARGET}"
  echo "Pushed ${PUSH_TARGET}"
else
  echo "Skipping push (set PUSH_TARGET to push)."
fi
