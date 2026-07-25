# ADR-0005: Patch de enriquecimento de vídeo (kind=video) via ffprobe

**Date:** 2026-07-25
**Status:** Accepted

## Context

O ComfyUI v0.28.0 tem um sistema de assets (`--enable-assets`) que rastreia arquivos de output em um banco SQLite (`comfyui.db`). Cada asset recebe metadados enriquecidos (`kind`, `width`, `height`, `duration`).

**Problema:** O enriquecimento stock só lida com imagens (`image/*`). A função `_maybe_store_image_dimensions()` em `ingest.py` retorna imediatamente se o MIME type não começa com `image/`. Vídeos (`video/mp4`) ficam com `kind=unknown` e **não aparecem** na aba "Arquivos e Mídia" da UI (o filtro por kind não os encontra).

O código stock tem até um comentário: *"Forward-compatible: future media kinds (e.g. "video" with duration/fps) can extend this shape"* — mas ainda não implementado.

## Decision

Criar `video_dimensions.py` (equivalente de `image_dimensions.py` para vídeos) que usa `ffprobe` (já no container) para extrair `width`, `height`, e `duration`. Patchar `ingest.py` para chamar `extract_video_dimensions()` quando o MIME é `video/*`.

### Aplicação do patch

O patch é aplicado no `entrypoint.sh` a cada boot (como o patch do `google-genai`):
1. Cria `/app/ComfyUI/app/assets/services/video_dimensions.py`
2. Adiciona import em `ingest.py`
3. Modifica `_maybe_store_image_dimensions()` para aceitar video
4. Re-enriquece MP4s existentes no DB via SQL

## Consequences

- MP4s agora aparecem com `kind=video`, `width`, `height`, `duration` no DB e na API
- A aba "Arquivos e Mídia" mostra os vídeos corretamente
- Se o ComfyUI upstream implementar isso nativamente no futuro, o patch é no-op (a verificação `if ! -f` evita overwrite)
