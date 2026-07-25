# ⚠️ REGRAS CRÍTICAS DE DESENVOLVIMENTO E DEPLOY DO COMFYUI

Este repositório possui diretrizes arquiteturais estritas. **Todos os agentes de IA e desenvolvedores devem seguir estas regras sem exceção.** Violar qualquer regra causa regressão silenciosa, builds quebrados, ou frontend que não renderiza.

---

## 📌 1. PIN DE VERSÃO DO FRONTEND (Pre-baked, não runtime download)

* **REGRA:** O frontend é **pre-baked** no Dockerfile via `COPY web_custom/1.48.4/` e servido via `--front-end-root` no `entrypoint.sh`. **NUNCA** use `--front-end-version` (download runtime) — pode falhar por GitHub API rate limit e servir versão errada.
* **VERSAO ESTÁVEL:** Sempre use a tag fixa **`v1.48.4`**.
* **PROIBIDO:**
  - `--front-end-version Comfy-Org/ComfyUI_frontend@latest` (pulls nightly)
  - `--front-end-version Comfy-Org/ComfyUI_frontend@v1.48.5` (bug `graph accessed before initialization`)
  - Qualquer versão não testada
* **MOTIVO:** A versão `v1.48.5` tem um race condition: `TypeError: Cannot read properties of undefined (reading '_nodes')` que quebra a inicialização do Vue 3 silenciosamente e reverte a tela para o menu clássico (litegraph legacy), fazendo parecer que o deploy falhou.
* **PARA ATUALIZAR:** Baixe o zip da nova release do frontend, extraia para `web_custom/<nova_versao>/`, atualize o `COPY` no Dockerfile e o `--front-end-root` no entrypoint. Teste localmente antes de pushar.

---

## 🎨 2. ERRO DE FONTE MONOSPACE (Google Translate)

* **PROBLEMA:** Se a interface do ComfyUI carregar com uma fonte monospace (Courier/linha de código) no lugar da fonte sans-serif limpa padrão, o motivo é o uso de extensões de tradução (ex: **Google Translate** no Chrome).
* **EXPLICAÇÃO:** O Google Tradutor envolve os blocos de texto em tags `<font>`. Como o CSS da nova interface do ComfyUI não estiliza a tag `<font>`, o navegador herda a fonte monospace padrão de sistema.
* **SOLUÇÃO:** **NÃO tente alterar o CSS do repositório para corrigir isso.** A solução correta é orientar o usuário a desativar a tradução automática para o domínio do ComfyUI (adicionando "Nunca traduzir este site" nas configurações da extensão).

---

## 🛠️ 3. DEPLOY LOCAL (Apple Silicon / Mac)

* **REGRA:** Quando executar a aplicação localmente no Mac (`docker compose up --build`), a configuração da plataforma **deve** ser fixada em `platform: linux/amd64`.
* **MOTIVO:** Os pacotes de PyTorch CPU (`torch==2.5.1+cpu` etc.) não possuem builds estáveis pré-compilados para a arquitetura `arm64` (Apple Silicon) em repositórios padrão. Forçar a plataforma `amd64` no docker-compose local faz o Docker Desktop rodar a emulação via Rosetta 2 automaticamente, permitindo o download correto das dependências.

---

## 🔒 4. RESILIÊNCIA DE CREDENCIAIS (Portainer Stacks)

* **REGRA:** O arquivo `deploy/comfyui.yaml` no GitHub usa **placeholders** (`YOUR_BCRYPT_HASH_HERE`, `YOUR_API_TOKEN_HERE`) — o repo é **público**. As credenciais reais ficam apenas no Portainer (Stack file content editado direto na UI) ou em `~/.config/cortexx/secrets/`.
* **MOTIVO:** O Portainer pode limpar ou sobrescrever variáveis de ambiente dinâmicas quando ocorre uma atualização de imagem ou redeploy de container. As credenciais devem estar hardcoded no YAML do Portainer (não via Stack Env), MAS o YAML do repositório público usa placeholders.
* **FLUXO:** Editar `deploy/comfyui.yaml` local → substituir placeholders pelos valores reais → colar o YAML completo no Portainer Stack editor → salvar. NUNCA commitar os valores reais.

---

## 🧹 5. CACHE DO BROWSER (Não é Cloudflare, não é CDN)

