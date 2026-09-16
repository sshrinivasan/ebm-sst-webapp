# ---- Stage 1: build the React frontend ----
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python backend + serve static frontend ----
FROM python:3.13-slim

# System deps for pandas/numpy/matplotlib wheels + openpyxl
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Backend deps first (layer caching)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Backend source (the `app` package lives at /app/backend/app)
COPY backend/ /app/backend/

# Built frontend static files
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

# Work from the backend dir so `app.main:app` resolves
WORKDIR /app/backend

# Railway injects a dynamic PORT env var; fall back to 8000 locally.
# The app must bind 0.0.0.0 so Railway's proxy can reach it.
EXPOSE 8000

# Run uvicorn serving the FastAPI app. The frontend is served by FastAPI's
# StaticFiles mount (see backend/app/main.py) so a single container/port works.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
