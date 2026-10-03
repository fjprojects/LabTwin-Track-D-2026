# Optional complete Linux demo image; the existing backend Dockerfile remains.
FROM node:24-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# One HTTPS origin for API, signed media, UI and on-device camera assets.
ENV VITE_API_URL=/api
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    LITELLM_LOCAL_MODEL_COST_MAP=True \
    DJANGO_SETTINGS_MODULE=deployment.settings \
    PYTHONPATH=/app:/app/backend \
    LABTWIN_EVALUATOR_PYTHON=/opt/labtwin-evaluation/bin/python \
    LABTWIN_PROJECT_ROOT=/app LABTWIN_DATA_DIR=/data
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential default-jdk-headless \
       ffmpeg poppler-utils tesseract-ocr libreoffice-impress fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-render.txt requirements-evaluation.txt /app/
# Do not replace/downgrade the tested CrewAI/LanceDB/Chroma requirements.
RUN pip install --no-cache-dir -r requirements-render.txt \
    && python -m venv /opt/labtwin-evaluation \
    && /opt/labtwin-evaluation/bin/pip install --no-cache-dir -r requirements-evaluation.txt
COPY backend/ /app/backend/
COPY scripts/ /app/scripts/
COPY evaluation/ /app/evaluation/
COPY deployment/ /app/deployment/
COPY --from=frontend /build/frontend/dist/ /app/frontend/dist/
RUN useradd --uid 10001 --create-home labtwin \
    && mkdir -p /data \
    && chown -R labtwin:labtwin /app /data
USER 10001:10001
EXPOSE 10000
CMD ["python", "/app/deployment/start.py"]
