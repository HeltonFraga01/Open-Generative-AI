# Cinematic Image Generator · Higgsfield + OmniRoute

**Langflow Flow UUID:** `2ab4f4b3-8ee1-4674-8f9b-5d6d333bd17e`  
**Langflow Project:** `4715662f-102b-49fb-884b-739c993992e8`  
**Langflow URL:** https://ai.fragaai.com.br  
**Created:** 2026-07-26

## Overview

A deterministic, native-only Langflow flow that takes a cinematic prompt
(Higgsfield preset + subject), expands it into a full 8-slot cinematic
prompt, and calls the OmniRoute image generation API to produce a cinematic
image. The image URL is returned in the ChatOutput.

## Flow Architecture

```
ChatInput → Prompt Template → TypeConverter (Message→JSON) → APIRequest (POST) → ChatOutput
```

| Node | Component Type | Role |
|---|---|---|
| ChatInput | `ChatInput` | User types `PRESET | subject` (e.g. `NEON CITY \| cyberpunk samurai`) |
| Prompt Template | `Prompt Template` | Expands preset+subject into full cinematic prompt (8-slot grammar) + formats as JSON body for the OmniRoute API. Uses mustache mode (`{{input}}`). |
| TypeConverter | `TypeConverter` | Converts Message (JSON string) → Data object with parsed dict, for use as HTTP body |
| APIRequest | `APIRequest` | POST to `https://omniroute.cortexx.online/v1/images/generations` with body `{model, prompt, n, size}` and `Authorization` header |
| ChatOutput | `ChatOutput` | Displays the API response (image URL on success, error details on failure) |

## OmniRoute API

- **Endpoint:** `POST https://omniroute.cortexx.online/v1/images/generations`
- **Model:** `kc/gpt-5.4-image-2` (kilocode route, 409K ctx, vision+thinking)
- **Body format:** OpenAI-compatible `{"model": "...", "prompt": "...", "n": 1, "size": "1024x1024"}`
- **Auth:** `Authorization: Bearer <OMNIROUTE_API_KEY>`

## Authentication (via Tweak)

The flow does NOT hardcode any API keys. The `Authorization` header has
placeholder value `Bearer TWEAK_AT_RUNTIME`. To use the flow:

### Via Langflow API (tweaks parameter)

```bash
curl -X POST "https://ai.fragaai.com.br/api/v1/run/2ab4f4b3-8ee1-4674-8f9b-5d6d333bd17e?stream=false"   -H "x-api-key: <LANGFLOW_API_KEY>"   -H "Content-Type: application/json"   -d '{
    "input_value": "NEON CITY | cyberpunk samurai in rain",
    "tweaks": {
      "APIRequest-image": {
        "headers": [
          {"key": "Content-Type", "value": "application/json"},
          {"key": "Authorization", "value": "Bearer omni_xxxxxxxx"}
        ]
      }
    }
  }'
```

### Via Langflow Playground (UI)

1. Open the flow in the Langflow Playground
2. Click on the `APIRequest-image` node
3. Replace the `Authorization` header value `TWEAK_AT_RUNTIME` with `Bearer <your_omniroute_key>`
4. Run the flow with input `PRESET | subject`

## Available Higgsfield Presets

The Prompt Template includes 18 preset seeds (camera + lighting + style):

`EARTH ZOOM`, `FLOAT SPIN`, `ORBIT 360`, `ICE STATUE`, `NEON CITY`,
`STORM GIANT`, `IN THE DARK`, `DRIFT RACING`, `MOONWALK`,
`ORBITAL PRESENCE`, `FREE FALL`, `RED CARPET`, `SOUL FIGHTER`,
`SUMMER HAZE`, `3D RENDER`, `CLAY FIGURINE`, `ACTION FIGURE`,
`BLUE DEPTH`

See the full 48-preset catalog in the `higgsfield-cinematic-flows` skill.

## Policy Compliance (WaaS Prospector)

- ✅ ZERO custom components — all 5 nodes are native Langflow components
- ✅ DAG deterministic — no Agent with expensive tools, no loops
- ✅ 1 ChatInput → ... → 1 ChatOutput
- ✅ Auth via tweak — no hardcoded API keys
- ✅ UUID of flow is immutable (2ab4f4b3-8ee1-4674-8f9b-5d6d333bd17e)

## Smoke Test Result

```
Input: "NEON CITY | cyberpunk samurai in rain"
Status: 200 OK (flow executed successfully)
API Result: 401 "Invalid API key" (expected — placeholder auth not yet replaced)
```

The flow correctly:
1. Parsed the ChatInput message
2. Expanded the prompt template (no f-string errors)
3. Converted the Message to JSON data
4. Sent POST to OmniRoute with the JSON body
5. Returned the API response (including the 401 error) to ChatOutput

When the auth placeholder is replaced with a valid OmniRoute key, the flow
will return the generated image URL in the ChatOutput.
