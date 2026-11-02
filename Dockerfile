FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY config/ ./config/
COPY src/ ./src/
COPY dbt/ ./dbt/
RUN python -m pip install --upgrade pip && pip install ".[dev,analytics,api]"
ENV PYTHONPATH=/app:/app/src
CMD ["python", "-m", "knbs_cbk_pipeline.pipeline"]
