FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY schemas ./schemas

RUN python -m pip install --no-cache-dir '.[transport]'

EXPOSE 8090

CMD ["edge-log-agent"]