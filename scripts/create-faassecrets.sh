#!/usr/bin/env bash
set -euo pipefail

# Create/update OpenFaaS secrets for artifact storage credentials.
# Requires faas-cli logged into the gateway.

GATEWAY=${GATEWAY:-http://127.0.0.1:8080}
ACCESS_KEY=${ARTIFACT_ACCESS_KEY:?set ARTIFACT_ACCESS_KEY}
SECRET_KEY=${ARTIFACT_SECRET_KEY:?set ARTIFACT_SECRET_KEY}

export OPENFAAS_URL="${GATEWAY}"

printf "%s" "${ACCESS_KEY}" | faas-cli secret create artifact-access-key --from-stdin || faas-cli secret update artifact-access-key --from-stdin <<<"${ACCESS_KEY}"
printf "%s" "${SECRET_KEY}" | faas-cli secret create artifact-secret-key --from-stdin || faas-cli secret update artifact-secret-key --from-stdin <<<"${SECRET_KEY}"

echo "Secrets artifact-access-key and artifact-secret-key created/updated."
