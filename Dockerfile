# syntax=docker/dockerfile:1
# LineageLens - production image. Everything runs offline; no telemetry.

# ---------- Stage 1: build the web UI ----------
FROM node:20-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# vite.config.ts writes the bundle to ../lineagelens/static
RUN mkdir -p ../lineagelens/static && npm run build

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

ARG VERSION=dev
LABEL org.opencontainers.image.title="LineageLens" \
      org.opencontainers.image.description="Local, offline column-level lineage and impact analysis for dbt, Snowflake and Power BI." \
      org.opencontainers.image.source="https://github.com/dhruvpuri-goswami/LineageLens" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LINEAGELENS_HOST=0.0.0.0 \
    LINEAGELENS_PORT=8765 \
    LINEAGELENS_HOME=/data \
    LINEAGELENS_LOG_FORMAT=json \
    LINEAGELENS_LOG_LEVEL=info \
    LINEAGELENS_ALLOWED_ROOTS=/inputs:/data

WORKDIR /app

# Locked, hash-checked dependencies first (cached layer).
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY LICENSES/ ./LICENSES/
COPY lineagelens/ ./lineagelens/
COPY --from=frontend /build/lineagelens/static/ ./lineagelens/static/
RUN pip install --no-deps . \
 && rm -rf /app/lineagelens /app/build \
 && groupadd --system --gid 10001 lineagelens \
 && useradd --system --uid 10001 --gid lineagelens --home-dir /data --shell /usr/sbin/nologin lineagelens \
 && mkdir -p /data /inputs \
 && chown lineagelens:lineagelens /data

USER 10001:10001
VOLUME ["/data"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import os,sys,urllib.request; u='http://127.0.0.1:%s/api/health' % os.environ.get('LINEAGELENS_PORT','8765'); sys.exit(0 if urllib.request.urlopen(u, timeout=4).status == 200 else 1)"]

ENTRYPOINT ["lineagelens"]
CMD ["serve", "--no-browser"]
