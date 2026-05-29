# syntax=docker/dockerfile:1.7
# ----------------------------------------------------------------------------
# Econmesh API — production Dockerfile
#
# Multi-stage build:
#   1. builder  → installs Poetry, resolves and installs runtime deps into
#                 a self-contained virtualenv at /opt/venv.
#   2. runtime  → minimal image, non-root user, copies only the venv + src/.
# ----------------------------------------------------------------------------

ARG PYTHON_VERSION=3.14
ARG POETRY_VERSION=2.0.1

# ============================================================================
# Stage 1 — builder
# ============================================================================
FROM python:${PYTHON_VERSION}-slim AS builder

ARG POETRY_VERSION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry-cache \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app
COPY pyproject.toml poetry.lock* README.md ./

RUN python -m venv "${VIRTUAL_ENV}" \
    && poetry install --only main --no-root --no-ansi \
    && rm -rf "${POETRY_CACHE_DIR}"

# ============================================================================
# Stage 2 — runtime
# ============================================================================
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app src ./src
COPY --chown=app:app pyproject.toml README.md ./

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl --silent --fail http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", "src.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "4", \
     "-b", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--timeout", "60"]
