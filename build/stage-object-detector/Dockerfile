ARG BASE_IMAGE=fave-base:dev
ARG WATCHDOG_VERSION=0.9.11

FROM ghcr.io/openfaas/of-watchdog:${WATCHDOG_VERSION} as watchdog

FROM ${BASE_IMAGE} as app

# Model paths
RUN mkdir -p /opt/models

# Copy vendored models from local directory
COPY models/model.onnx /opt/models/model.onnx
COPY models/coco.names /opt/models/coco.names

COPY --from=watchdog /fwatchdog /usr/bin/fwatchdog

WORKDIR /home/app
COPY . ./ 

ENV fprocess="python3 index.py" \
    mode="http" \
    http_upstream_url="http://127.0.0.1:5000" \
    upstream_timeout="300s" \
    read_timeout="300s" \
    write_timeout="300s"

CMD ["fwatchdog"]