# server.py — kilo-gateway as a local Python API (Flask).
#
# Same wire surface as worker.js — a transparent proxy plus a free-models
# catalog for Kilo Gateway (api.kilo.ai/api/gateway):
#
#   GET  /v1/models            free-model catalog (price = 0 and "free" in name)
#   POST /v1/chat/completions  OpenAI Chat wire (stream + non-stream)
#   POST /v1/messages          Anthropic Messages wire
#   POST /v1/responses         OpenAI Responses wire
#   GET  /health
#
# Paid models: if the caller sends an Authorization header (their Kilo key),
# it is forwarded and paid models work too. Free models never need it.
# Only headers that look like real Kilo keys (sk-/pk-) are forwarded —
# harness placeholder keys would break the keyless free tier.
#
# Run:  python server.py                     # 0.0.0.0:8080 (PORT/HOST override)
#       gunicorn -w 4 -b 0.0.0.0:8080 server:app   # production
#
# Deps: flask + httpx. No secrets required.

import json
import os
import threading
import time

import httpx
from flask import Flask, Response, request

UPSTREAM = "https://api.kilo.ai/api/gateway"
KILO_MODELS_API = "https://api.kilo.ai/api/gateway/models"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Api-Key, Anthropic-Version, Anthropic-Beta",
    "Access-Control-Expose-Headers": "X-Gateway-Upstream-Status",
    "Access-Control-Max-Age": "86400",
}

PROXY_PATHS = {"/v1/chat/completions", "/v1/messages", "/v1/responses",
               "/v1/completions", "/v1/embeddings"}

MODELS_TTL = 5 * 60  # seconds

app = Flask(__name__)

# Shared connection pool (thread-safe); generous read timeout for slow models.
_client = httpx.Client(timeout=httpx.Timeout(600.0, connect=30.0))

# --- models catalog (5-minute cache, per worker) ------------------------------------

_models_lock = threading.Lock()
_models_cache = {"at": 0.0, "data": None}


def _is_free_model(m):
    pricing = m.get("pricing") or {}
    try:
        free_pricing = float(pricing.get("prompt") or "0") == 0 and \
            float(pricing.get("completion") or "0") == 0
    except (TypeError, ValueError):
        free_pricing = False
    name = (m.get("name") or m.get("id") or "").lower()
    return free_pricing and "free" in name


def load_models():
    now = time.time()
    with _models_lock:
        if _models_cache["data"] and now - _models_cache["at"] < MODELS_TTL:
            return _models_cache["data"]
    resp = httpx.get(KILO_MODELS_API, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"Kilo models API HTTP {resp.status_code}")
    j = resp.json()
    all_models = j if isinstance(j, list) else (j.get("data") or [])
    free = [m for m in all_models if _is_free_model(m)]
    catalog = [{
        "id": m.get("id"),
        "object": "model",
        "created": 0,
        "owned_by": (m.get("id") or "kilo").split("/")[0],
        "name": m.get("name") or m.get("id"),
        "free": True,
        "context_length": m.get("context_length"),
        "max_completion_tokens": (m.get("top_provider") or {}).get("max_completion_tokens"),
        "input_modalities": (m.get("architecture") or {}).get("input_modalities") or ["text"],
        "description": m.get("description") or "",
    } for m in free]
    data = {"all": all_models, "catalog": catalog}
    with _models_lock:
        _models_cache.update(at=time.time(), data=data)
    return data


# --- helpers --------------------------------------------------------------------------


def _json(data, status=200, extra=None):
    headers = {"content-type": "application/json", **CORS_HEADERS, **(extra or {})}
    return Response(json.dumps(data), status=status, headers=headers)


def _looks_like_real_key(value):
    value = value or ""
    value = value[7:].strip() if value.lower().startswith("bearer ") else value
    return value.lower().startswith(("sk-", "pk-"))


# --- proxy ------------------------------------------------------------------------------


def _proxy(path):
    auth = request.headers.get("authorization") or ""
    api_key = request.headers.get("x-api-key") or ""

    # Kilo rejects *any* invalid Authorization outright — even for free models
    # (harnesses like Hermes always send a placeholder key). Only forward the
    # header when it looks like a real Kilo key (sk-...); otherwise drop it so
    # the request rides the keyless free tier.
    looks_real = _looks_like_real_key(auth) or _looks_like_real_key(api_key)
    headers = {"content-type": "application/json"}
    if auth and looks_real:
        headers["authorization"] = auth
    if api_key and looks_real:
        headers["x-api-key"] = api_key
    av = request.headers.get("anthropic-version")
    if av:
        headers["anthropic-version"] = av
    ab = request.headers.get("anthropic-beta")
    if ab:
        headers["anthropic-beta"] = ab

    body = request.get_data() if request.method == "POST" else None
    query = request.query_string.decode("latin-1") if request.query_string else ""
    try:
        # stream=True keeps the body unread so it can pass straight through
        # (SSE included); the response must be fully consumed inside the
        # generator while the client is still open.
        req = _client.build_request(request.method, UPSTREAM + path + ("?" + query if query else ""),
                                    headers=headers, content=body)
        resp = _client.send(req, stream=True)
    except httpx.HTTPError as exc:
        return _json({"error": {"type": "upstream_error",
                                "message": f"Upstream fetch failed: {exc}"}}, 502)

    out_headers = {"x-gateway-upstream-status": str(resp.status_code), **CORS_HEADERS}
    ct = resp.headers.get("content-type")
    if ct:
        out_headers["content-type"] = ct
    for h in ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset", "retry-after"):
        v = resp.headers.get(h)
        if v:
            out_headers[h] = v

    def generate():
        try:
            for chunk in resp.iter_raw():
                yield chunk
        finally:
            resp.close()

    return Response(generate(), status=resp.status_code, headers=out_headers)


# --- routes -------------------------------------------------------------------------------


@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    n = None
    try:
        n = len(load_models()["catalog"])
    except Exception:  # noqa: BLE001
        pass
    return _json({
        "ok": True,
        "service": "kilo-gateway (python)",
        "upstream": UPSTREAM,
        "free_models_cached": n,
        "routes": ["/v1/models", "/v1/chat/completions", "/v1/messages", "/v1/responses"],
        "note": "Free models need no key. Send your Kilo API key as Authorization: Bearer <key> for paid models.",
    })


@app.route("/v1/models", methods=["GET"])
def models():
    try:
        data = load_models()
    except Exception as exc:  # noqa: BLE001
        return _json({"error": {"type": "upstream_error", "message": str(exc)}}, 502)
    return _json({"object": "list", "data": data["catalog"],
                  "kilo_total_models": len(data["all"])})


@app.before_request
def _options_short_circuit():
    if request.method == "OPTIONS":
        return Response(status=204)


@app.route("/<path:path>", methods=["POST"])
def proxy(path):
    full = "/" + path
    if full not in PROXY_PATHS:
        return _json({
            "error": {
                "type": "not_found",
                "message": f"Unsupported POST {full}. Use POST /v1/chat/completions, /v1/messages, /v1/responses, or GET /v1/models.",
            },
        }, 404)
    return _proxy(full)


@app.route("/<path:_any>", methods=["GET", "POST"])
def not_found(_any):
    return _json({
        "error": {
            "type": "not_found",
            "message": f"Unsupported {request.method} /{_any}. Use POST /v1/chat/completions, /v1/messages, /v1/responses, or GET /v1/models.",
        },
    }, 404)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0")
    app.run(host=host, port=port, threaded=True)
