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

# Install runtime deps for custom nodes that were installed via Manager
# These are NOT in the Dockerfile because the nodes are installed in a volume at runtime
if [ -d /workspace/custom_nodes/llm-toolkit ]; then
    echo "Installing llm-toolkit runtime deps (google-genai)..."
    pip install --no-cache-dir google-genai 2>/dev/null || true
fi

# Patch: add video dimensions enrichment to ComfyUI assets system
# The stock asset enrichment only sets kind=image for image/* MIME types.
# This patch adds kind=video for video/* MIME types using ffprobe.
if [ ! -f /app/ComfyUI/app/assets/services/video_dimensions.py ]; then
    echo "Installing video dimensions enrichment patch..."
    cat > /app/ComfyUI/app/assets/services/video_dimensions.py << 'VD_EOF'
"""Video dimension and metadata extraction for asset ingest."""
from __future__ import annotations
import json, logging, shutil, subprocess
from typing import Any
logger = logging.getLogger(__name__)
def extract_video_dimensions(file_path, mime_type=None):
    if mime_type is not None and not mime_type.startswith("video/"):
        return None
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run([ffprobe, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", file_path], capture_output=True, timeout=10)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
    except Exception:
        return None
    vs = None
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            vs = s; break
    if not vs:
        return None
    w, h = int(vs.get("width", 0)), int(vs.get("height", 0))
    if w <= 0 or h <= 0:
        return None
    dur = None
    ds = data.get("format", {}).get("duration") or vs.get("duration")
    if ds:
        try: dur = round(float(ds), 2)
        except: pass
    meta = {"kind": "video", "width": w, "height": h}
    if dur is not None: meta["duration"] = dur
    return meta
VD_EOF

    # Patch ingest.py to import and use video_dimensions
    if ! grep -q 'video_dimensions' /app/ComfyUI/app/assets/services/ingest.py; then
        sed -i '/from app.assets.services.image_dimensions import extract_image_dimensions/a from app.assets.services.video_dimensions import extract_video_dimensions' /app/ComfyUI/app/assets/services/ingest.py
    fi

    # Replace the image-only check with image+video check
    sed -i 's/if not mime_type or not mime_type.startswith("image\/"):/if not mime_type:/' /app/ComfyUI/app/assets/services/ingest.py
    sed -i 's/dims = extract_image_dimensions(file_path, mime_type=mime_type)/dims = extract_image_dimensions(file_path, mime_type=mime_type) if mime_type.startswith("image\/") else extract_video_dimensions(file_path, mime_type=mime_type)/' /app/ComfyUI/app/assets/services/ingest.py
fi

# Re-enrich existing MP4s in the DB (in case they were registered before the patch)
if [ -f /workspace/user/comfyui.db ] && [ -f /app/ComfyUI/app/assets/services/video_dimensions.py ]; then
    python3 -c "
import sqlite3, json, glob, os, sys
sys.path.insert(0, '/app/ComfyUI')
try:
    from app.assets.services.video_dimensions import extract_video_dimensions
    conn = sqlite3.connect('/workspace/user/comfyui.db')
    c = conn.cursor()
    rows = c.execute(\"SELECT id, file_path, system_metadata FROM asset_references WHERE name LIKE '%.mp4'\").fetchall()
    for ref_id, fp, sm in rows:
        dims = extract_video_dimensions(fp, mime_type='video/mp4')
        if dims:
            current = json.loads(sm) if sm else {}
            if current.get('kind') != 'video':
                current.update(dims)
                c.execute('UPDATE asset_references SET system_metadata=?, enrichment_level=2 WHERE id=?', (json.dumps(current), ref_id))
    conn.commit()
    conn.close()
except Exception:
    pass
" 2>/dev/null || true
fi

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