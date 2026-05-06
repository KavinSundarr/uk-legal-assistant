#!/bin/sh
set -e
echo "Starting UK Legal Assistant..."
echo "PORT is: $PORT"
export APP_PORT=${PORT:-8000}
echo "Using port: $APP_PORT"
exec python -m uvicorn backend.app.main:app \
    --host 0.0.0.0 \
    --port $APP_PORT \
    --workers 1 \
    --log-level info
