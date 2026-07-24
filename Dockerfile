FROM public.ecr.aws/docker/library/python:3.11-slim

# Install system dependencies
RUN apt-get -o Acquire::AllowInsecureRepositories=true \
    -o Acquire::AllowDowngradeToInsecureRepositories=true \
    update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU (pinned — latest 2.13.x is too large for buildx QEMU)
RUN pip install --no-cache-dir torch==2.5.1+cpu torchvision==0.20.1+cpu torchaudio==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu

# Clone ComfyUI — master branch (required for frontend v1.48.5 compatibility)
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

# ComfyUI-Manager 4.2.2 — pip-installable package (NO root __init__.py)
RUN git clone --branch 4.2.2 --depth 1 https://github.com/Comfy-Org/ComfyUI-Manager.git /tmp/ComfyUI-Manager && \
    pip install --no-cache-dir /tmp/ComfyUI-Manager && \
    cp -r /tmp/ComfyUI-Manager /app/ComfyUI/custom_nodes/ComfyUI-Manager && \
    rm -rf /tmp/ComfyUI-Manager

# Install ComfyUI dependencies
WORKDIR /app/ComfyUI
RUN pip install --no-cache-dir -r requirements.txt

# Install bcrypt for auth
RUN pip install --no-cache-dir bcrypt

# Copy auth files
COPY auth/ /app/ComfyUI/auth/

# Patch server.py to inject auth middleware (no cache to force re-patch)
RUN python /app/ComfyUI/auth/patch_server.py && cat /app/ComfyUI/server.py | grep -A2 "AUTH ROUTES"

# Backup default structures before symlinking
RUN cp -r /app/ComfyUI/custom_nodes /app/ComfyUI/custom_nodes_default && \
    cp -r /app/ComfyUI/models /app/ComfyUI/models_default

# Install OpenAI-compatible custom nodes for OmniRoute/NexusMind integration
# 1. ComfyUI-AI-CustomURL — text, image, video, audio, speech (any OpenAI-compatible endpoint)
RUN git clone --depth 1 https://github.com/bowtiedbluefin/ComfyUI-AI-CustomURL.git /app/ComfyUI/custom_nodes/ComfyUI-AI-CustomURL && \
    cd /app/ComfyUI/custom_nodes/ComfyUI-AI-CustomURL && pip install --no-cache-dir -r requirements.txt || true

# 2. comfyui-openai-llm — MCP tools, image input, lightweight OpenAI-compatible
RUN git clone --depth 1 https://github.com/godmt/comfyui-openai-llm.git /app/ComfyUI/custom_nodes/comfyui-openai-llm && \
    cd /app/ComfyUI/custom_nodes/comfyui-openai-llm && pip install --no-cache-dir -r requirements.txt || true

# 3. ComfyUI-YALLM-node — multi-modal, local/remote OpenAI-like APIs
RUN git clone --depth 1 https://github.com/asaddi/ComfyUI-YALLM-node.git /app/ComfyUI/custom_nodes/ComfyUI-YALLM-node && \
    cd /app/ComfyUI/custom_nodes/ComfyUI-YALLM-node && pip install --no-cache-dir -r requirements.txt || true

# Re-snapshot custom_nodes to include the new nodes for volume init
# Use /. to copy CONTENTS (not the dir itself) — avoids custom_nodes/custom_nodes/ bug
RUN rm -rf /app/ComfyUI/custom_nodes_default && \
    mkdir -p /app/ComfyUI/custom_nodes_default && \
    cp -r /app/ComfyUI/custom_nodes/. /app/ComfyUI/custom_nodes_default/

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8188

ENTRYPOINT ["/entrypoint.sh"]