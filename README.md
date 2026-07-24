# ComfyUI — Deploy Docker Swarm com Auth Nativa

> [!IMPORTANT]
> **LEITURA OBRIGATÓRIA PARA AGENTES DE IA E DESENVOLVEDORES:** Antes de realizar qualquer modificação ou atualização de pacotes neste repositório, leia atentamente as regras críticas listadas em [COMFYUI_RULES.md](file:///Users/heltonfraga/Documents/Develop/Open-Generative-AI/COMFYUI_RULES.md) para evitar regressão de layout e erros de compilação.

> Documentação técnica completa para manutenção e operação.
> Última atualização: 2026-07-24
> Status: **Funcionando localmente e em produção** (verificado com HTTP 200 + login + Bearer token)

---

## 📋 Visão Geral

ComfyUI rodando como **orquestrador visual de workflows** que chamam APIs externas (Gemini, OmniRoute, Fal, etc.) via custom nodes. **Sem inferência local** — roda em modo `--cpu`. Auth nativa com usuário/senha via middleware injetado no build (sem Cloudflare/Traefik basicauth).

| Componente | Versão | Repo |
|---|---|---|
| ComfyUI (core) | `v0.28.0` | `comfyanonymous/ComfyUI` |
| ComfyUI-Manager | `4.2.2` | `Comfy-Org/ComfyUI-Manager` |
| ComfyUI Frontend | `v1.48.4` | `Comfy-Org/ComfyUI_frontend` |
| PyTorch | `2.5.1+cpu` | — |
| Python | `3.11-slim` | `public.ecr.aws/docker/library/python` |
| Imagem Docker | `heltonfraga/comfyui:v0.28.0-v5` | Docker Hub |
| Stack Portainer | ID `452` (`cortexx-comfyui`) | — |

### Custom Nodes (instalados no build)

| Node | Repo | Função |
|---|---|---|
| ComfyUI-AI-CustomURL | `bowtiedbluefin/ComfyUI-AI-CustomURL` | Texto, **imagem**, **vídeo**, **speech** — qualquer endpoint OpenAI-compatible com custom URL |
| comfyui-openai-llm | `godmt/comfyui-openai-llm` | MCP tools, image input, leve |
| ComfyUI-YALLM-node | `asaddi/ComfyUI-YALLM-node` | Multi-modal, OpenAI-like APIs local/remoto |

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
    --front-end-version Comfy-Org/ComfyUI_frontend@v1.48.4 \
    --output-directory /workspace/output \
    --input-directory /workspace/input \
    --user-directory /workspace/user \
    --models-directory /workspace/models \
    --temp-directory /workspace/temp
```

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
docker buildx build --platform linux/amd64 -t heltonfraga/comfyui:v0.28.0-v5 -f Dockerfile --push .
```

> ⚠️ Docker Hub rate limit (429) é comum. Se falhar, aguardar 3-5 min e retentar. O push das layers geralmente completa mesmo com erro 429 no pull (rate limit é por IP, não por push).

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
   - Linha 17: `--branch v0.28.0` → nova tag
   - Linha 20: `--branch 4.2.2` → nova tag
   - Linha 46 (entrypoint.sh): `--front-end-version Comfy-Org/ComfyUI_frontend@v1.48.4` → nova tag

3. **Verificar se Manager mudou estrutura:**
   - Tag 4.2.2 não tem `__init__.py` na raiz (precisa `pip install`)
   - Se voltar a ter `__init__.py`, remover o `pip install` e manter só `git clone` + `cp`

4. **Atualizar tag da imagem:** `heltonfraga/comfyui:v0.28.0-v5` → `v0.28.0-v6` (ou nova versão)

5. **Build → Push → Deploy → Testar os 3 endpoints**

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
