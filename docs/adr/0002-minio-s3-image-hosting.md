# ADR-0002: MinIO S3 como intermediário de upload para image-to-video

**Date:** 2026-07-25
**Status:** Accepted

## Context

O xAI/Grok video API exige que a imagem de referência esteja em uma **URL HTTP pública**. O ComfyUI em produção não tem um endpoint público para servir imagens do `/workspace/input/` — a auth nativa bloqueia acesso sem bearer token, e o xAI não envia credentials.

Um intermediário de hospedagem era necessário.

## Alternativas consideradas

| Alternativa | Pros | Cons | Decisão |
|---|---|---|---|
| **MinIO S3** (já no servidor) | Já deployado, compatível S3, bucket público, sem custo | Latência de upload (~1-2s) | ✅ Escolhido |
| imgur API | Grátis, URL curta | Rate limit, não controlamos, dependência externa | ❌ |
| S3 AWS | Padrão, confiável | Custo, dependência externa, uma conta a mais | ❌ |
| ComfyUI `/api/view` como URL | Sem intermediário | Exige auth header — xAI não envia | ❌ |
| Data URL inline (`data:image/jpeg;base64,...`) | Sem upload | xAI ignora silenciosamente (ver ADR-0001) | ❌ |
| Multipart/form-data | Sem URL intermediária | xAI retorna HTTP 415 | ❌ |

## Decision

Usar o MinIO S3 já deployado no servidor (`s3.fragaai.com.br`) com bucket `comfyui-images` configurado como **public-read**.

### Fluxo de upload

```
IMAGE tensor (ComfyUI) → JPEG bytes → PUT /comfyui-images/comfyui_{timestamp}_{hash}.jpg → URL pública
```

### Credenciais

As credenciais do MinIO (`MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`) são injetadas no container via Portainer service spec (env vars). O repo público usa placeholders `YOUR_MINIO_*`.

## Consequences

- **Bucket `comfyui-images`** acumula imagens temporárias — cada upload cria um arquivo único baseado em timestamp + hash MD5
- **TODO:** Adicionar lifecycle policy (expiração automática após 24h) para não encher o disco
- Se MinIO cair, image-to-video quebra (o node retorna erro de upload); text-to-video ainda funciona
