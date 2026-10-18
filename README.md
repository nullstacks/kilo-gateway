# kilo-gateway

Cloudflare Worker exposing **Kilo Gateway's free models** (no account, no API
key, no fingerprinting) as a standard OpenAI/Anthropic-compatible endpoint.

[![Deploy to Cloudflare Workers](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/nullstacks/kilo-gateway)

## Why it's simple

Kilo's free tier (`api.kilo.ai/api/gateway`) requires **no auth at all** and
natively serves all three wire protocols. This worker is a transparent proxy
plus a free-model catalog — no request rewriting, no client simulation.

## Free models (17 in catalog, 14 verified 2026-10-18)

`GET /v1/models` returns the live list (refreshed every 5 min, filtered with
the same rule as [anxkhn/free-kilo-gateway](https://github.com/anxkhn/free-kilo-gateway):
price = 0 and "free" in the name). Highlights:

- `kilo-auto/free` — auto-router (256K ctx)
- `reflection/beam-free` (1048K ctx)
- `nvidia/nemotron-3-ultra-550b-a55b:free` (1000K ctx)
- `nvidia/nemotron-3.5-super-vl:free` (vision, 1000K ctx)
- `thinkingmachines/inkling-small:free` (vision, 1048K ctx)
- `cohere/north-mini-code:free`, `poolside/laguna-s-2.1:free`, ...

Known quirks: some providers enforce **per-model daily caps** (`limit_rpd`
429 — switch model or wait for reset); `stealth/glyph-cluster` returns
encrypted-reasoning with empty content.

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
