#!/usr/bin/env bash
# Production entrypoint for containerised deployments (Dokploy, Docker, K8s).
set -euo pipefail

: "${PORT:=8000}"
: "${WEB_CONCURRENCY:=2}"

exec gunicorn src.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w "${WEB_CONCURRENCY}" \
  -b "0.0.0.0:${PORT}" \
  --access-logfile - \
  --error-logfile - \
  --timeout 60
