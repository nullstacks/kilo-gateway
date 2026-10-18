// kilo-gateway — Cloudflare Worker
// Exposes Kilo Gateway's free models (no account, no API key) as a standard
// OpenAI/Anthropic-compatible endpoint for any external harness.
//
// Kilo Gateway (api.kilo.ai) natively serves all three wire protocols and its
// free tier requires no auth, so this worker is a transparent proxy plus a
// free-models catalog:
//
//   GET  /v1/models            free-model catalog (from Kilo's model list,
//                              filter: prompt+completion price = 0, "free" in
//                              name — same rule as anxkhn/free-kilo-gateway)
//   POST /v1/chat/completions  OpenAI Chat wire (stream + non-stream)
//   POST /v1/messages          Anthropic Messages wire
//   POST /v1/responses         OpenAI Responses wire
//   GET  /health
//
// Paid models: if the caller sends an Authorization header (their Kilo key),
// it is forwarded and paid models work too. Free models never need it.
// A model not in the free catalog is still proxied as-is — Kilo itself
// returns 401 PAID_MODEL_AUTH_REQUIRED when no valid key is present.

const UPSTREAM = "https://api.kilo.ai/api/gateway";
const KILO_MODELS_API = "https://api.kilo.ai/api/gateway/models";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Api-Key, Anthropic-Version, Anthropic-Beta",
  "Access-Control-Expose-Headers": "X-Gateway-Upstream-Status",
  "Access-Control-Max-Age": "86400",
};

function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json", ...CORS, ...extra },
  });
}

const PROXY_PATHS = new Set(["/v1/chat/completions", "/v1/messages", "/v1/responses", "/v1/completions", "/v1/embeddings"]);

function isFreeModel(m) {
  const p = m.pricing || {};
  const freePricing =
    parseFloat(p.prompt || "0") === 0 && parseFloat(p.completion || "0") === 0;
  const name = (m.name || m.id || "").toLowerCase();
  return freePricing && name.includes("free");
}

let modelsCache = { at: 0, data: null };
async function loadModels() {
  if (modelsCache.data && Date.now() - modelsCache.at < 5 * 60 * 1000)
    return modelsCache.data;
  const r = await fetch(KILO_MODELS_API);
  if (!r.ok) throw new Error(`Kilo models API HTTP ${r.status}`);
  const j = await r.json();
  const all = Array.isArray(j) ? j : j.data || [];
  const free = all.filter(isFreeModel);
  const catalog = free.map((m) => ({
    id: m.id,
    object: "model",
    created: 0,
    owned_by: m.id?.split("/")[0] || "kilo",
    name: m.name || m.id,
    free: true,
    context_length: m.context_length ?? null,
    max_completion_tokens: m.top_provider?.max_completion_tokens ?? null,
    input_modalities: m.architecture?.input_modalities ?? ["text"],
    description: m.description ?? "",
  }));
  modelsCache = { at: Date.now(), data: { all, catalog } };
  return modelsCache.data;
}

async function handleModels() {
  const { all, catalog } = await loadModels();
  return json({ object: "list", data: catalog, kilo_total_models: all.length });
}

async function proxy(request, url, pathname, env) {
  const auth = request.headers.get("authorization") || "";
  const apiKey = request.headers.get("x-api-key") || "";

  const headers = new Headers({ "content-type": "application/json" });
  // Kilo rejects *any* invalid Authorization outright — even for free models
  // (harnesses like Hermes always send a placeholder key). Only forward the
  // header when it looks like a real Kilo key (sk-...); otherwise drop it so
  // the request rides the keyless free tier.
  const looksReal = /^(sk-|pk-)/i.test(auth.replace(/^Bearer\s+/i, "")) || /^(sk-|pk-)/i.test(apiKey);
  if (auth && looksReal) headers.set("authorization", auth);
  if (apiKey && looksReal) headers.set("x-api-key", apiKey);
  const av = request.headers.get("anthropic-version");
  if (av) headers.set("anthropic-version", av);
  const ab = request.headers.get("anthropic-beta");
  if (ab) headers.set("anthropic-beta", ab);

  const init = { method: request.method, headers };
  if (request.method === "POST") init.body = await request.text();

  let resp;
  try {
    resp = await fetch(UPSTREAM + pathname + url.search, init);
  } catch (e) {
    return json({ error: { type: "upstream_error", message: `Upstream fetch failed: ${e.message}` } }, 502);
  }

  const out = new Headers();
  const ct = resp.headers.get("content-type");
  if (ct) out.set("content-type", ct);
  out.set("x-gateway-upstream-status", String(resp.status));
  out.set("access-control-allow-origin", "*");
  const rl = [];
  for (const h of ["x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset", "retry-after"]) {
    const v = resp.headers.get(h);
    if (v) rl.push([h, v]);
  }
  for (const [h, v] of rl) out.set(h, v);

  return new Response(resp.body, { status: resp.status, headers: out });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

    if (path === "/" || path === "/health") {
      let n = null;
      try { n = (await loadModels()).catalog.length; } catch {}
      return json({
        ok: true,
        service: "kilo-gateway",
        upstream: UPSTREAM,
        free_models_cached: n,
        routes: ["/v1/models", "/v1/chat/completions", "/v1/messages", "/v1/responses"],
        note: "Free models need no key. Send your Kilo API key as Authorization: Bearer <key> for paid models.",
      });
    }

    if (path === "/v1/models" && request.method === "GET") {
      try {
        return await handleModels();
      } catch (e) {
        return json({ error: { type: "upstream_error", message: e.message } }, 502);
      }
    }

    if (request.method !== "POST" || !PROXY_PATHS.has(path)) {
      return json(
        {
          error: {
            type: "not_found",
            message: `Unsupported ${request.method} ${path}. Use POST /v1/chat/completions, /v1/messages, /v1/responses, or GET /v1/models.`,
          },
        },
        404
      );
    }

    return proxy(request, url, path, env);
  },
};
