FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY data/index/ ./data/index/
COPY entrypoint.sh ./entrypoint.sh

RUN chmod +x /app/entrypoint.sh

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
