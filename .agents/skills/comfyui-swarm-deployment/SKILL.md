---
name: comfyui-swarm-deployment
description: Guides building custom ComfyUI CPU images, deploying to Portainer Swarm, configuring Traefik Basic Auth, and connecting AI agents via ComfyUI MCP.
---

# ComfyUI Swarm Deployment and MCP Integration

## Overview

This skill guides the process of building, securing, deploying, and integrating a CPU-only **ComfyUI** instance on a Docker Swarm cluster (managed by Portainer), and connecting it to developer agents (Cursor, Claude Desktop) via the **Model Context Protocol (MCP)**.

### Target Environment Facts:
*   **Cluster Nodes**: 1 manager node (`manager01`).
*   **Operating System**: Linux.
*   **Architecture**: `x86_64` (linux/amd64) - CPU-only (no NVIDIA CUDA).
*   **Domain**: `comfyui.nexusmind.digital` (routed via Traefik reverse proxy).

---

## 📦 Custom Docker Image Architecture

Using bloated default images (like `ai-dock` over 6GB with SSH/Syncthing/Caddy/Jupyter/Quicktunnels) represents a security risk and causes system crashes. We use a custom, lightweight (approx. 1.2GB) Docker image built directly on top of the official Python slim image.

### 1. The `Dockerfile`
This setup pre-installs the new official **ComfyUI-Frontend v2** (built on Vue 3 + PrimeVue) and pins Python dependencies to prevent version mismatches (e.g. `torchaudio` crashing due to `undefined symbol: aoti_torch_abi_version`).

```dockerfile
FROM public.ecr.aws/docker/library/python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU (pinned versions for compatibility)
RUN pip install --no-cache-dir torch==2.5.1+cpu torchvision==0.20.1+cpu torchaudio==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu

# Clone ComfyUI at stable tag v0.28.0
RUN git clone --branch v0.28.0 https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

# Clone ComfyUI-Manager at stable tag 4.2.2
RUN cd /app/ComfyUI/custom_nodes && \
    git clone --branch 4.2.2 https://github.com/ltdrdata/ComfyUI-Manager.git

# Install ComfyUI dependencies
WORKDIR /app/ComfyUI
RUN pip install --no-cache-dir -r requirements.txt

# Install ComfyUI-Manager dependencies
RUN pip install --no-cache-dir -r custom_nodes/ComfyUI-Manager/requirements.txt

# Copy auth patch files (multi-user with password)
COPY auth/ /app/ComfyUI/auth/
COPY auth/migrations/20260723_create_auth_users.py /app/ComfyUI/alembic_db/versions/
RUN cp /app/ComfyUI/auth/models.py /app/ComfyUI/app/database/auth_models.py

# Install bcrypt for secure password hashing
RUN pip install --no-cache-dir bcrypt

# Backup default structures before symlinking (includes ComfyUI-Manager)
RUN cp -r /app/ComfyUI/custom_nodes /app/ComfyUI/custom_nodes_default && \
    cp -r /app/ComfyUI/models /app/ComfyUI/models_default

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose port
EXPOSE 8188

ENTRYPOINT ["/entrypoint.sh"]
```

### 2. The `entrypoint.sh`
This script dynamically sets up directories on container boot, copying default nodes and models to the persistent mount folder (`/workspace/`) if empty, then symlinking them back to `/app/ComfyUI/`.

```bash
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

# Run ComfyUI with multi-user + stable frontend (no --cpu)
exec python /app/ComfyUI/main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --multi-user \
    --front-end-version Comfy-Org/ComfyUI_frontend@v1.48.4 \
    --output-directory /workspace/output \
    --input-directory /workspace/input \
    --user-directory /workspace/user \
    "$@"
```

---

## 🛠️ Build and Push Commands

To avoid running out of disk space on a developer Mac's Docker virtual disk (`ResourceExhausted` / `No space left on device`), compile **exclusively** for the production platform (`linux/amd64`) instead of building a multi-platform image.

### Build Checklist:
1.  **Prune Docker cache** to free up disk space:
    ```bash
    docker system prune -a -f --volumes
    docker builder prune -a -f
    docker buildx prune --all --force
    ```
2.  **Run Buildx build** targeting single-platform `linux/amd64` and push to Docker Hub:
    ```bash
    docker buildx build --platform linux/amd64 -t heltonfraga/comfyui:latest -f Dockerfile --push .
    ```

---

## 🌐 Portainer Swarm Deploy & Security

Exposing ComfyUI publicly without authentication is a massive security loophole. We route traffic through Traefik and apply a **Basic Authentication Middleware** at the Swarm label level.

