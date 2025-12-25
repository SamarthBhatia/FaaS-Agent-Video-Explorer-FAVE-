ARG BASE_IMAGE=fave-base:dev
ARG WATCHDOG_VERSION=0.9.11

FROM ghcr.io/openfaas/of-watchdog:${WATCHDOG_VERSION} as watchdog

FROM ${BASE_IMAGE} as app

ARG MODEL_URL=https://huggingface.co/Kalray/yolov4-tiny/resolve/main/yolov4-tiny.onnx
ARG LABEL_URL=https://raw.githubusercontent.com/pjreddie/darknet/master/data/coco.names

RUN mkdir -p /opt/models && \
    wget -O /opt/models/model.onnx "${MODEL_URL}" && \
    wget -O /opt/models/coco.names "${LABEL_URL}"

COPY --from=watchdog /fwatchdog /usr/bin/fwatchdog

WORKDIR /home/app
COPY handler.py index.py stage_object_detector_service.py ./

ENV fprocess="python3 index.py" \
    mode="http" \
    http_upstream_url="http://127.0.0.1:5000" \
    upstream_timeout="300s" \
    read_timeout="300s" \
    write_timeout="300s"

CMD ["fwatchdog"]
