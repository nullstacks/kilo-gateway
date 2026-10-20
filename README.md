# kilo-gateway

**Kilo Gateway's free models** (no account, no API key, no fingerprinting) as
a standard OpenAI/Anthropic-compatible endpoint — deploy as a Cloudflare
Worker **or run the Python Flask server locally/on any box**.

[![Deploy to Cloudflare Workers](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/nullstacks/kilo-gateway)

## Two runtimes, same API

| | Cloudflare Worker | Python (Flask) |
|---|---|---|
| File | `worker.js` | `server.py` |
| Runtime | edge, no server | local machine, VPS, Docker, systemd… |
| Install | `npx wrangler deploy` | `pip install -r requirements.txt` |
| Secrets | none | none |

Both expose the identical endpoints and behave identically: transparent
proxy plus a free-model catalog, real-key detection, rate-limit header
passthrough.

## Why it's simple

Kilo's free tier (`api.kilo.ai/api/gateway`) requires **no auth at all** and
natively serves all three wire protocols. This gateway is a transparent proxy
plus a free-model catalog — no request rewriting, no client simulation.

## Free models (current catalog)

`GET /v1/models` returns the live list (refreshed every 5 min, filtered with
the same rule as [anxkhn/free-kilo-gateway](https://github.com/anxkhn/free-kilo-gateway):
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

## Deploy to Cloudflare Workers

**Option A — button above.**

**Option B — CLI:**

```bash
git clone https://github.com/nullstacks/kilo-gateway
cd kilo-gateway
npx wrangler deploy
```

## Run the Python server

```bash
pip install -r requirements.txt          # flask + httpx
python3 server.py                        # serves on 0.0.0.0:8080 (PORT/HOST to override)
```

Production options:

```bash
gunicorn -w 4 -b 0.0.0.0:8080 server:app          # WSGI, stateless — scale freely
flask --app server run --host 0.0.0.0 --port 8080 # dev server
```

A `Dockerfile` is included: `docker build -t kilo-gateway . && docker run -p 8080:8080 kilo-gateway`.

No secrets or environment variables required. Optionally put your own
API-key protection (auth proxy, reverse-proxy basic auth, …) in front.

## Usage

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"cohere/north-mini-code:free","messages":[{"role":"user","content":"hi"}]}'
```

```bash
# OpenCode / any OpenAI-compatible tool
base_url = http://localhost:8080/v1
api_key  = anything (ignored for free models)
```

Paid models: send your Kilo key as `Authorization: Bearer <key>` (or
`X-Api-Key`) — only headers that look like real Kilo keys (`sk-`/`pk-`) are
forwarded, so harness placeholder keys don't break the keyless free tier:

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-kilo-key>" \
  -d '{"model":"z-ai/glm-5","messages":[{"role":"user","content":"hi"}]}'
```

## License

MIT
