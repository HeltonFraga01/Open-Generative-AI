# ADR-0004: Entrypoint instala deps de custom nodes em runtime

**Date:** 2026-07-25
**Status:** Accepted

## Context

Custom nodes instalados via ComfyUI-Manager em produção persistem no volume `/workspace/custom_nodes/` (volume Docker nomeado). Esses nodes podem ter dependências Python que não estão na imagem Docker base.

**Problema:** O `llm-toolkit` (instalado via Manager) depende de `google-genai`, que não está na imagem. Ao reiniciar o container, o ComfyUI falhava ao carregar o node com `ModuleNotFoundError: No module named 'google'`.

A solução naive seria adicionar todas as deps de todos os nodes possíveis no Dockerfile, mas isso incharia a imagem com packages que podem nunca ser usados.

## Decision

O `entrypoint.sh` tem um bloco **antes de iniciar o ComfyUI** que verifica se cada custom node instalado no volume tem deps conhecidas e as instala via `pip install`:

```bash
if [ -d /workspace/custom_nodes/llm-toolkit ]; then
    echo "Installing llm-toolkit runtime deps (google-genai)..."
    pip install --no-cache-dir google-genai 2>/dev/null || true
fi
```

### Nodes cobertos (atualmente)

| Custom node | Dep necessária | Padrão de detecção |
|---|---|---|
| `llm-toolkit` | `google-genai` | `/workspace/custom_nodes/llm-toolkit` existe |

### Como adicionar um novo node com deps

1. Adicione um bloco `if [ -d /workspace/custom_nodes/<nome> ]; then` no entrypoint
2. Liste as deps com `pip install --no-cache-dir <dep>`
3. Faça build de nova imagem e deploy

## Consequences

- **Positivas:** Nodes instalados via Manager em runtime funcionam mesmo se não estiverem no Dockerfile
- **Negativas:** Cada boot leva ~10s extra para `pip install`. Se pacote não estiver no PyPI cache, depende de internet
- **Limitação:** Se o node não tem reconhecimento no entrypoint, suas deps não serão instaladas — `ModuleNotFoundError` aparecerá nos logs e o node não carrega (mas o resto do ComfyUI funciona normalmente)
