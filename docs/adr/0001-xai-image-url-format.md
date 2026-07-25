# ADR-0001: xAI Grok video API usa `image: {"url": ...}` (objeto), não `image_url` (string)

**Date:** 2026-07-25
**Status:** Accepted
**Decision Maker:** Rick-B Fraga (agente) + Helton Fraga

## Context

O custom node `NexusVideo` precisava enviar uma imagem (do tensor ComfyUI `LoadImage`) para a API de video generation do xAI/Grok via NexusMind sub2api. A primeira implementação enviava a imagem como `data:image/jpeg;base64,...` no campo `image_url` (string).

**Problema:** O vídeo era gerado com HTTP 200, mas a imagem de referência era **completamente ignorada** — o xAI gerava text-to-video puro, sem usar a imagem. Testes com uma imagem magenta distintiva confirmaram: 0% magenta no frame de saída.

## Investigation

### 1. Teste direto com data URL

```python
payload = {"model": "grok-imagine-video-1.5", "prompt": "...", "image_url": "data:image/jpeg;base64,..."}
# HTTP 200, vídeo gerado, mas imagem NÃO usada (.frame sem traços da imagem)
```

### 2. Teste com URL pública (picsum.photos)

```python
payload = {"model": "grok-imagine-video-1.5", "prompt": "...", "image_url": "https://picsum.photos/..."}
# HTTP 200, vídeo gerado, mas imagem NÃO usada
```

### 3. Inspeção do código-fonte sub2api

Clonamos o tree do `github.com/Wei-Shaw/sub2api` e lemos `backend/internal/service/grok_media.go`:

- `parseGrokMediaJSONRequest()` lê `image` e `image_url` do JSON → coloca em `InputImageURLs`
- `sanitizeGrokMediaForwardBody()` para `videos_generations` cai no `default` case → **passa o body original direto pro xAI upstream**
- Ou seja: o sub2api não reconstrói o payload de vídeo — o que você envia é o que o xAI recebe

### 4. Documentação do xAI

A doc em `docs.x.ai` mostra que `/v1/videos/generations` aceita:

```
image: null | object   ← OBJETO, não string
```

E para `video edit` o exemplo claro: `"video": {"url": "https://..."}`

### 5. Teste com formato correto

```python
payload = {"model": "grok-imagine-video-1.5", "prompt": "...", "image": {"url": "https://s3.fragaai.com.br/..."}}
# HTTP 200, vídeo gerado, 88.3% magenta no frame → IMAGEM USADA! ✅
```

## Decision

O node `NexusVideo` envia `image` como **objeto** `{"url": "https://..."}` com uma **URL HTTP pública**, nunca como string `image_url` nem data URL.

Para obter a URL pública:
1. O node converte o tensor ComfyUI para JPEG bytes
2. Faz upload para o MinIO S3 (bucket `comfyui-images`, public-read)
3. Usa a URL resultante (`https://s3.fragaai.com.br/comfyui-images/...`) no payload

## Consequences

- **Positivas:**
  - Image-to-video funciona de verdade — o xAI usa a imagem como referência
  - Imagens ficam persistidas no MinIO para auditoria/debug
  - Funciona com qualquer imagem que tenha uma URL pública

- **Negativas:**
  - Depende do MinIO estar online — se cair, i2v quebra (t2v ainda funciona)
  - Latência extra: upload + round-trip MinIO antes de chamar a API
  - Bucket `comfyui-images` acumula imagens — precisa de lifecycle policy (TODO)

- **Riscos:**
  - Se o xAI mudar o formato da API (de `image: {"url":...}` para outro), o node quebra
  - MinIO credentials no Portainer — se alguém recriar o service sem as env vars, i2v quebra

## References

- xAI docs: https://docs.x.ai (session "Videos → Video generation")
- sub2api source: `backend/internal/service/grok_media.go` (function `sanitizeGrokMediaForwardBody`)
- Test validation: frame analysis showing 88.3% magenta pixels when using correct format
