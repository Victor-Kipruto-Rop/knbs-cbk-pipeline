FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ ./src/
COPY config/ ./config/

RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app:/app/src

CMD ["python", "-m", "knbs_cbk_pipeline.ingestion.runner"]
