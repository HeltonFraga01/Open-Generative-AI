#!/bin/bash
set -e

# Setup workspace directories if they don't exist
mkdir -p /workspace/custom_nodes
mkdir -p /workspace/models
mkdir -p /workspace/output
mkdir -p /workspace/input
mkdir -p /workspace/user

# Copy defaults if empty
if [ -z "$(ls -A /workspace/custom_nodes 2>/dev/null)" ]; then
    echo "Initializing default custom_nodes (incl. ComfyUI-Manager)..."
    cp -r /app/ComfyUI/custom_nodes_default/. /workspace/custom_nodes/
fi

if [ -z "$(ls -A /workspace/models 2>/dev/null)" ]; then
    echo "Initializing default models folder structure..."
    cp -r /app/ComfyUI/models_default/. /workspace/models/
fi

# Create symlinks to the app directory
rm -rf /app/ComfyUI/custom_nodes
ln -s /workspace/custom_nodes /app/ComfyUI/custom_nodes

rm -rf /app/ComfyUI/models
ln -s /workspace/models /app/ComfyUI/models

# Run ComfyUI with multi-user + stable frontend (forcing CPU mode)
exec python /app/ComfyUI/main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --cpu \
    --multi-user \
    --front-end-version Comfy-Org/ComfyUI_frontend@v1.48.4 \
    --output-directory /workspace/output \
    --input-directory /workspace/input \
    --user-directory /workspace/user \
    "$@"