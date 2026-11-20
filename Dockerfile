# Stage 1: build the frontend
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: the Python app, which also serves the built frontend
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /frontend/dist ./app/static

RUN useradd --create-home appuser
USER appuser

# Railway sets PORT. The cron service replaces this command (see railway.cron.json).
# Railway's edge is the only way in, so trust its X-Forwarded-For and -Proto headers:
# the app then sees each visitor's real address and https (findings F14).
# FORWARDED_ALLOW_IPS narrows which proxies are believed; "*" when it is not set.
# --no-server-header: do not tell visitors which web server and version runs the app (F27).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-*}\" --no-server-header"]
