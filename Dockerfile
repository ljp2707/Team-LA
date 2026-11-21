# Base images are pinned by digest, not just tag, so a rebuild always starts from the
# exact image that was tested; Dependabot proposes new digests (findings F40).

# Stage 1: build the frontend
FROM node:26-slim@sha256:e6bedef217677b276c591795e169840edd9096dbf13f29df8ef8d1856b8820bc AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: the Python app, which also serves the built frontend.
# The slim image has no compilers; only the app, its locked packages and the built
# frontend go in. Tests, dev requirements and source maps stay out (.dockerignore).
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Debian security fixes that are newer than the pinned base image (Trivy in CI fails the
# build on any fixable HIGH or CRITICAL issue, findings F42). Nothing new is installed.
RUN apt-get update     && apt-get upgrade -y --no-install-recommends     && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt ./
# Every package, including the ones they depend on, must match a hash in the lock file,
# so a tampered or swapped package on PyPI fails the build (findings F39).
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt
COPY backend/ ./
COPY --from=frontend /frontend/dist ./app/static

RUN useradd --create-home appuser
USER appuser

# Docker and most hosts restart a container whose health check fails. Railway uses its own
# check on /api/health (railway.json). The Host header is one production answers to (F14).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3     CMD ["python", "-c", "import os, urllib.request as u; u.urlopen(u.Request('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), headers={'Host': 'healthcheck.railway.app'}), timeout=4)"]

# Railway sets PORT. The cron service replaces this command (see railway.cron.json).
# Railway's edge is the only way in, so trust its X-Forwarded-For and -Proto headers:
# the app then sees each visitor's real address and https (findings F14).
# FORWARDED_ALLOW_IPS narrows which proxies are believed; "*" when it is not set.
# --no-server-header: do not tell visitors which web server and version runs the app (F27).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-*}\" --no-server-header"]
