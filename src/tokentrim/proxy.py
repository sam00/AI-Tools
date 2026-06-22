"""Drop-in compressing proxy for the standard ``/v1/chat/completions`` API.

Point any chat-completions client at this proxy instead of the provider. It
compresses the ``messages`` array on ``/v1/chat/completions`` before forwarding
to the upstream provider, then streams the response straight back. Zero code
changes in your app — just change the base URL.

    tokentrim proxy --port 8787 --upstream <your-provider>/v1

Requires the ``proxy`` extra:  pip install 'tokentrim[proxy]'
"""

from __future__ import annotations

import hashlib
import json
import os
import time

from .config import get_config
from .core import compress
from .stats import get_stats
from .tokens import TokenCounter


class _ResponseCache:
    """Exact-match response cache keyed on the normalized request.

    Skips the upstream LLM call entirely when an identical request was seen
    within the TTL. Lossless and safe for deterministic requests (temperature 0);
    off by default because higher-temperature requests intentionally vary.
    """

    def __init__(self, ttl: int = 3600, max_entries: int = 1024) -> None:
        self.ttl = ttl
        self.max_entries = max_entries
        self._store: dict[str, tuple[float, dict]] = {}

    @staticmethod
    def key(body: dict) -> str:
        relevant = {
            k: body.get(k)
            for k in ("model", "messages", "temperature", "top_p", "tools", "tool_choice", "response_format")
        }
        blob = json.dumps(relevant, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get(self, body: dict) -> dict | None:
        k = self.key(body)
        hit = self._store.get(k)
        if not hit:
            return None
        created, value = hit
        if self.ttl > 0 and (time.time() - created) > self.ttl:
            self._store.pop(k, None)
            return None
        return value

    def put(self, body: dict, value: dict) -> None:
        if len(self._store) >= self.max_entries:
            self._store.pop(next(iter(self._store)), None)
        self._store[self.key(body)] = (time.time(), value)


def create_app(upstream: str | None = None):
    import httpx
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, Response, StreamingResponse

    cfg = get_config()
    upstream_base = (upstream or os.getenv("TOKENTRIM_UPSTREAM_BASE_URL") or "").rstrip("/")
    if not upstream_base:
        raise ValueError(
            "upstream base URL is required: pass --upstream or set "
            "TOKENTRIM_UPSTREAM_BASE_URL to your provider's /v1 base URL"
        )
    counter = TokenCounter(backend=cfg.tokenizer, model=cfg.model)

    app = FastAPI(title="TokenTrim proxy", version="0.1.0")
    client = httpx.AsyncClient(timeout=httpx.Timeout(600.0))

    cache_enabled = os.getenv("TOKENTRIM_CACHE_RESPONSES", "0").strip().lower() in {"1", "true", "yes", "on"}
    response_cache = _ResponseCache(ttl=int(os.getenv("TOKENTRIM_CACHE_TTL", "3600")))

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok", "upstream": upstream_base, "response_cache": cache_enabled}

    @app.get("/stats")
    async def stats():
        return get_stats().to_dict()

    def _forward_headers(request: Request) -> dict:
        headers = {}
        for key, value in request.headers.items():
            lk = key.lower()
            if lk in {"host", "content-length", "accept-encoding", "connection"}:
                continue
            headers[key] = value
        return headers

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        body = await request.json()
        messages = body.get("messages")
        if isinstance(messages, list) and cfg.enabled:
            before = sum(counter.count(_text(m)) for m in messages)
            body["messages"] = compress(messages, cfg)
            after = sum(counter.count(_text(m)) for m in body["messages"])
            saved = max(0, before - after)
        else:
            saved = 0

        url = f"{upstream_base}/chat/completions"
        headers = _forward_headers(request)

        # Exact-match response cache: skip the upstream call entirely on a hit.
        if cache_enabled and not body.get("stream"):
            cached = response_cache.get(body)
            if cached is not None:
                return JSONResponse(
                    status_code=200,
                    content=cached,
                    headers={"x-tokentrim-tokens-saved": str(saved), "x-tokentrim-cache": "hit"},
                )

        if body.get("stream"):
            upstream_req = client.build_request("POST", url, json=body, headers=headers)
            upstream_resp = await client.send(upstream_req, stream=True)

            async def relay():
                async for chunk in upstream_resp.aiter_raw():
                    yield chunk
                await upstream_resp.aclose()

            resp_headers = {"x-tokentrim-tokens-saved": str(saved)}
            return StreamingResponse(
                relay(),
                status_code=upstream_resp.status_code,
                media_type=upstream_resp.headers.get("content-type", "text/event-stream"),
                headers=resp_headers,
            )

        upstream_resp = await client.post(url, json=body, headers=headers)
        payload = _safe_json(upstream_resp)
        if cache_enabled and upstream_resp.status_code == 200 and "error" not in payload:
            response_cache.put(body, payload)
        return JSONResponse(
            status_code=upstream_resp.status_code,
            content=payload,
            headers={"x-tokentrim-tokens-saved": str(saved), "x-tokentrim-cache": "miss"},
        )

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def passthrough(path: str, request: Request):
        # Transparently forward any other endpoint (models, embeddings, etc.).
        url = f"{upstream_base}/{path}"
        headers = _forward_headers(request)
        data = await request.body()
        upstream_resp = await client.request(
            request.method, url, content=data, headers=headers, params=request.query_params
        )
        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            media_type=upstream_resp.headers.get("content-type"),
        )

    return app


def _text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"error": "non-json upstream response", "body": resp.text[:2000]}


def run_proxy(host: str | None = None, port: int | None = None, upstream: str | None = None) -> None:
    import uvicorn

    cfg = get_config()
    host = host or os.getenv("TOKENTRIM_PROXY_HOST", "127.0.0.1")
    port = port or int(os.getenv("TOKENTRIM_PROXY_PORT", "8787"))
    resolved_upstream = upstream or os.getenv("TOKENTRIM_UPSTREAM_BASE_URL")
    if not resolved_upstream:
        raise SystemExit(
            "[tokentrim] set --upstream or TOKENTRIM_UPSTREAM_BASE_URL to your "
            "provider's /v1 base URL"
        )
    app = create_app(upstream=resolved_upstream)
    print(f"[tokentrim] proxy on http://{host}:{port}  → upstream {resolved_upstream}")
    print(f"[tokentrim] level={cfg.level} min_tokens={cfg.min_tokens} reversible={cfg.reversible}")
    uvicorn.run(app, host=host, port=port, log_level="info")