* **REGRA:** Se o frontend Vue 3 não renderiza em produção (topbar/sidebar não aparecem, canvas vazio, erro `graph accessed before initialization`), **PRIMEIRO** limpe o cache do browser antes de investigar qualquer outra causa.
* **MOTIVO:** O ComfyUI Vue 3 frontend guarda estado no `localStorage` + `indexedDB` + disk cache. Versões antigas do frontend deixam state stale que causa `graph accessed before initialization` **mesmo com a versão correta (v1.48.4)**. Uma simples recarga (Cmd+Shift+R) **não** resolve — o disk cache e localStorage persistem.
* **SINTOMAS:** Frontend funciona localmente mas falha em produção. `cf-cache-status: BYPASS` confirma que Cloudflare não está cacheando. `transferSize: 0` indica disk cache do browser, não CDN.
* **RESOLUÇÃO (em ordem):**
  1. Hard refresh (Cmd+Shift+R) — às vezes resolve cache de JS/CSS
  2. Limpar dados do site (DevTools → Application → Storage → "Clear site data") — remove localStorage + indexedDB stale
  3. Testar em DuckDuckGo (limpa todo cache entre sessões) ou Chrome incognito — se funcionar, é cache do browser com certeza
* **NÃO FAÇA:** Rebuildar a imagem, mudar versão do frontend, purgar Cloudflare, ou fazer qualquer alteração no servidor antes de confirmar que não é cache do browser.

---

## 📋 6. FORMATO DE WORKFLOW JSON (UI vs API)

* **REGRA:** Workflows salvos em `/workspace/user/default/workflows/` para a sidebar do ComfyUI **DEVEM** estar em **formato UI** (com `nodes` array, `links` array, `widgets_values`, `pos`, `size`, `version: "0.4"`), **NÃO** em formato API (com `class_type`, `inputs` como dict de node IDs string).
* **MOTIVO:** O frontend Vue do ComfyUI só consegue carregar workflow em formato UI. Workflow em formato API (com chaves `"1"`, `"2"` e `class_type`) é aceito apenas pelo endpoint `POST /api/prompt` — clicar no workflow na sidebar **não faz nada** (sem erro, sem canvas update, sem console error — falha silenciosa).
* **COMO IDENTIFICAR:**
  - **Formato UI:** Tem `nodes` (array), `links` (array), `last_node_id`, `last_link_id`, `version`
  - **Formato API:** Tem chaves string `"1"`, `"2"` (node IDs), cada uma com `class_type` e `inputs` (dict)
* **CONVERSÃO:** Transformar API → UI exige:
  1. Criar array `nodes` com `widgets_values` extraídos dos `inputs` (valores não-link)
  2. Criar array `links` onde cada `["node_id", slot]` vira `[link_id, from_node, from_slot, to_node, to_slot, type]`
  3. Adicionar `pos`, `size`, `flags`, `order`, `mode`, `properties` a cada node
  4. Setar `version: "0.4"` no topo

---

## 🏷️ 7. NOMES CORRETOS DOS NODES AICustomURL

* **REGRA:** O padrão de nomenclatura dos nodes do `ComfyUI-AI-CustomURL` é **`<Function>_AICustomURL`** (ex: `ImageGeneration_AICustomURL`), **NÃO** `AICustomURL_<Function>` (ex: `AICustomURL_Image` não existe).
* **NODES CORRETOS:**
  - `TextGeneration_AICustomURL` — texto/chat
  - `ImageGeneration_AICustomURL` — geração de imagem
  - `VideoGeneration_AICustomURL` — geração de vídeo
  - `VideoRetrieve_AICustomURL` — poll de vídeo async
  - `VideoPreview_AICustomURL` — preview de vídeo
  - `SpeechGeneration_AICustomURL` — speech/audio
  - `ImageLoader_AICustomURL` — carregar imagem de URL
  - `SaveVideo_AICustomURL` — salvar vídeo
* **VERIFICAÇÃO:** Sempre confirme o nome do node via `GET /object_info/<nome>` antes de construir workflow JSON. Um nome errado retorna `400 Bad Request` no `/api/prompt` sem mensagem clara.

---

## 🚫 8. MODO DE OPERAÇÃO — 100% API (Sem Inferência Local)

