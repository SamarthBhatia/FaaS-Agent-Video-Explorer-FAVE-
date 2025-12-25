ARG BASE_IMAGE=fave-base:dev
ARG WATCHDOG_VERSION=0.9.11

FROM ghcr.io/openfaas/of-watchdog:${WATCHDOG_VERSION} as watchdog

FROM ${BASE_IMAGE} as app

COPY --from=watchdog /fwatchdog /usr/bin/fwatchdog

WORKDIR /home/app
COPY handler.py index.py stage_librosa_service.py ./


ENV fprocess="python3 index.py" \
    mode="http" \
    http_upstream_url="http://127.0.0.1:5000" \
    upstream_timeout="120s" \
    read_timeout="120s" \
    write_timeout="120s"

CMD ["fwatchdog"]