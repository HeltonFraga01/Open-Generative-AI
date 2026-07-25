#!/bin/bash
set -e

# Setup workspace directories
mkdir -p /workspace/custom_nodes
mkdir -p /workspace/models
mkdir -p /workspace/output
mkdir -p /workspace/input
mkdir -p /workspace/user/default
mkdir -p /workspace/temp

mkdir -p /workspace/user/default
cat << 'EOF' > /workspace/user/default/comfy.settings.json
{
    "Comfy.InstalledVersion": "1.48.4",
    "Comfy.TutorialCompleted": true,
    "Comfy.VueNodes.Enabled": true,
    "Comfy.UseNewMenu": "Top",
    "Comfy.MenuPosition.Docked": true
}
EOF

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

mkdir -p /workspace/user/default /workspace/user/workflows /workspace/user/subgraphs
mkdir -p /workspace/user/__manager

# Ensure Manager config.ini has personal_cloud + allow installs
if [ ! -f /workspace/user/__manager/config.ini ]; then
    echo "Installing ComfyUI-Manager config.ini (personal_cloud, allow installs)..."
    cp /tmp/manager_config.ini /workspace/user/__manager/config.ini
else
    # Patch existing config: set network_mode and allow installs
    sed -i 's/^network_mode = .*/network_mode = personal_cloud/' /workspace/user/__manager/config.ini 2>/dev/null || true
    sed -i 's/^allow_git_url_install = .*/allow_git_url_install = True/' /workspace/user/__manager/config.ini 2>/dev/null || true
    sed -i 's/^allow_pip_install = .*/allow_pip_install = True/' /workspace/user/__manager/config.ini 2>/dev/null || true
    # If keys don't exist, append them
    grep -q '^network_mode' /workspace/user/__manager/config.ini || echo 'network_mode = personal_cloud' >> /workspace/user/__manager/config.ini
    grep -q '^allow_git_url_install' /workspace/user/__manager/config.ini || echo 'allow_git_url_install = True' >> /workspace/user/__manager/config.ini
    grep -q '^allow_pip_install' /workspace/user/__manager/config.ini || echo 'allow_pip_install = True' >> /workspace/user/__manager/config.ini
fi

# Ensure permissions on Manager config
chmod 777 /workspace/user/__manager/config.ini 2>/dev/null || true
if [ ! -f /workspace/user/comfy.templates.json ]; then
    echo "[]" > /workspace/user/comfy.templates.json
fi

rm -rf /root/.cache/comfyui /workspace/web 2>/dev/null || true

# Run ComfyUI with server optimization flags (no --multi-user — single user only)
exec python /app/ComfyUI/main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --cpu \
    --enable-manager \
    --enable-assets \
    --enable-cors-header \
    --enable-compress-response-body \
    --max-upload-size 100 \
    --front-end-root /app/ComfyUI/web_custom_versions/Comfy-Org_ComfyUI_frontend/1.48.4 \
    --output-directory /workspace/output \
    --input-directory /workspace/input \
    --user-directory /workspace/user \
    --models-directory /workspace/models \
    --temp-directory /workspace/temp \
    "$@"