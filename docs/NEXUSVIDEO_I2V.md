# NexusVideo — Image-to-Video via NexusMind sub2api (Grok)

> **Status:** ✅ Funcionando em produção (v0.28.0-v15)
> **Testado em:** 2026-07-25 — MP4 3.2MB gerado com imagem de referência confirmada
> **Custom node:** `custom_nodes/ComfyUI-NexusVideo/__init__.py`

---

## Visão geral

O `NexusVideo` é um custom node que gera vídeo (text-to-video e image-to-video) chamando a API do NexusMind sub2api (`api.nexusmind.digital/v1`), que por sua vez chama o xAI/Grok upstream. A API é **assíncrona**: POST retorna `request_id`, polling GET até `done`, download do MP4.

O fluxo de image-to-video requer que a imagem esteja hospedada em uma **URL HTTP pública** — o xAI não aceita data URLs nem base64 inline. Este node resolve isso fazendo upload da imagem para o MinIO (S3) antes de chamar a API.

```
LoadImage → NexusVideo → (MinIO upload → xAI i2v API → polling → download MP4) → SaveText + PreviewVideo
```

---

## Arquitetura do fluxo

```
┌──────────┐     ┌──────────────────────────────────────────────────────┐     ┌───────────┐
│ LoadImage │────▶│ NexusVideo                                            │────▶│ SaveText   │
│ (tensor)  │     │                                                        │     │ (status)   │
└──────────┘     │  1. tensor → JPEG bytes                               │     └───────────┘
                   │  2. upload JPEG → MinIO S3 (bucket comfyui-images)  │
                   │  3. POST /v1/videos/generations                     │     ┌───────────┐
                   │     body: {"model":"grok-imagine-video-1.5",        │────▶│PreviewVideo│
                   │            "prompt":"...",                          │     │(video_path)│
                   │            "image":{"url":"https://s3.fragaai..."}} │     └───────────┘
                   │  4. poll GET /v1/videos/{request_id} until "done"   │
                   │  5. download GET /v1/videos/{request_id}/content   │
                   │  6. save MP4 → /workspace/output/                   │
                   └──────────────────────────────────────────────────────┘
```

---

## API do NexusMind sub2api (Grok vídeo)

### Endpoints

| Método | Path | Descrição |
|---|---|---|
| POST | `/v1/videos/generations` | Submete geração (t2v ou i2v). Retorna `{"request_id":"..."}` |
| GET | `/v1/videos/{request_id}` | Polling de status. Retorna `{"status":"done","progress":100,"video":{"url":"/v1/videos/{id}/content"}}` |
| GET | `/v1/videos/{request_id}/content` | Download do MP4 binário |

### Payload — Text-to-Video (T2V)

```json
{
  "model": "grok-imagine-video",
  "prompt": "A serene lake at sunrise",
  "n": 1
}
```

### Payload — Image-to-Video (I2V) ⚠️ CRÍTICO

```json
{
  "model": "grok-imagine-video-1.5",
  "prompt": "animate this image with dynamic motion",
  "n": 1,
  "image": {
    "url": "https://s3.fragaai.com.br/comfyui-images/comfyui_xxxxx.jpg"
  }
}
```

### ⚠️ ARMADILHAS DA API (descobertas em 2026-07-25)

| O que NÃO fazer | Por quê | O que acontece |
|---|---|---|
| `"image_url": "data:image/jpeg;base64,..."` | xAI ignora data URLs silenciosamente | **HTTP 200 mas vídeo é text-only** — imagem NÃO é usada |
| `"image_url": "https://..."` (string) | xAI espera `"image"` como **objeto**, não `"image_url"` como string | **HTTP 200 mas imagem NÃO é usada** |
| `"resolution": "720p"` | xAI rejeita campos não reconhecidos | **HTTP 422** |
| `"duration": 5` | xAI rejeita campos não reconhecidos | **HTTP 422** |
| multipart/form-data com `image` file | xAI video API não aceita multipart | **HTTP 415** |
| `"n": 2` ou maior | xAI suporta apenas n=1 para vídeo | Erro ou comportamento indefinido |

### Modelos disponíveis

| Modelo | Tipo | Duração |
|---|---|---|
| `grok-imagine-video` | Text-to-video | 8s (default) |
| `grok-imagine-video-1.5` | Image-to-video | 5s (default) |
| `grok-imagine-video-1.5-pro` | Image-to-video (premium) | — |

---

## MinIO S3 — Bucket de imagens

O bucket `comfyui-images` no MinIO (`s3.fragaai.com.br`) hospeda as imagens temporárias para o xAI. É **public-read** (qualquer um pode GET, só auth pode PUT).

### Configuração

