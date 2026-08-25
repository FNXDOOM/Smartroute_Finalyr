FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python dependencies before copying source for better layer caching.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# The backend uses top-level imports such as `database` and `routers`, so run
# Uvicorn from the backend directory.
COPY backend/ /app/backend/
COPY alembic.ini /app/backend/alembic.ini
COPY alembic/ /app/backend/alembic/
WORKDIR /app/backend

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
