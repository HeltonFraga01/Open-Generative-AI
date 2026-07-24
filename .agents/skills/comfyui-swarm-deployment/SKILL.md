---
name: comfyui-swarm-deployment
description: Guides building custom ComfyUI CPU images, deploying to Portainer Swarm, configuring Native Auth, and connecting AI agents via ComfyUI MCP using Bearer Token.
---

# ComfyUI Swarm Deployment and MCP Integration

## Overview

This skill guides the process of building, securing, deploying, and integrating a CPU-only **ComfyUI** instance on a Docker Swarm cluster (managed by Portainer), and connecting it to developer agents (Cursor, Claude Desktop) via the **Model Context Protocol (MCP)** using native Token-based authentication.

### Target Environment Facts:
*   **Cluster Nodes**: 1 manager node (`manager01`).
*   **Operating System**: Linux.
*   **Architecture**: `x86_64` (linux/amd64) - CPU-only (no NVIDIA CUDA).
*   **Domain**: `comfyui.nexusmind.digital` (routed via Traefik reverse proxy).

---

## 📦 Custom Docker Image Architecture

Using bloated default images (like `ai-dock` over 6GB with SSH/Syncthing/Caddy/Jupyter/Quicktunnels) represents a security risk and causes system crashes. We use a custom, lightweight (approx. 1.2GB) Docker image built directly on top of the official Python slim image.

### 1. The `Dockerfile`
This setup pre-installs the new official **ComfyUI-Frontend** (Vue 3 based), pins PyTorch CPU versions, and strictly pins the `transformers` library to support Qwen3-VL/CLIP loaders.

```dockerfile
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

# Clone ComfyUI at latest stable tag
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

# ComfyUI-Manager 4.2.2 — pip-installable package
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

# Clone other custom nodes (ComfyUI-AI-CustomURL, comfyui-openai-llm, ComfyUI-YALLM-node)
RUN git clone --depth 1 https://github.com/cortexx-cloud/ComfyUI-AI-CustomURL.git /app/ComfyUI/custom_nodes/ComfyUI-AI-CustomURL && \
    cd /app/ComfyUI/custom_nodes/ComfyUI-AI-CustomURL && pip install --no-cache-dir -r requirements.txt || true

RUN git clone --depth 1 https://github.com/cortexx-cloud/comfyui-openai-llm /app/ComfyUI/custom_nodes/comfyui-openai-llm && \
    cd /app/ComfyUI/custom_nodes/comfyui-openai-llm && pip install --no-cache-dir -r requirements.txt || true

RUN git clone --depth 1 https://github.com/asaddi/ComfyUI-YALLM-node.git /app/ComfyUI/custom_nodes/ComfyUI-YALLM-node && \
    cd /app/ComfyUI/custom_nodes/ComfyUI-YALLM-node && pip install --no-cache-dir -r requirements.txt || true

# Backup default structures before symlinking
RUN rm -rf /app/ComfyUI/custom_nodes_default && \
    mkdir -p /app/ComfyUI/custom_nodes_default && \
    cp -r /app/ComfyUI/custom_nodes/. /app/ComfyUI/custom_nodes_default/

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8188
ENTRYPOINT ["/entrypoint.sh"]
```

### 2. The `entrypoint.sh`
This script dynamically sets up directories on container boot, copying default nodes to the persistent mount folder (`/workspace/`) if empty, adjusting directory permissions to avoid SQLite locks, and starting the ComfyUI server.

```bash
#!/bin/bash
set -e

# Setup workspace directories
mkdir -p /workspace/custom_nodes
mkdir -p /workspace/models
mkdir -p /workspace/output
mkdir -p /workspace/input
mkdir -p /workspace/user

# Copy defaults if empty
if [ -z "$(ls -A /workspace/custom_nodes 2>/dev/null)" ]; then
    echo "Initializing default custom_nodes..."
    cp -r /app/ComfyUI/custom_nodes_default/. /workspace/custom_nodes/
fi

# Apply broad permissions to avoid SQLite DB locking or KeyError: 'Unknown user: default'
chown -R root:root /workspace
chmod -R 777 /workspace

# Symlinks mapping
rm -rf /app/ComfyUI/custom_nodes
ln -s /workspace/custom_nodes /app/ComfyUI/custom_nodes

rm -rf /app/ComfyUI/models
ln -s /workspace/models /app/ComfyUI/models

# Symlink user directory to solve SQLite user DB issues
rm -rf /app/ComfyUI/user
ln -s /workspace/user /app/ComfyUI/user

# Run ComfyUI on CPU
exec python /app/ComfyUI/main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --cpu \
    --enable-manager \
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
```

