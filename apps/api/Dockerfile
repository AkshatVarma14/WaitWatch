# Pinned official Python slim image for reproducibility and security
FROM python:3.12-slim-bookworm AS runtime

# Environment settings
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install security certificates and curl for diagnostics
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files and source code
COPY pyproject.toml alembic.ini ./
COPY alembic/ ./alembic/
COPY app/ ./app/

# Install package and dependencies
RUN pip install --no-cache-dir .

# Create unprivileged runtime user
RUN groupadd --system --gid 1001 waitwatch && \
    useradd --system --uid 1001 --gid waitwatch --home-dir /app waitwatch && \
    chown -R waitwatch:waitwatch /app

USER waitwatch

EXPOSE 8000

# Native healthcheck using Python standard library (no external dependencies needed)
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