### Docker Compose Stack Spec (`deploy/comfyui.yaml`)
```yaml
version: '3.8'

services:
  comfyui:
    image: heltonfraga/comfyui:latest
    environment:
      - WEB_ENABLE_AUTH=false
      # API keys for external generation (Gemini, Fal, OmniRoute)
      - GEMINI_API_KEY=${GEMINI_API_KEY:-}
      - FAL_API_KEY=${FAL_API_KEY:-}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - OPENAI_BASE_URL=${OPENAI_BASE_URL:-https://omniroute.cortexx.online/v1}
      # Database (default SQLite in user directory)
      - DATABASE_URL=sqlite:////workspace/user/comfyui.db
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
        # ── Autenticação Básica (HARDCODED diretamente para resiliência no Portainer) ──
        # A senha gerada abaixo para 'nexusmind' é 'NexusGenerative2026!'
        - "traefik.http.middlewares.comfyui-auth.basicauth.users=nexusmind:$$apr1$$z5AMyJ1b$$XPkqxwBmT2foH8w8yjdOx."
        - "traefik.http.routers.comfyui.middlewares=comfyui-auth"

volumes:
  comfyui_workspace_v2:

networks:
  network_public:
    external: true
```

> [!IMPORTANT]
> **Escape Double Dollars ($$)**: Traefik labels in Docker Compose YAML require escaping every dollar sign `$` in hashed passwords as `$$`. If not escaped, Docker Compose attempts to interpolate them as environment variables, which breaks the password hash.

---

## 🔌 Connecting Agents via MCP (Model Context Protocol)

The MCP server connects Cursor or Claude Desktop to the remote ComfyUI instance to execute image/video generation workflows.

### ⚠️ Chromium Security Limitation:
When opening the ComfyUI site in the browser, **do not** use embedded credentials in the URL bar (e.g. `https://user:pass@comfyui...`).
Modern Chromium browsers block JavaScript sub-resource fetching (`fetch('/users')`) when the main window's URL has embedded credentials. This causes the Vue 3 app to throw an uncaught TypeError and freeze. 
**Access the URL directly (`https://comfyui.nexusmind.digital`) and enter credentials in the browser prompt.**

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
        *   `COMFYUI_AUTH_SCHEME` = `Basic`
        *   `COMFYUI_AUTH_TOKEN` = `bmV4dXNtaW5kOk5leHVzR2VuZXJhdGl2ZTIwMjYh` (Note: base64 of username:password)

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
        "COMFYUI_AUTH_SCHEME": "Basic",
        "COMFYUI_AUTH_TOKEN": "bmV4dXNtaW5kOk5leHVzR2VuZXJhdGl2ZTIwMjYh"
      }
    }
  }
}
```

---

## 🔍 Diagnostics & Verification Commands

### 1. Check HTTP Health & Login Authentication
Verify the endpoint responds with 401 (unauthorized) normally, and 200 (ok) with proper credentials:
```bash
# Devem retornar 401 Unauthorized
curl -I https://comfyui.nexusmind.digital/

# Deve retornar 200 OK
curl -I -u nexusmind:NexusGenerative2026! https://comfyui.nexusmind.digital/
```

### 2. Monitor Container Swarm Logs & Task State
```bash
# Listar tarefas Swarm ativas para o serviço
PORTAINER_ENV_FILE=~/.config/cortexx/portainer.env node scripts/portainer-cli.mjs logs --endpointId=1 --serviceId=<id_do_servico> --tail=100
```

---

## ⚠️ Common Pitfalls

*   **ComfyUI-MCP Auth Limitation**: The NPM package `comfyui-mcp` discards embedded credentials (e.g. `user:pass@host`) from `COMFYUI_URL` inside its internal URL parser. To pass credentials to a reverse proxy requiring Basic Auth (like Traefik), you **must** configure `COMFYUI_AUTH_HEADER=Authorization`, `COMFYUI_AUTH_SCHEME=Basic`, and `COMFYUI_AUTH_TOKEN=<base64_encoded_credentials>`.
*   **CPU Flag Obligatory**: If running on CPU-only hosts, the `--cpu` flag is **absolutely mandatory** in the python launch command. Without it, PyTorch falls back to GPU/CUDA checks and throws a fatal `AssertionError: Torch not compiled with CUDA enabled`.
*   **Database Initialisation Permission Error**: If the SQLite database fails to initialize (`unable to open database file`), the server will crash with `KeyError: 'Unknown user: default'` in multi-user mode. Fix it by running `chown -R root:root /workspace` and `chmod -R 777 /workspace` on container start, and symlink `/app/ComfyUI/user` to `/workspace/user` instead of using the `--user-directory` CLI parameter.
*   **Docker Desktop VM Out of Disk**: Multi-platform builds (amd64 + arm64) cache massive compilation libraries. Always prune cache (`docker system prune -a --volumes` and `docker builder prune -a`) before rebuilding.
*   **PyTorch version mismatch**: If updating PyTorch, ensure `torch`, `torchvision`, and `torchaudio` versions are manually pinned to matching releases (e.g. `2.5.1+cpu`) to avoid undefined ABI symbols at launch.
*   **Traefik Basic Auth Unescaped Passwords**: Always verify that the htpasswd string inside the YAML contains `$$` instead of `$`.

