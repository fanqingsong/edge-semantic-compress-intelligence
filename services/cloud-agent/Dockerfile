FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.12-slim

WORKDIR /app

COPY services/cloud-agent/pyproject.toml ./pyproject.toml
COPY services/cloud-agent/src/cloud/agent ./src/cloud/agent
COPY libs/cloud/src/cloud/retrieval ./src/cloud/retrieval
COPY libs/cloud/src/cloud/rag ./src/cloud/rag
COPY libs/shared/src/shared ./src/shared

RUN python -m pip install --no-cache-dir \
    --timeout 120 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    '.[milvus,transport]'

CMD ["cloud-rag-agent"]
