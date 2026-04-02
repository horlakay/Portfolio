FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY shared /app/shared
COPY services/rule-engine /app/services/rule-engine
COPY scripts /app/scripts

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

CMD ["uvicorn", "rule_engine.main:app", "--host", "0.0.0.0", "--port", "8003"]
