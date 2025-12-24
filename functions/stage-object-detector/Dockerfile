FROM fave-base:dev

ARG MODEL_URL=https://huggingface.co/Kalray/yolov4-tiny/resolve/main/yolov4-tiny.onnx
ARG LABEL_URL=https://raw.githubusercontent.com/pjreddie/darknet/master/data/coco.names

RUN mkdir -p /opt/models && \
    wget -O /opt/models/model.onnx "${MODEL_URL}" && \
    wget -O /opt/models/coco.names "${LABEL_URL}"

COPY . /workspace/

CMD ["fprocess=python3 handler.py"]

