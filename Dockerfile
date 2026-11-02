FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY schemas ./schemas

RUN python -m pip install --no-cache-dir \
    --timeout 120 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    '.[transport]'

EXPOSE 8090

CMD ["edge-log-agent"]