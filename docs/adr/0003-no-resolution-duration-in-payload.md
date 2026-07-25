# ADR-0003: resolution e duration não enviados à API xAI

**Date:** 2026-07-25
**Status:** Accepted

## Context

Os campos `resolution` (ex: "720p") e `duration` (ex: 5) aparecem como widgets no node `NexusVideo` na UI do ComfyUI. A primeira implementação os enviava no payload JSON da API.

**Problema:** o xAI upstream retornava **HTTP 422** com a mensagem: *"xAI upstream returned status 422"*.

## Investigation

Testamos dois payloads idênticos:

```python
# Com resolution/duration:
{"model": "grok-imagine-video-1.5", "prompt": "...", "resolution": "720p", "duration": 5}
# → 422

# Sem resolution/duration:
{"model": "grok-imagine-video-1.5", "prompt": "...", "n": 1}
# → 200 ✅
```

A documentação do xAI lista `resolution` e `duration` como campos opcionais (`null | string` e `integer | null`), mas o upstream do NexusMind sub2api rejeita quando esses campos estão presentes.

## Decision

O node `NexusVideo` mantém os widgets `resolution` e `duration` na UI (para referência do usuário e futura compatibilidade), mas **não os inclui** no payload enviado à API. Apenas `model`, `prompt`, `n`, e `image` (quando aplicável) são enviados.

## Consequences

- Usuário pode ajustar os widgets na UI, mas isso não afeta a geração (por enquanto)
- Se o upstream do NexusMind mudar para aceitar esses campos, pode-se reabilitá-los no payload
