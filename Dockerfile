FROM public.ecr.aws/docker/library/python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU (latest stable)
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Clone ComfyUI repository
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

# Install ComfyUI dependencies
WORKDIR /app/ComfyUI
RUN pip install --no-cache-dir -r requirements.txt

# Install ComfyUI Frontend package
RUN pip install --no-cache-dir comfyui-frontend-package --upgrade

# Backup default structures before symlinking
RUN cp -r /app/ComfyUI/custom_nodes /app/ComfyUI/custom_nodes_default && \
    cp -r /app/ComfyUI/models /app/ComfyUI/models_default

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose port
EXPOSE 8188

ENTRYPOINT ["/entrypoint.sh"]
