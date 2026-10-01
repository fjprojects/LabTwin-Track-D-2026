FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       default-jdk-headless \
       ffmpeg \
       poppler-utils \
       tesseract-ocr \
       libreoffice-impress \
       fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-render.txt /app/requirements-render.txt
COPY requirements-evaluation.txt /app/requirements-evaluation.txt

RUN pip install --no-cache-dir     -r /app/requirements-render.txt
RUN python -m venv /opt/labtwin-evaluation \
    && /opt/labtwin-evaluation/bin/pip install --no-cache-dir -r /app/requirements-evaluation.txt
ENV LABTWIN_EVALUATOR_PYTHON=/opt/labtwin-evaluation/bin/python
ENV LABTWIN_PROJECT_ROOT=/app

COPY backend/ /app/
COPY scripts/ /app/scripts/
COPY evaluation/benchmark.json /app/evaluation/benchmark.json

CMD ["sh", "-c", "python manage.py migrate && exec gunicorn backend.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 1 --timeout 180"]
