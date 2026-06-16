FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
RUN pip install --no-cache-dir pandas
