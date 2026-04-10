FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/shared/src:/app/services/analyst-console/src

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY shared /app/shared
COPY services/analyst-console /app/services/analyst-console
COPY scripts /app/scripts

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

CMD ["uvicorn", "analyst_console.main:app", "--host", "0.0.0.0", "--port", "8007"]