* **REGRA:** O servidor Hetzner (62GB RAM) roda ComfyUI em **modo API-only** — sem modelos locais, sem checkpoints, sem inferência local. Todos os workflows chamam APIs externas (OmniRoute, NexusMind/Grok).
* **MOTIVO:** Flux Schnell fp8 (17GB) + VAE (13GB) + t5xxl (4.6GB) + clip_l (235MB) = ~35GB de modelos consomem toda a RAM do servidor (62GB total → 1.6GB livre),-starving outros serviços (OmniRoute, NexusMind, Portainer). O user confirmou: *"nuuu pode remover os modelos vamos deixar apenas para api mesmo"*.
* **PROIBIDO:** Baixar modelos para `/workspace/models/` sem verificação de impacto na RAM. Se adicionar modelo local, monitore RAM livre com `GET /system_stats` após carregar.
* **EXCEÇÃO:** Se for absolutamente necessário inferência local, use modelo pequeno (SD 1.5, ~4GB RAM) ou servidor dedicado com GPU.

---

_Leitura complementar: A skill `comfyui-swarm-deployment` em `~/.hermes/skills/` documenta TODOS os detalhes técnicos, armadilhas, e procedimentos de build/deploy/debug._

---

## 🎥 9. NEXUSVIDEO — IMAGE-TO-VIDEO REQUER URL PÚBLICA (MinIO)

* **REGRA:** O node `NexusVideo` em modo image-to-video (quando recebe um tensor `IMAGE` do `LoadImage`) precisa fazer upload da imagem para o **MinIO S3** antes de chamar a API do xAI/Grok. Data URLs e `image_url` como string **NÃO funcionam** — o xAI ignora silenciosamente e gera text-to-video puro.
* **FORMATO CORRETO da API xAI:** `"image": {"url": "https://..."}` (objeto com `url`), **NÃO** `"image_url": "..."` (string).
* **MINIO ENV VARS OBRIGATÓRIAS:** `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `MINIO_SECURE` — injetadas via Portainer service spec (não no repo público). Sem essas vars, o node retorna erro de upload e o i2v falha (t2v ainda funciona).
* **DETALHES TÉCNICOS COMPLETOS:** Ver `docs/NEXUSVIDEO_I2V.md` — arquitetura, API, armadilhas, troubleshooting.
* **ADRs:** `docs/adr/0001-xai-image-url-format.md`, `docs/adr/0002-minio-s3-image-hosting.md`

---

## 🔗 10. PREVIEWVIDEO USA `video_path`, NÃO `filepath`

* **REGRA:** O node `PreviewVideo` (do llm-toolkit) aceita apenas o input `video_path` (STRING, widget). **NUNCA** use `filepath` como nome de input — o método `preview()` não aceita esse argumento e o workflow falha com `TypeError`.
* **MOTIVO:** Workflows salvos no IndexedDB do browser podem ter inputs fantasma (`filepath`) que não existem na definição real do node. O ComfyUI tenta passar todos os inputs como kwargs e quebra.
* **FIX:** Nos links do workflow, conectar `NexusVideo.video_url` → `PreviewVideo.video_path`. **NUNCA** criar um input com nome `filepath` no PreviewVideo.

---

## 📦 11. DEPS DE CUSTOM NODES INSTALADOS EM RUNTIME

* **REGRA:** Custom nodes instalados via ComfyUI-Manager em produção persistem no volume, mas suas deps Python **NÃO** estão na imagem Docker. O `entrypoint.sh` tem um bloco que instala deps conhecidas antes de iniciar o ComfyUI.
* **MOTIVO:** Se você instalar um custom node via Manager e ele precisar de uma lib Python não-bundled, o ComfyUI falha ao carregar o node no próximo restart. O entrypoint resolve isso instalando a dep automaticamente.
* **COMO ADICIONAR NOVA DEP:** Edite `entrypoint.sh`, adicione `pip install <dep>` dentro do bloco `if [ -d /workspace/custom_nodes/<nome> ]`, faça build nova imagem e deploy.
* **ADRs:** `docs/adr/0004-entrypoint-runtime-deps.md`

---

## 🚫 12. NUNCA ENVIAR `resolution` OU `duration` À API xAI

* **REGRA:** O node `NexusVideo` tem widgets `resolution` e `duration` na UI, mas eles **NÃO são enviados** no payload da API. O xAI rejeita com HTTP 422 se esses campos estiverem presentes.
* **MOTIVO:** A docs do xAI lista esses campos como opcionais, mas o upstream do NexusMind sub2api rejeita com 422 quando presentes.
* **ADR:** `docs/adr/0003-no-resolution-duration-in-payload.md`
