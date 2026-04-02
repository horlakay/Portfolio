FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY shared /app/shared
COPY services/decision-service /app/services/decision-service
COPY data /app/data
COPY tests /app/tests
COPY scripts /app/scripts

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

CMD ["uvicorn", "decision_service.main:app", "--host", "0.0.0.0", "--port", "8005"]