| Env var | Valor | Onde |
|---|---|---|
| `MINIO_ENDPOINT` | `s3.fragaai.com.br` | deploy/comfyui.yaml (Portainer) |
| `MINIO_ACCESS_KEY` | [REDACTED] | Portainer (não no repo público) |
| `MINIO_SECRET_KEY` | [REDACTED] | Portainer (não no repo público) |
| `MINIO_BUCKET` | `comfyui-images` | deploy/comfyui.yaml |
| `MINIO_SECURE` | `true` | deploy/comfyui.yaml |

### Como o bucket foi criado

```python
from minio import Minio
import json

client = Minio("s3.fragaai.com.br", access_key="...", secret_key="...", secure=True)

# Criar bucket
client.make_bucket("comfyui-images")

# Policy public-read
policy = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"AWS": ["*"]},
        "Action": ["s3:GetObject"],
        "Resource": ["arn:aws:s3:::comfyui-images/*"]
    }]
}
client.set_bucket_policy("comfyui-images", json.dumps(policy))
```

---

## Como o sub2api funciona (inspeção do código-fonte)

O sub2api (`github.com/Wei-Shaw/sub2api`) é o gateway entre a API do Fraga AI e o xAI/Grok upstream.

### Fluxo do body

1. **`parseGrokMediaJSONRequest`** lê o JSON body do request
   - Extrai `model`, `prompt`, `image`/`image_url` → coloca em `InputImageURLs`
   - Aceita `"image"` (array de URLs) e `"image_url"` (string)

2. **`sanitizeGrokMediaForwardBody`** para `videos_generations`
   - Cai no `default` case → **passa o body original direto pro xAI upstream**
   - Não reconstrói o payload — o que você envia é o que o xAI recebe

3. O xAI recebe o body e processa:
   - Se tem `"image": {"url": "https://..."}` → image-to-video
   - Se NÃO tem imagem válida → text-to-video (ignora silenciosamente)

### Por que `image_url` (string) não funciona

O sub2api lê `image_url` e coloca em `InputImageURLs`, mas para **video generation** o body é repassado as-is. O xAI não lê `image_url` como campo top-level no video endpoint — ele espera `image` como objeto com `url`.

---

## Workflows

### 10 — NexusVideo Image-to-Video

`workflows/10_nexusvideo_image_to_video.json`

```
LoadImage → NexusVideo (i2v) → SaveText (status) + PreviewVideo (video_path)
```

**Inputs do NexusVideo:**
- `image` (IMAGE tensor do LoadImage — o node converte para JPEG e faz upload MinIO)
- `base_url`: `https://api.nexusmind.digital/v1`
- `api_key`: sua chave NexusMind
- `model`: `grok-imagine-video-1.5`
- `prompt`: descrição da animação desejada
- `image_url`: deixar vazio (preenchido automaticamente quando `image` é conectado)
- `auto_poll`: `true` (o node faz polling automaticamente)
- `poll_interval`: 5 (segundos)
- `max_wait_time`: 300 (segundos)

> NOTA: `resolution` e `duration` são campos do node aceitos pela UI mas **não enviados** à API (causavam 422). O node ignora esses valores no payload.

### 11 — NexusVideo Text-to-Video

`workflows/11_nexusvideo_text_to_video.json`

```
NexusVideo (t2v, sem LoadImage) → SaveText (status) + PreviewVideo (video_path)
```

### Link PreviewVideo ⚠️

O `PreviewVideo` (do llm-toolkit) aceita apenas `video_path` (STRING), **NÃO** `filepath`. Workflow deve ligar `NexusVideo.video_url` → `PreviewVideo.video_path`.

---

## Troubleshooting

| Sintoma | Causa | Solução |
|---|---|---|
| Vídeo gerado mas imagem não aparece | `image_url` como string ou data URL | Usar `image: {"url": "..."}` com URL pública do MinIO |
| HTTP 422 ao submeter | `resolution` ou `duration` no payload | Node já remove esses campos — se ainda ocorre, verifique se o node está atualizado |
| HTTP 415 ao submeter | Multipart/form-data enviado | Usar JSON body (não multipart) |
| `No module named 'minio'` | Imagem Docker sem `minio` SDK | Build com Dockerfile que tem `pip install minio` (v14+) |
| `No module named 'google'` | llm-toolkit sem `google-genai` | Entrypoint v15+ instala automaticamente |
| Download 404 (duplo `/v1`) | URL de download concatenada errado | Node já corrige — `video_path` já vem como `/v1/videos/{id}/content` |
| `PreviewVideo.preview() got unexpected keyword 'filepath'` | Link errado no workflow | Mudar link para `video_path` (não `filepath`) |
