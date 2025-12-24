ARG BASE_IMAGE=fave-base:dev
ARG WATCHDOG_VERSION=0.9.11

FROM ghcr.io/openfaas/of-watchdog:${WATCHDOG_VERSION} as watchdog

FROM ${BASE_IMAGE} as app

COPY --from=watchdog /fwatchdog /usr/bin/fwatchdog

WORKDIR /home/app
COPY handler.py stage_ffmpeg1_service.py ./

ENV fprocess="python3 handler.py" \
    mode="http" \
    upstream_timeout="180s" \
    read_timeout="180s" \
    write_timeout="180s"

CMD ["fwatchdog"]
