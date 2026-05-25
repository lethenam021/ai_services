#!/bin/bash
# Chạy migration trước khi start app
echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec "$@"