FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends build-essential default-jdk-headless && rm -rf /var/lib/apt/lists/*
COPY runtime.py /opt/labtwin/runtime.py
USER 65534:65534
ENTRYPOINT ["python", "-I", "/opt/labtwin/runtime.py"]
