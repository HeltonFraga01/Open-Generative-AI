# ComfyUI — Deploy Docker Swarm com Auth Nativa

> [!IMPORTANT]
> **LEITURA OBRIGATÓRIA PARA AGENTES DE IA E DESENVOLVEDORES:** Antes de realizar qualquer modificação ou atualização de pacotes neste repositório, leia atentamente as regras críticas listadas em [COMFYUI_RULES.md](file:///Users/heltonfraga/Documents/Develop/Open-Generative-AI/COMFYUI_RULES.md) para evitar regressão de layout e erros de compilação.

> Documentação técnica completa para manutenção e operação.
> Última atualização: 2026-07-25
> Status: **Funcionando em produção** (HTTP 200, v0.28.0-v15, login nativo, 847+ nodes, image-to-video via MinIO confirmado)

---

## 📋 Visão Geral

ComfyUI rodando como **orquestrador visual de workflows** que chamam APIs externas (OmniRoute, NexusMind/Grok) via custom nodes. **100% API — sem inferência local**, roda em modo `--cpu` no Hetzner. Auth nativa com usuário/senha via middleware aiohttp injetado no build (sem Cloudflare/Traefik basicauth). Deploy via GHCR privado + Portainer Swarm.

| Componente | Versão | Repo |
|---|---|---|
| ComfyUI (core) | `master` (v0.28.0) | `comfyanonymous/ComfyUI` |
| ComfyUI-Manager | `4.2.2` (pip install) | `Comfy-Org/ComfyUI-Manager` |
| ComfyUI Frontend | `v1.48.4` (pre-baked) | `Comfy-Org/ComfyUI_frontend` |
| PyTorch | `2.5.1+cpu` (pinned) | — |
| Python | `3.11-slim` | `public.ecr.aws/docker/library/python` |
| Imagem Docker | `ghcr.io/heltonfraga01/comfyui:v0.28.0-v15` | GHCR privado |
| MinIO S3 | `s3.fragaai.com.br` (bucket `comfyui-images`) | Para uploads de image-to-video |

### Custom Nodes (instalados no build)

| Node | Repo | Função | Nodes fornecidos |
|---|---|---|---|
| `ComfyUI-AI-CustomURL` | `bowtiedbluefin/ComfyUI-AI-CustomURL` | Texto, **imagem**, **vídeo**, **speech** — qualquer endpoint OpenAI-compatible com custom URL | 13 nodes (`TextGeneration_AICustomURL`, `ImageGeneration_AICustomURL`, `VideoGeneration_AICustomURL`, etc.) |
| `comfyui-openai-llm` | `godmt/comfyui-openai-llm` | MCP tools, image input, leve | 9 nodes |
| `ComfyUI-YALLM-node` | `asaddi/ComfyUI-YALLM-node` | Multi-modal, OpenAI-like APIs local/remoto | 1 node |
| `ComfyUI-Gemini-Antigravity` | Custom (neste repo) | Geração de imagem via Gemini Antigravity (NexusMind proxy) | 1 node (`GeminiAntigravityImage`) |
| `ComfyUI-NexusVideo` | Custom (neste repo) | Geração de vídeo text-to-video e image-to-video via NexusMind sub2api (Grok) | 1 node (`NexusVideo`) |

> **Total: 29 nodes de API externa** (13 AICustomURL + 9 OpenAI-LLM + 1 YALLM + 6 MCP). Estes nodes aceitam `base_url` + `api_key` como inputs — aponte para OmniRoute ou NexusMind.

### Backend de Inferência (gateways conectáveis)

| Gateway | URL base | Models | Capabilities |
|---|---|---|---|
| **OmniRoute** | `https://omniroute.cortexx.online/v1` | 872 | chat (849), image (8), video (8: Veo free, Seedance), audio (5) |
| **NexusMind** | `https://api.nexusmind.digital/v1` | 17 | chat (Grok 4.x), image (grok-imagine), video (grok-imagine-video) |

---

## 🌐 Acesso

- **URL:** https://comfyui.nexusmind.digital
- **Login browser:** usuário `nexusmind` / senha definida no env `COMFYUI_DEFAULT_PASS_HASH` (bcrypt)
- **API/MCP:** header `Authorization: Bearer <COMFYUI_API_TOKEN>`

### Credenciais (referência, não colocar em chat)

- Senha do browser: hash bcrypt em `deploy/comfyui.yaml` → `COMFYUI_DEFAULT_PASS_HASH`
- Token da API: em `deploy/comfyui.yaml` → `COMFYUI_API_TOKEN`
- Ambos também em `~/.hermes/config.yaml` → `mcp_servers.comfyui.env`

---

## 📁 Estrutura de Arquivos

```
Open-Generative-AI/
├── Dockerfile              # Build da imagem (clone + pip install + patch auth + custom nodes)
├── entrypoint.sh           # Symlinks + CLI args do ComfyUI
├── deploy/
│   └── comfyui.yaml        # Stack Docker Swarm (Portainer stack 452)
├── workflows/              # Workflows de teste e referência (JSON)
│   ├── 01_chat_prompt_enhancement.json          # OmniRoute (Mistral) → NexusMind (Grok) → OmniRoute (Claude)
│   ├── 02_omniroute_gpt5_image.json             # OmniRoute GPT-5 Image → Preview
│   ├── 03_nexusmind_grok_image.json             # NexusMind Grok Imagine → Preview
│   ├── 04_omniroute_veo_video.json              # OmniRoute Veo (async) → Retrieve → Preview
│   └── 05_full_pipeline_enhance_image_video.json # Enhance → Image → Video
└── auth/
    ├── auth_inject.py       # Código do middleware: login, session, Bearer token, login HTML
    ├── patch_server.py      # Script Python que injeta auth_inject.py no server.py durante o build
    ├── models.py            # (legacy) Modelo SQLAlchemy — não usado na versão atual
    ├── auth_middleware.py   # (legacy) Middleware alternativo — não usado na versão atual
    ├── auth_routes.py       # (legacy) Rotas alternativas — não usado na versão atual
    └── user_manager_patched.py  # (legacy) Override do user_manager — não usado na versão atual
```

> **Atenção:** Os arquivos `models.py`, `auth_middleware.py`, `auth_routes.py`, `user_manager_patched.py` são legacy de uma abordagem anterior com SQLAlchemy. A versão atual usa apenas `auth_inject.py` + `patch_server.py`.

---

## 🏗️ Como o Build Funciona

### Dockerfile (passo a passo)

1. **Base:** `python:3.11-slim` (ECR — evita rate limit do Docker Hub)
2. **Sistema:** `apt-get install git curl ffmpeg build-essential`
3. **PyTorch CPU:** `torch==2.5.1+cpu` (sem GPU)
4. **Clone ComfyUI:** `git clone --branch v0.28.0 --depth 1` de `comfyanonymous/ComfyUI`
5. **Clone + pip install Manager:** `git clone --branch 4.2.2 --depth 1` de `Comfy-Org/ComfyUI-Manager` + `pip install /tmp/ComfyUI-Manager`
   > ⚠️ Manager 4.2.2 não tem `__init__.py` na raiz — é um package pip-installável. Só clonar não funciona; precisa `pip install`.
6. **pip install requirements** do ComfyUI
7. **pip install bcrypt** para auth
8. **COPY auth/** → `/app/ComfyUI/auth/`
9. **Patch server.py:** `python /app/ComfyUI/auth/patch_server.py`
   - Adiciona `auth_middleware` à lista de middlewares
   - Injeta rotas `/api/auth/*` no método `add_routes()`
   - Anexa código de `auth_inject.py` ao final do arquivo
   - Verifica com `grep "AUTH ROUTES"` que o patch foi aplicado
10. **Backup** de `custom_nodes` e `models` para inicialização do volume
11. **entrypoint.sh** copiado e com `chmod +x`

### Entrypoint.sh

1. Cria diretórios em `/workspace/` (volume persistente)
2. Se volume vazio: copia defaults (incl. ComfyUI-Manager) dos backups
3. Cria symlinks: `/app/ComfyUI/custom_nodes` → `/workspace/custom_nodes`, etc.
4. Executa ComfyUI com flags otimizadas:

```bash
python /app/ComfyUI/main.py \
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
    --temp-directory /workspace/temp
```

> **Pre-baked frontend:** O frontend v1.48.4 é copiado no build (`COPY web_custom/1.48.4/`) e servido via `--front-end-root`. NUNCA usar `--front-end-version` (download runtime) — pode falhar por GitHub API rate limit e servir versão errada.

---

## 🔐 Sistema de Auth

### Arquitetura

```
Request → Traefik (TLS) → ComfyUI (aiohttp) → auth_middleware → handler
                                                          ↓
                                              Bearer token? → bypass (MCP)
                                              Cookie session? → bypass (browser)
                                              Nenhum? → login HTML / 401 JSON
```

### Fluxos de auth

**Browser:**
1. `GET /` sem cookie → HTML da tela de login
2. `POST /api/auth/login` com `{username, password}` → bcrypt.checkpw → set cookie `comfy_session` (7 dias, httponly)
3. `GET /` com cookie → interface ComfyUI

**MCP/API:**
1. Request com header `Authorization: Bearer <COMFY...N>` → bypass direto

### Variáveis de ambiente (deploy/comfyui.yaml)

| Env | Função | Exemplo |
|---|---|---|
| `COMFYUI_AUTH_ENABLED` | Liga/desliga auth | `true` |
| `COMFYUI_DEFAULT_USER` | Usuário único | `nexusmind` |
| `COMFYUI_DEFAULT_PASS_HASH` | Hash bcrypt da senha | `$2b$12$...` |
| `COMFYUI_API_TOKEN` | Token fixo para MCP/API | (random 32 chars) |

> Sessions são **in-memory** (`_valid_sessions = {}`). Restart do container = todos perdem login (fazem login de novo). Token API é stateless.

### Gerar nova senha bcrypt

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'NOVA_SENHA', bcrypt.gensalt(12)).decode())"
```

### Gerar novo token API

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 🔌 Configuração do MCP (Hermes)

Em `~/.hermes/config.yaml`:

```yaml
comfyui:
  command: npx
  args:
    - -y
    - comfyui-mcp
  env:
    COMFYUI_URL: https://comfyui.nexusmind.digital
    COMFYUI_AUTH_HEADER: Authorization
    COMFYUI_AUTH_SCHEME: Bearer
    COMFYUI_AUTH_TOKEN: <MESMO_TOKEN_DO_DEPLOY_YAML>
  connect_timeout: 30
  timeout: 120
```

O `comfyui-mcp` (npm `comfyui-mcp@0.46.0`) envia `Authorization: Bearer <token>` em toda requisição. O middleware do ComfyUI valida e faz bypass do cookie.

> Após mudar a config do MCP, reiniciar o Hermes para recarregar.

---

## 🚀 Deploy e Redeploy

### Build da imagem

```bash
cd ~/Documents/Develop/Open-Generative-AI

# Prune obrigatório antes de cada build (Mac arm64 → linux/amd64 via QEMU)
docker buildx prune --all --force

# Build + push para GHCR (privado, sem rate limit)
docker buildx build --platform linux/amd64 \
  -t ghcr.io/heltonfraga01/comfyui:v0.28.0-v12 \
  -f Dockerfile --push .
```

> **GHCR privado** (GitHub Container Registry) — sem rate limit do Docker Hub. Requer classic PAT com scope `write:packages`. Registry auth configurada no Portainer (ID 2, Type 3).
> **Build Mac arm64 → linux/amd64:** ~7-12min via QEMU. Sempre `docker buildx prune` antes para evitar `No space left on device`.

### Redeploy via Portainer API

```bash
source ~/.config/cortexx/secrets/portainer.env
CONTENT=$(cat deploy/comfyui.yaml | jq -Rs .)
curl -s -k -X PUT "$PORTAINER_URL/api/stacks/452?endpointId=1" \
  -H "X-API-Key: $PORTAINER_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"StackFileContent\": ${CONTENT}, \"Prune\": false, \"PullImage\": true}"
```

### Verificar funcionamento

```bash
# 1. Sem auth → deve retornar 200 (login HTML)
curl -s -o /dev/null -w "%{http_code}" https://comfyui.nexusmind.digital/

# 2. Login → deve retornar {"success": true}
curl -s https://comfyui.nexusmind.digital/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"nexusmind","password":"<SENHA>"}'

# 3. Bearer token (MCP) → deve retornar 200
curl -s -H "Authorization: Bearer <TOKEN>" -o /dev/null -w "%{http_code}" https://comfyui.nexusmind.digital/system_stats
```

> **NUNCA marcar como concluído sem executar os 3 testes acima.** 404 não é funcionando.

---

## ⚠️ Pitfalls e Lições Aprendidas

### 1. ComfyUI-Manager 4.2.2 não tem `__init__.py` na raiz
A partir da 4.2.2, o Manager virou package pip-installável. Só `git clone` dentro de `custom_nodes/` **não funciona** — o ComfyUI procura `__init__.py` na raiz do custom node e não encontra. Solução: `pip install` + `cp -r` para a pasta `custom_nodes/`.

### 2. Patch do server.py precisa de indentação correta
O `server.py` da v0.28.0 tem 8 espaços de indentação. O `patch_server.py` faz `str.replace()` do padrão exato:
```
"        routes = web.RouteTableDef()\n        self.routes = routes"
```
Se erroneamente usar 0 espaços, o replace não encontra, as rotas não são injetadas, e `routes is not defined` no runtime.

### 3. Docker Hub rate limit (429 Too Many Requests)
Builds frequentes batem o limite. As layers **subem** mesmo com erro 429 (o rate limit é no pull, não no push). Mas o Swarm pode não conseguir `pullImage` se o servidor também estiver rate-limited. Aguardar 5-10 min entre deploys.

### 4. Docker buildx cache
Se alterar `auth_inject.py` ou `patch_server.py` mas não alterar o `COPY auth/` (que invalida o cache), o buildx pode usar cache da camada do `RUN python patch_server.py`. Forçar invalidação com `--no-cache` ou mudar algo no `COPY` (ex: `COPY auth/ /app/ComfyUI/auth/` já invalida se o conteúdo mudar).

### 5. ComfyUI nativo NÃO tem auth com senha
O `--multi-user` só cria perfis separados com UUID — sem senha, sem login. A auth com senha é **inteiramente** via o patch `auth_inject.py`. Sem o patch, qualquer um acessa.

### 6. `WEB_ENABLE_AUTH` não existe
Essa env var foi inventada em iterações anteriores. Não existe no código do ComfyUI. As env vars reais são `COMFYUI_AUTH_ENABLED`, `COMFYUI_DEFAULT_USER`, `COMFYUI_DEFAULT_PASS_HASH`, `COMFYUI_API_TOKEN` (todas custom, definidas no `auth_inject.py`).

### 7. Basicauth do Traefik/Cloudflare foi removido
A versão anterior usava `traefik.http.middlewares.comfyui-auth.basicauth.users=nexusmind:$$apr1$$...` no yaml. Isso foi **removido**. A auth é nativa no ComfyUI agora. Não adicionar de volta.

### 8. Volume `v3` é o atual
`v1` e `v2` são volumes antigos com dados de tentativas anteriores. `v3` é limpo e atual.

---

## 🔄 Atualizar Versões no Futuro

Para atualizar ComfyUI, Manager ou Frontend:

1. **Verificar tag estável** nos repositórios:
   - https://github.com/comfyanonymous/ComfyUI/tags
   - https://github.com/Comfy-Org/ComfyUI-Manager/tags
   - https://github.com/Comfy-Org/ComfyUI_frontend/releases

2. **Atualizar Dockerfile:**
   - `git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git` (mantém master)
   - `git clone --branch 4.2.2` → nova tag do Manager
   - `COPY web_custom/1.48.4/` → baixar nova versão do frontend zip, extrair para `web_custom/<nova_versao>/`

3. **Atualizar entrypoint.sh:**
   - `--front-end-root /app/ComfyUI/web_custom_versions/Comfy-Org_ComfyUI_frontend/<nova_versao>`

4. **⚠️ NUNCA usar `--front-end-version` (runtime download)** — usa `--front-end-root` (pre-baked). Download runtime pode falhar por GitHub API rate limit.

5. **Verificar se Manager mudou estrutura:**
   - Tag 4.2.2 não tem `__init__.py` na raiz (precisa `pip install`)
   - Se voltar a ter `__init__.py`, remover o `pip install` e manter só `git clone` + `cp`

6. **Atualizar tag da imagem:** `ghcr.io/heltonfraga01/comfyui:v0.28.0-v12` → `v0.28.0-v13` (ou nova versão)

7. **Prune → Build → Push → Deploy → Testar os 3 endpoints**

> **⚠️ REGRA CRÍTICA:** O frontend é **pre-baked** no Dockerfile (`COPY web_custom/1.48.4/`). Para mudar a versão, baixe o zip da nova release, extraia para `web_custom/<nova_versao>/`, atualize o `COPY` no Dockerfile e o `--front-end-root` no entrypoint. NUNCA use `@latest` ou `v1.48.5` (bug `graph accessed before initialization`).

### 🧹 Cache do Browser (Checklist de Troubleshooting)

Se o frontend não renderiza em produção mas funciona localmente:

1. **Hard refresh (Cmd+Shift+R)** — às vezes resolve cache de JS/CSS
2. **Limpar dados do site (DevTools → Application → Storage → Clear site data)** — remove localStorage + indexedDB stale do Vue
3. **Testar em DuckDuckGo ou incognito** — se funcionar, é cache do browser com certeza
4. **NÃO culpar Cloudflare** — `cf-cache-status: BYPASS` confirma que não é CDN

> O ComfyUI Vue 3 frontend guarda estado no localStorage + indexedDB. Versões antigas do frontend podem deixar state stale que causa `graph accessed before initialization` mesmo com a versão correta (v1.48.4). Limpar tudo resolve.

---

## 🎨 Workflows de Teste e Referência

> Para usar: arraste o arquivo JSON para dentro da interface do ComfyUI, ou use o botão "Load" no menu.
> Substitua `OMNIROUTE_API_KEY_HERE` e `NEXUSMIND_API_KEY_HERE` pelas chaves reais.

### 01 — Chat: Prompt Enhancement

`workflows/01_chat_prompt_enhancement.json`

```
OmniRoute (Mistral Large) → NexusMind (Grok 4.5) → history
                          → OmniRoute (Claude Sonnet) → critique
```

OmniRoute enhances a simple concept into a rich image prompt. NexusMind writes a story from it. Claude critiques the prompt quality. Tudo via `/v1/chat/completions`.

**Nodes:** `TextGeneration_AICustomURL` × 3

---

### 02 — OmniRoute GPT-5 Image

`workflows/02_omniroute_gpt5_image.json`

```
OmniRoute (kilocode/gpt-5-image) → PreviewImage
```

Gera imagem via OmniRoute. Endpoint: `/v1/images/generations`.

**Nodes:** `ImageGeneration_AICustomURL`, `PreviewImage`

---

### 03 — NexusMind Grok Imagine Image

`workflows/03_nexusmind_grok_image.json`

```
NexusMind (grok-imagine-image) → PreviewImage
```

Gera imagem via Grok Imagine da NexusMind. Mesmo endpoint OpenAI-compatible.

**Nodes:** `ImageGeneration_AICustomURL`, `PreviewImage`

---

### 04 — OmniRoute Veo Video (async)

`workflows/04_omniroute_veo_video.json`

```
OmniRoute (veo-free/veo) → video_id
VideoRetrieve → video_url
VideoPreview → player
```

Vídeo é assíncrono. Node 1 submete e retorna `video_id`. Node 2 faz poll com o `video_id` até o vídeo estar pronto. Node 3 mostra o player.

**Nodes:** `VideoGeneration_AICustomURL`, `VideoRetrieve_AICustomURL`, `VideoPreview_AICustomURL`

---

### 05 — Full Pipeline: Enhance → Image → Video

`workflows/05_full_pipeline_enhance_image_video.json`

```
OmniRoute (Mistral) → enhanced prompt
OmniRoute (GPT-5 Image) → image from prompt → Preview
NexusMind (Grok Video) → video from image
```

Pipeline completo: um LLM do OmniRoute transforma um conceito simples em um prompt visual rico → gera imagem → envia a imagem para o Grok animar em vídeo.

---

### 07 — NexusMind Grok Image (Simples)

`workflows/07_nexusmind_grok_image_simple.json`

```
NexusMind (grok-imagine-image) → SaveImage
```

Workflow mais simples — 2 nodes. Gera imagem via Grok Imagine da NexusMind. **Verificado end-to-end 2026-07-24** (imagem `NexusMind_Grok_00001_.png`, 1.4MB, ~15s de geração).

**Importante:** O workflow 06 (Flux Schnell local) foi removido — o servidor agora é 100% API. Ver seção "Modo de Operação" abaixo.

---

### 09 — Gemini Antigravity Image

`workflows/09_gemini_antigravity_image.json`

```
GeminiAntigravityImage → SaveImage
```

Gera imagem via Gemini Antigravity (proxy NexusMind). Custom node próprio (`ComfyUI-Gemini-Antigravity`). 6 modelos disponíveis. **Status:** Funciona, mas sujeito a 503 ("No available Gemini accounts") quando o pool Google do sub2api esgota.

---

### 10 — NexusVideo Image-to-Video ⭐

`workflows/10_nexusvideo_image_to_video.json`

```
LoadImage → NexusVideo (i2v via MinIO) → SaveText (status) + PreviewVideo (video_path)
```

**Verificado end-to-end 2026-07-25.** Gera vídeo a partir de uma imagem de referência. O node faz upload da imagem para o MinIO S3, obtém URL pública, e envia `{"image":{"url":"..."}}` para a API xAI/Grok. Vídeo MP4 (~3MB, 5s) é salvo em `/workspace/output/`.

> **⚠️ Documentação completa:** [docs/NEXUSVIDEO_I2V.md](docs/NEXUSVIDEO_I2V.md) — armadilhas, formato da API, troubleshooting.

---

### 11 — NexusVideo Text-to-Video

`workflows/11_nexusvideo_text_to_video.json`

```
NexusVideo (t2v, sem LoadImage) → SaveText (status) + PreviewVideo (video_path)
```

Gera vídeo a partir de texto. Não precisa de MinIO (sem imagem para upload). **Verificado end-to-end 2026-07-25.**

---

### Nodes disponíveis do ComfyUI-AI-CustomURL

| Node ID | Categoria | Inputs principais | Outputs |
|---|---|---|---|
| `TextGeneration_AICustomURL` | ai_customurl | base_url, api_key, model, prompt, temperature, max_tokens, system_prompt, image | text (STRING), full_response (STRING) |
| `ImageGeneration_AICustomURL` | ai_customurl | base_url, api_key, prompt, model, n, size, quality, style, response_format | images (IMAGE), urls (STRING) |
| `VideoGeneration_AICustomURL` | ai_customurl | base_url, api_key, model, prompt, resolution, duration, fps, aspect_ratio, auto_poll, image | video_url, video_id, api_key, status, response_json |
| `VideoRetrieve_AICustomURL` | ai_customurl | base_url, api_key, video_id | video_url, status, response_json |
| `VideoPreview_AICustomURL` | ai_customurl | video_url | — |
| `SpeechGeneration_AICustomURL` | ai_customurl | base_url, api_key, model, input, response_format, speed | audio (AUDIO), file_path (STRING) |
| `ImageLoader_AICustomURL` | ai_customurl | url | image (IMAGE) |
| `SaveVideo_AICustomURL` | ai_customurl | video_url, filename | — |

### 9. `cp -r` cria subdirectory errado se não usar `/.`
`cp -r /app/ComfyUI/custom_nodes /app/ComfyUI/custom_nodes_default` cria `custom_nodes_default/custom_nodes/...`. O correto é `cp -r /app/ComfyUI/custom_nodes/. /app/ComfyUI/custom_nodes_default/` para copiar o **conteúdo** da pasta, não a pasta em si. Sem isso, o ComfyUI tenta carregar `custom_nodes/custom_nodes/__init__.py` e falha.

### 10. Volume novo para forçar re-init dos custom nodes
Ao adicionar novos custom nodes no Dockerfile, o entrypoint só copia defaults se o volume estiver **vazio**. Volume antigo (v3) já tinha `custom_nodes` preenchido → sync incremental só copia nodes novos, mas pode falhar com o subdirectory bug (pitfall #9). Solução: bumpar o volume (v4, v5, ...) para forçar init limpo.

---

## 📞 Suporte

- **Repo local:** `~/Documents/Develop/Open-Generative-AI/`
- **Credenciais Portainer:** `~/.config/cortexx/secrets/portainer.env`
- **Stack ID:** `452` (endpoint `1`)
- **Skill Hermes:** `comfyui-swarm-deployment` em `~/.hermes/skills/`

---

## 📚 Documentação Técnica

| Documento | Descrição |
|---|---|
| [COMFYUI_RULES.md](COMFYUI_RULES.md) | Regras críticas — OBRIGATÓRIO antes de qualquer modificação |
| [docs/NEXUSVIDEO_I2V.md](docs/NEXUSVIDEO_I2V.md) | Como o image-to-video funciona (MinIO upload → xAI API → MP4) |
| [docs/adr/](docs/adr/) | Architecture Decision Records — o *porquê* de cada decisão |

### ADRs

| ADR | Decisão |
|---|---|
| [0001](docs/adr/0001-xai-image-url-format.md) | xAI Grok video API usa `image: {"url": ...}` (objeto), não `image_url` (string) |
| [0002](docs/adr/0002-minio-s3-image-hosting.md) | MinIO S3 como intermediário de upload para image-to-video |
| [0003](docs/adr/0003-no-resolution-duration-in-payload.md) | `resolution` e `duration` não enviados à API xAI (causam 422) |
| [0004](docs/adr/0004-entrypoint-runtime-deps.md) | Entrypoint instala deps de custom nodes em runtime |
| [0005](docs/adr/0005-video-enrichment-ffprobe.md) | Patch de enriquecimento de vídeo (kind=video) via ffprobe |

---

## 🗂️ CHANGELOG

| Data | Versão | Mudança |
|---|---|---|
| 2026-07-25 | v0.28.0-v16 | Patch: enriquecimento de vídeo com ffprobe (`kind=video`, width/height/duration). MP4s agora aparecem na aba Arquivos e Mídia |
| 2026-07-25 | v0.28.0-v15 | `pip install minio` + `google-genai` no entrypoint. NexusVideo i2v via MinIO. Deploy ← imagem v15 |
| 2026-07-25 | v0.28.0-v14 | `pip install minio` no Dockerfile para NexusVideo i2v |
| 2026-07-24 | v0.28.0-v13 | Custom nodes `ComfyUI-Gemini-Antigravity` + `ComfyUI-NexusVideo` adicionados |
| 2026-07-24 | v0.28.0-v12 | Auth nativa, `--enable-assets`, Manager config persistente, 847 nodes |
