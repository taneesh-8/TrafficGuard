#!/usr/bin/env bash
set -e
mkdir -p uploads evidence_output
echo "Starting TrafficGuard AI on port ${PORT:-8000}..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
