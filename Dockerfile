FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build tools for native extensions (hdbscan, h3, osmnx's geo stack, ortools).
# Most ship manylinux wheels, but this is cheap insurance against a
# platform/arch where pip has to build one of them from source.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies before copying source for better layer caching.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# The backend uses top-level imports such as `database` and `routers`, so run
# Uvicorn from the backend directory.
COPY backend/ /app/backend/
COPY alembic.ini /app/backend/alembic.ini
COPY alembic/ /app/backend/alembic/
# services/prediction/demand_model.py resolves the XGBoost model as
# <app-root>/ml/models/demand_model.pkl. Without this, the image builds fine
# but /predict/heatmap silently falls back to the heuristic predictor.
COPY ml/ /app/ml/
WORKDIR /app/backend

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live', timeout=3)"]

# --proxy-headers + --forwarded-allow-ips lets Uvicorn trust X-Forwarded-For/Proto
# from a reverse proxy (e.g. Nginx Proxy Manager) so it correctly detects HTTPS
# (see the HSTS header logic in backend/main.py) and logs real client IPs.
# The worker service (docker-compose.yml) overrides both CMD and HEALTHCHECK.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
