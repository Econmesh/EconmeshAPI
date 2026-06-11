#!/usr/bin/env bash
# Render build script — install runtime dependencies only.
set -euo pipefail

poetry install --only main --no-root --no-ansi
