FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend

WORKDIR /app

COPY pyproject.toml requirements.lock README.md ./
COPY backend ./backend
COPY config ./config
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir -r requirements.lock

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
