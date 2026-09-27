# Build the UI, then a slim runtime that serves it and the API on one port.
FROM node:22-slim AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MALLOC_ARENA_MAX=2 \
    PORT=8000
WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN grep -v -i pytest /tmp/requirements.txt > /tmp/runtime.txt \
    && pip install --no-cache-dir -r /tmp/runtime.txt \
    && rm /tmp/requirements.txt /tmp/runtime.txt
COPY backend ./backend
COPY --from=web /src/frontend/dist ./frontend/dist
RUN useradd --create-home --uid 1000 desk \
    && mkdir -p /app/backend/data/cache \
    && chown -R desk:desk /app
USER desk
EXPOSE 8000
CMD ["python", "-m", "backend.app.serve"]
