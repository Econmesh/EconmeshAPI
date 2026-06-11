#!/usr/bin/env bash
# Render start script — gunicorn bound to Render's dynamic PORT.
set -euo pipefail

: "${PORT:=8000}"
: "${WEB_CONCURRENCY:=2}"

exec poetry run gunicorn src.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w "${WEB_CONCURRENCY}" \
  -b "0.0.0.0:${PORT}" \
  --access-logfile - \
  --error-logfile - \
  --timeout 60
