#!/usr/bin/env bash
set -e

# Install system dependencies needed by OpenCV headless on Ubuntu
apt-get update -qq && apt-get install -y -qq \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libgl1 \
    2>/dev/null || true

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

echo "Build complete."
