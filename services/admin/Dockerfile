FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.12-slim

WORKDIR /app

COPY services/admin/pyproject.toml ./pyproject.toml
COPY services/admin/src/cloud/admin ./src/cloud/admin
COPY services/knowledge-ingest/src/cloud/knowledge ./src/cloud/knowledge
COPY libs/cloud/src/cloud/retrieval ./src/cloud/retrieval
COPY libs/shared/src/shared ./src/shared

RUN python -m pip install --no-cache-dir \
    --timeout 120 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    '.[milvus,documents]'

RUN python -c "import cloud.knowledge.ingest, cloud.admin.http; from pathlib import Path; assert (Path(cloud.admin.http.__file__).parent / 'static' / 'index.html').is_file()"

EXPOSE 8088

CMD ["cloud-admin"]
