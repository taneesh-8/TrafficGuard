#!/usr/bin/env bash
set -e

pip install --upgrade pip

# Install pydantic-core from pre-built wheel before anything else
# (avoids Rust compilation which fails on Render's read-only cargo cache)
pip install "pydantic-core==2.27.1" --only-binary :all:

# Install everything else
pip install -r requirements.txt --only-binary pydantic-core,numpy

echo "Build complete."
