FROM public.ecr.aws/docker/library/python:3.11-slim

# Install system dependencies
RUN apt-get -o Acquire::AllowInsecureRepositories=true \
    -o Acquire::AllowDowngradeToInsecureRepositories=true \
    update && apt-get install -y --no-install-recommends \
    git \
    curl \
    unzip \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU (conditional by architecture to support multi-platform buildx)
ARG TARGETARCH
RUN if [ "$TARGETARCH" = "arm64" ]; then \
        pip install --no-cache-dir torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1; \
    else \
        pip install --no-cache-dir torch==2.5.1+cpu torchvision==0.20.1+cpu torchaudio==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu; \
    fi

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

# Pin transformers and huggingface_hub to prevent KeyError: 'default' on Qwen3-VL/CLIP loaders
RUN pip install --no-cache-dir transformers==4.57.3 "huggingface_hub>=0.34.0,<1.0"

# Install bcrypt for auth
RUN pip install --no-cache-dir bcrypt

# Copy auth files
COPY auth/ /app/ComfyUI/auth/

# Copy pre-bundled frontend v1.48.4
COPY web_custom/1.48.4 /app/ComfyUI/web_custom_versions/Comfy-Org_ComfyUI_frontend/1.48.4

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

# 4. ComfyUI-Gemini-Antigravity — Gemini-native image generation via NexusMind Antigravity proxy
COPY custom_nodes/ComfyUI-Gemini-Antigravity/__init__.py /app/ComfyUI/custom_nodes/ComfyUI-Gemini-Antigravity/__init__.py

# 5. ComfyUI-NexusVideo — Grok video generation (text-to-video & image-to-video) via NexusMind sub2api
COPY custom_nodes/ComfyUI-NexusVideo/__init__.py /app/ComfyUI/custom_nodes/ComfyUI-NexusVideo/__init__.py

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