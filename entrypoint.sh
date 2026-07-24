#!/bin/bash
set -e

# Setup workspace directories
mkdir -p /workspace/custom_nodes
mkdir -p /workspace/models
mkdir -p /workspace/output
mkdir -p /workspace/input
mkdir -p /workspace/user
mkdir -p /workspace/temp

# Copy defaults if empty
if [ -z "$(ls -A /workspace/custom_nodes 2>/dev/null)" ]; then
    echo "Initializing default custom_nodes (incl. ComfyUI-Manager + API nodes)..."
    cp -r /app/ComfyUI/custom_nodes_default/. /workspace/custom_nodes/
else
    # Sync: copy any nodes from snapshot that aren't in the volume yet
    echo "Syncing new custom_nodes from image snapshot..."
    for node_dir in /app/ComfyUI/custom_nodes_default/*/; do
        node_name=$(basename "$node_dir")
        if [ ! -d "/workspace/custom_nodes/$node_name" ]; then
            echo "  + Installing $node_name"
            cp -r "$node_dir" "/workspace/custom_nodes/$node_name"
        fi
    done
fi

if [ -z "$(ls -A /workspace/models 2>/dev/null)" ]; then
    echo "Initializing default models folder structure..."
    cp -r /app/ComfyUI/models_default/. /workspace/models/
fi

# Ensure permissions
chown -R root:root /workspace || true
chmod -R 777 /workspace || true

# Create symlinks
rm -rf /app/ComfyUI/custom_nodes
ln -s /workspace/custom_nodes /app/ComfyUI/custom_nodes

rm -rf /app/ComfyUI/models
ln -s /workspace/models /app/ComfyUI/models

rm -rf /app/ComfyUI/user
ln -s /workspace/user /app/ComfyUI/user
# Clear old frontend cache to force re-download of the pinned version
# (pitfall #50 — old volumes keep stale frontend despite --front-end-version bump)
# Note: we do NOT delete /app/ComfyUI/web_custom_versions because it contains our pre-baked v1.48.4 to avoid GitHub API rate limits
rm -rf /root/.cache/comfyui /workspace/web 2>/dev/null || true

# Run ComfyUI with server optimization flags (no --multi-user — single user only)
# NOTE: --front-end-version v1.48.5 requires ComfyUI master (not v0.28.0).
# v0.28.0 + embedded v1.45.21 has a "graph accessed before initialization" bug
# that prevents the Vue topbar/sidebar from rendering.
exec python /app/ComfyUI/main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --cpu \
    --enable-manager \
    --enable-cors-header \
    --enable-compress-response-body \
    --max-upload-size 100 \
    --front-end-version Comfy-Org/ComfyUI_frontend@v1.48.4 \
    --output-directory /workspace/output \
    --input-directory /workspace/input \
    --user-directory /workspace/user \
    --models-directory /workspace/models \
    --temp-directory /workspace/temp \
    "$@"