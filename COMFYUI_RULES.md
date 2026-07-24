# ⚠️ REGRAS CRÍTICAS DE DESENVOLVIMENTO E DEPLOY DO COMFYUI

Este repositório possui diretrizes arquiteturais estritas. **Todos os agentes de IA e desenvolvedores devem seguir estas regras sem exceção.**

---

## 📌 1. PIN DE VERSÃO DO FRONTEND (Evitar Fallback Silencioso)
*   **REGRA:** **NUNCA** utilize `--front-end-version Comfy-Org/ComfyUI_frontend@latest` ou versões não testadas no `entrypoint.sh` ou flags de inicialização.
*   **MOTIVO:** Versões mais recentes do frontend do ComfyUI (ex: `1.48.5`) possuem incompatibilidades com o backend `v0.28.0` e lançam a exceção:
    `TypeError: Cannot read properties of undefined (reading '_nodes') at main.ts:113:4`
    Isso quebra a inicialização do Vue 3 silenciosamente e reverte a tela para o menu clássico (antigo), fazendo parecer que o deploy falhou ou foi revertido.
*   **VERSÃO DE REFERÊNCIA ESTÁVEL:** Sempre use a tag fixa **`Comfy-Org/ComfyUI_frontend@v1.48.4`**.

---

## 🎨 2. ERRO DE FONTE MONOSPACE (Google Translate)
*   **PROBLEMA:** Se a interface do ComfyUI carregar com uma fonte monospace (Courier/linha de código) no lugar da fonte sans-serif limpa padrão, o motivo é o uso de extensões de tradução (ex: **Google Translate** no Chrome).
*   **EXPLICAÇÃO:** O Google Tradutor envolve os blocos de texto em tags `<font>`. Como o CSS da nova interface do ComfyUI não estiliza a tag `<font>`, o navegador herda a fonte monospace padrão de sistema.
*   **SOLUÇÃO:** **NÃO tente alterar o CSS do repositório para corrigir isso.** A solução correta é orientar o usuário a desativar a tradução automática para o domínio do ComfyUI (adicionando "Nunca traduzir este site" nas configurações da extensão).

---

## 🛠️ 3. DEPLOY LOCAL (Apple Silicon / Mac)
*   **REGRA:** Quando executar a aplicação localmente no Mac (`docker compose up --build`), a configuração da plataforma **deve** ser fixada em `platform: linux/amd64`.
*   **MOTIVO:** Os pacotes de PyTorch CPU (`torch==2.5.1+cpu` etc.) não possuem builds estáveis pré-compilados para a arquitetura `arm64` (Apple Silicon) em repositórios padrão. Forçar a plataforma `amd64` no docker-compose local faz o Docker Desktop rodar a emulação via Rosetta 2 automaticamente, permitindo o download correto das dependências.

---

## 🔒 4. RESILIÊNCIA DE CREDENCIAIS (Portainer Stacks)
*   **REGRA:** Todas as chaves de API, senhas hash de login e tokens de autenticação **devem** ser declarados diretamente de forma estática (hardcoded) no arquivo YAML de deploy (`deploy/comfyui.yaml`), em vez de serem injetados dinamicamente via a interface de Stack Env do Portainer.
*   **MOTIVO:** O Portainer pode limpar ou sobrescrever variáveis de ambiente dinâmicas quando ocorre uma atualização de imagem ou redeploy de container, o que quebra a criptografia das chaves salvas e invalida os tokens cadastrados.
