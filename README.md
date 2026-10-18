# kilo-gateway

Cloudflare Worker exposing **Kilo Gateway's free models** (no account, no API
key, no fingerprinting) as a standard OpenAI/Anthropic-compatible endpoint.

[![Deploy to Cloudflare Workers](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/nullstacks/kilo-gateway)

## Why it's simple

Kilo's free tier (`api.kilo.ai/api/gateway`) requires **no auth at all** and
natively serves all three wire protocols. This worker is a transparent proxy
plus a free-model catalog — no request rewriting, no client simulation.

## Free models (current catalog)

17 in the catalog — `GET /v1/models` returns this list live (refreshed every
5 min, filtered with the same rule as
[anxkhn/free-kilo-gateway](https://github.com/anxkhn/free-kilo-gateway):
price = 0 and "free" in the name). Snapshot 2026-10-18:

| Model | Context | Modalities | Status |
|---|---|---|---|
| `kilo-auto/free` | 256K | text | ✅ verified |
| `reflection/beam-free` | 1048K | text | ✅ verified |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 1000K | text | ✅ verified |
| `nvidia/nemotron-3.5-super-vl:free` | 1000K | text+image+video | ✅ verified |
| `nvidia/nemotron-3.5-lightning:free` | 1000K | text | ✅ verified (slow, ~2 min) |
| `nvidia/nemotron-3-super-120b-a12b:free` | 262K | text | ✅ verified |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | 256K | text+audio+image+video | ✅ verified |
| `nvidia/nemotron-3.5-content-safety:free` | 128K | text+image | ✅ verified |
| `cohere/north-mini-code:free` | 256K | text | ✅ verified |
| `poolside/laguna-s-2.1:free` | 262K | text | ✅ verified |
| `poolside/laguna-xs-2.1:free` | 262K | text | ⚠️ works, provider 429 at test time |
| `thinkingmachines/inkling-small:free` | 1048K | text+image+audio | ⚠️ daily cap hit at test time (`limit_rpd`) |
| `dots-studio/dots-3-note-preview:free` | 512K | text+image | ✅ verified |
| `xingchen-agi/xing4.0-29b-a4b:free` | 262K | text | ✅ verified |
| `liquid/lfm-2.5-2.6b:free` | 65K | text | ✅ verified |
| `openrouter/free` | 200K | text+image | ✅ verified — routes to OpenRouter free models |
| `stealth/glyph-cluster` | 256K | text | ⚠️ returns encrypted reasoning, empty content |

Known quirks: some providers enforce **per-model daily caps** (`limit_rpd`
429 — switch model or wait for reset for that model). The catalog rotates
upstream; `/v1/models` is always authoritative.

## Endpoints

```
GET  /v1/models            free catalog (context/modalities annotated)
POST /v1/chat/completions  OpenAI Chat wire (stream + non-stream)
POST /v1/messages          Anthropic Messages wire
POST /v1/responses         OpenAI Responses wire
GET  /health
```

## Deploy

**Option A — button above.**

**Option B — CLI:**

```bash
git clone https://github.com/nullstacks/kilo-gateway
cd kilo-gateway
npx wrangler deploy
```

No secrets required. Optionally set `API_KEY`-style protection yourself —
the worker forwards any `Authorization` header to Kilo, so a caller with a
paid Kilo key gets paid models too:

```bash
curl https://<your-worker>.workers.dev/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-kilo-key>" \
  -d '{"model":"z-ai/glm-5","messages":[{"role":"user","content":"hi"}]}'
```

## Usage

```bash
curl https://<your-worker>.workers.dev/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"cohere/north-mini-code:free","messages":[{"role":"user","content":"hi"}]}'
```

```bash
# OpenCode / any OpenAI-compatible tool
base_url = https://<your-worker>.workers.dev/v1
api_key  = anything (ignored for free models)
```

## License

MIT
