FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.12-slim

WORKDIR /app

COPY services/mqtt-kafka-bridge/pyproject.toml ./pyproject.toml
COPY services/mqtt-kafka-bridge/src/bridge ./src/bridge
COPY libs/shared/src/shared ./src/shared

RUN python -m pip install --no-cache-dir \
    --timeout 120 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    .

CMD ["mqtt-kafka-bridge"]
