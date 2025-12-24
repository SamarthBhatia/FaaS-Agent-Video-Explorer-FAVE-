FROM fave-base:dev

ARG MODEL_URL=https://github.com/onnx/models/raw/main/validated/vision/object_detection_segmentation/tiny-yolov4/model/tiny-yolov4-11.onnx
ARG LABEL_URL=https://raw.githubusercontent.com/onnx/models/main/validated/vision/object_detection_segmentation/tiny-yolov4/dependencies/coco.names

RUN mkdir -p /opt/models && \
    touch /opt/models/model.onnx && \
    touch /opt/models/coco.names

COPY . /workspace/

CMD ["fprocess=python3 handler.py"]

