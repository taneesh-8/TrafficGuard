#!/usr/bin/env bash
# render_start.sh — startup script for Render deployment
# Creates persistent data directories on the mounted disk before starting

set -e

# Ensure persistent directories exist on the mounted disk (/data)
mkdir -p /data/uploads
mkdir -p /data/evidence_output

echo "Data directories ready at /data"
echo "Starting TrafficGuard AI backend on port ${PORT:-8000}..."

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