---

## 🛠️ Build and Push Commands

To avoid running out of disk space on a developer Mac's Docker virtual disk (`ResourceExhausted` / `No space left on device`) or QEMU emulation memory crashes (OOM), compile **exclusively** for the production platform (`linux/amd64`) instead of building a multi-platform image.

### Build Checklist:
1.  **Prune Docker cache** to free up disk space:
    ```bash
    docker system prune -a -f --volumes
    docker builder prune -a -f
    ```
2.  **Run Buildx build** targeting single-platform `linux/amd64` and push to Docker Hub:
    ```bash
    docker buildx build --platform linux/amd64 -t heltonfraga/comfyui:v0.28.0-v12 -t heltonfraga/comfyui:latest -f Dockerfile --push .
    ```

---

## 🌐 Portainer Swarm Deploy & Native Auth

ComfyUI native multi-user authentication (`COMFYUI_AUTH_ENABLED=true`) handles security. We route traffic through Traefik without Traefik basicauth layers to allow seamless Bearer token header authorization.

### Docker Compose Stack Spec (`deploy/comfyui.yaml`)
```yaml
version: '3.8'

services:
  comfyui:
    image: heltonfraga/comfyui:v0.28.0-v12
    # ── chaves (HARDCODED diretamente na Spec YAML para resiliência no Portainer) ──
    # ATENÇÃO: NÃO extraia estas chaves para variáveis de ambiente na interface do Portainer (Stack Env).
    # Caso contrário, re-deploys de imagem apagarão as variáveis e quebrarão a criptografia/autenticação.
    environment:
      - COMFYUI_AUTH_ENABLED=true
      - COMFYUI_DEFAULT_USER=nexusmind
      # Hash bcrypt para a senha 'NexusGenerative2026!'
      - "COMFYUI_DEFAULT_PASS_HASH=$$2b$$12$$QRgFSxlS67QPl4CbQXoakOP24Fia7pnUBqlrZYvQzNHQ5nQf7BlDW"
      # Token estático para acesso do MCP e APIs programáticas
      - COMFYUI_API_TOKEN=zvztFnf9gNUkURYu7hYkKJlS5nFqpseSbo-jJ2q9chs
      - DATABASE_URL=sqlite:////workspace/user/comfyui.db
      - OPENAI_API_KEY=sk-placeholder
      - OPENAI_BASE_URL=https://omniroute.cortexx.online/v1
    volumes:
      - comfyui_workspace_v2:/workspace
    networks:
      - network_public
    deploy:
      mode: replicated
      replicas: 1
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
      labels:
        - "traefik.enable=true"
        - "traefik.docker.network=network_public"
        - "traefik.http.routers.comfyui.entrypoints=websecure"
        - "traefik.http.routers.comfyui.rule=Host(`comfyui.nexusmind.digital`)"
        - "traefik.http.routers.comfyui.priority=200"
        - "traefik.http.routers.comfyui.tls=true"
        - "traefik.http.routers.comfyui.tls.certresolver=letsencryptresolver"
        - "traefik.http.services.comfyui.loadbalancer.server.port=8188"

volumes:
  comfyui_workspace_v2:

networks:
  network_public:
    external: true
```

> [!IMPORTANT]
> **Escape Double Dollars ($$)**: ComfyUI environment values containing a dollar sign `$` (like the bcrypt pass hash) require escaping in Docker Compose YAML as `$$`. If not escaped, Docker Compose attempts to interpolate them as empty variables, which corrupts the hash.

---

## 🔌 Connecting Agents via MCP (Model Context Protocol)

The MCP server connects Cursor or Claude Desktop to the remote ComfyUI instance to execute image/video generation workflows.

