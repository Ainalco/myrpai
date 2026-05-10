#!/bin/bash
set -e

echo "Starting application startup sequence..."

# Run database migrations
echo "Running database migrations..."
python migrate.py

# Start the FastAPI application
echo "Starting FastAPI application..."
exec uvicorn main:socket_app --host 0.0.0.0 --port 9000 --reload
