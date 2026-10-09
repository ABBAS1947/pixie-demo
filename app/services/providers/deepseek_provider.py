"""DeepSeek provider — wraps the DeepSeek OpenAI-compatible chat-completions API
into the :class:`LLMProvider` interface.

Keeps the same shared httpx connection pool, streaming tool-call
accumulation, and reasoning-content handling so behaviour is identical.
"""
import asyncio
import json as _json

import httpx
import logging

from app.core.config import settings
from app.services.llm_provider import LLMProvider

# ── shared connection pool (one per process) ──────────────────────────
_client: httpx.AsyncClient | None = None
_log = logging.getLogger(__name__)


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10, read=settings.llm_timeout_read, write=10, pool=5
            ),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _client


class DeepSeekProvider(LLMProvider):
    """DeepSeek via the OpenAI-compatible chat-completions API."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self._model = model or settings.deepseek_model
        self._api_key = api_key or settings.deepseek_api_key
        self._base_url = (base_url or settings.deepseek_base_url).rstrip("/")

    # ── LLMProvider interface ──────────────────────────────────────────

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> dict:
        from app.services.processing_boundary import permit_external_processing
        await permit_external_processing()
        # DeepSeek's OpenAI-compatible JSON mode requires the prompt itself
        # to mention JSON. Keep this invariant in the provider boundary so
        # every structured caller (extraction, review generation, grading)
        # remains valid even when its domain prompt omits that implementation
        # detail.
        request_messages = messages
        if json_mode and not any("json" in str(m.get("content", "")).lower() for m in messages):
            request_messages = [
                {"role": "system", "content": "Return the requested result as valid JSON."},
                *messages,
            ]
        payload: dict = {
            "model": self._model,
            "messages": request_messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
            payload["thinking"] = {"type": "disabled"}
        if tools:
            payload["tools"] = tools

        client = _get_client()
        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        retries = settings.llm_max_retries
        resp = None
        # Bounded retry on transient failures (connect/read blips + server
        # pressure) so a flaky gateway auto-recovers instead of the call
        # silently dropping. Non-streaming only (streaming can't restart mid-way).
        for attempt in range(retries + 1):
            try:
                await permit_external_processing()
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code in (408, 429, 500, 502, 503, 504):
                    if attempt >= retries:
                        _log.error("LLM provider HTTP failure status=%s", resp.status_code)
                        resp.raise_for_status()
                    await asyncio.sleep(1 + attempt)
                    continue
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError:
                    _log.error("LLM provider HTTP failure status=%s", resp.status_code)
                    raise
                break
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
                if attempt >= retries:
                    raise exc
                await asyncio.sleep(1 + attempt)
        data = resp.json()
        choice = data["choices"][0]
        message = choice.get("message") or {}
        result: dict = {"content": message.get("content", "") or "",
                        "finish_reason": choice.get("finish_reason"),
                        "usage": data.get("usage", {}), "model": data.get("model", self._model)}

        # Some providers return tool_calls at the top level of the message
        raw_calls = message.get("tool_calls") or []
        if raw_calls:
            result["tool_calls"] = [
                {
                    "id": tc.get("id", ""),
                    "name": tc.get("function", {}).get("name", ""),
                    "arguments": tc.get("function", {}).get("arguments", ""),
                }
                for tc in raw_calls
            ]

        from app.services.processing_boundary import check_delivery_fence
        check_delivery_fence()
        return result

    async def stream(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ):
        """Streaming completion — yields the same types as the standard
        ``LLMProvider.stream`` format:
        - **without tools** → plain ``str`` chunks
        - **with tools** → ``{"text": "..."}`` / ``{"tool_calls": [...]}``
        """
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        from app.services.processing_boundary import permit_external_processing
        await permit_external_processing()
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools

        tool_calls_acc: dict[int, dict] = {}
        content_acc = ""
        client = _get_client()

        stream_headers = {"Authorization": f"Bearer {self._api_key}"}

        async with client.stream(
            "POST",
            f"{self._base_url}/chat/completions",
            headers=stream_headers,
            json=payload,
        ) as resp:
            from app.services.processing_boundary import check_delivery_fence
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                check_delivery_fence()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                obj = _json.loads(data)
                if not obj.get("choices"):
                    continue  # role/keepalive chunk with no completion data
                choice = obj["choices"][0]
                delta = choice.get("delta") or {}

                # Reasoning content (DeepSeek-R1, mimo, etc.) is intentionally
                # NOT yielded to the client: streaming it bleeds the model's
                # chain-of-thought into the user-visible reply. Swallowing it
                # here guarantees thinking text never leaks, whatever model runs.
                reasoning = delta.get("reasoning_content")
                if reasoning:
                    continue

                content = delta.get("content")
                if content:
                    content_acc += content
                    if tools:
                        yield {"text": content}
                    else:
                        yield content

                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = tool_calls_acc.setdefault(
                        idx,
                        {"id": "", "name": "", "arguments": ""},
                    )
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["arguments"] += fn["arguments"]
                    if tc.get("id"):
                        slot["id"] = tc["id"]

        if tools and tool_calls_acc:
            calls = [
                {"id": s["id"], "name": s["name"], "arguments": s["arguments"]}
                for s in tool_calls_acc.values()
            ]
            yield {"tool_calls": calls}