### 1. Cursor Setup
1.  Navigate to **Settings > Features > MCP**.
2.  Click **+ Add New MCP Server**.
3.  Fill in the configuration:
    *   **Name**: `comfyui`
    *   **Type**: `command`
    *   **Command**: `npx -y comfyui-mcp`
    *   **Environment Variables**:
        *   `COMFYUI_URL` = `https://comfyui.nexusmind.digital`
        *   `COMFYUI_AUTH_HEADER` = `Authorization`
        *   `COMFYUI_AUTH_SCHEME` = `Bearer`
        *   `COMFYUI_AUTH_TOKEN` = `zvztFnf9gNUkURYu7hYkKJlS5nFqpseSbo-jJ2q9chs`

### 2. Claude Desktop Setup
Open `~/Library/Application Support/Claude/claude_desktop_config.json` and add the service:
```json
{
  "mcpServers": {
    "comfyui": {
      "command": "npx",
      "args": ["-y", "comfyui-mcp"],
      "env": {
        "COMFYUI_URL": "https://comfyui.nexusmind.digital",
        "COMFYUI_AUTH_HEADER": "Authorization",
        "COMFYUI_AUTH_SCHEME": "Bearer",
        "COMFYUI_AUTH_TOKEN": "zvztFnf9gNUkURYu7hYkKJlS5nFqpseSbo-jJ2q9chs"
      }
    }
  }
}
```

---

## 🔍 Diagnostics & Verification Commands

### 1. Check HTTP Health & Login Authentication
Verify the endpoint responds with 200 (ok) and requests credentials normally:
```bash
# Test authentication flow and session cookie retrieval
curl -c cookies.txt -s -X POST -H "Content-Type: application/json" -d '{"username":"nexusmind","password":"NexusGenerative2026!"}' https://comfyui.nexusmind.digital/api/auth/login
# Response should be: {"success": true, "user": "nexusmind"}
```

### 2. Check System Statistics via Bearer Token
```bash
# Query the system stats API endpoint using the Bearer token
curl -s -H "Authorization: Bearer zvztFnf9gNUkURYu7hYkKJlS5nFqpseSbo-jJ2q9chs" https://comfyui.nexusmind.digital/system_stats
```

---

## ⚠️ Common Pitfalls

*   **Transformers v5.x Incompatibility**: HuggingFace `transformers` v5.0.0+ removes the `'default'` initializer key from `ROPE_INIT_FUNCTIONS`. This causes models like Qwen3-VL or CLIP loaders to crash on load with `KeyError: 'default'`. To resolve this, **strictly pin transformers to 4.57.3** and `huggingface_hub` to `<1.0`.
*   **ComfyUI-MCP Auth Limitation**: The NPM package `comfyui-mcp` discards embedded credentials (e.g. `user:pass@host`) from `COMFYUI_URL` inside its internal URL parser. To pass credentials, always configure `COMFYUI_AUTH_HEADER=Authorization`, `COMFYUI_AUTH_SCHEME=Bearer`, and `COMFYUI_AUTH_TOKEN=<api_token>`.
*   **CPU Flag Obligatory**: If running on CPU-only hosts, the `--cpu` flag is **absolutely mandatory** in the python launch command. Without it, PyTorch falls back to GPU/CUDA checks and throws a fatal `AssertionError: Torch not compiled with CUDA enabled`.
*   **Database Initialisation Permission Error**: If the SQLite database fails to initialize (`unable to open database file`), the server will crash with `KeyError: 'Unknown user: default'` in multi-user mode. Fix it by running `chown -R root:root /workspace` and `chmod -R 777 /workspace` on container start, and symlinking `/app/ComfyUI/user` to `/workspace/user` instead of using the `--user-directory` CLI parameter.
*   **Docker Desktop VM Out of Disk**: Multi-platform builds (amd64 + arm64) cache massive compilation libraries. Always prune cache (`docker system prune -a --volumes` and `docker builder prune -a`) before rebuilding.
*   **PyTorch version mismatch**: If updating PyTorch, ensure `torch`, `torchvision`, and `torchaudio` versions are manually pinned to matching releases (e.g. `2.5.1+cpu`) to avoid undefined ABI symbols at launch.
