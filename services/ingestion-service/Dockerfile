FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/shared/src:/app/services/ingestion-service/src

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY shared /app/shared
COPY services/ingestion-service /app/services/ingestion-service
COPY training /app/training
COPY tests /app/tests
COPY scripts /app/scripts

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

COPY data /app/data

CMD ["uvicorn", "ingestion_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
