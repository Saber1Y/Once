"""OpenAI-compatible client for the neatHack LiteLLM proxy, wrapped by neatlogs."""

from __future__ import annotations

import threading
from typing import Any

import neatlogs

from once.config import settings
from once.tracing import init_tracing

_client = None
_lock = threading.Lock()


class LLMNotConfigured(RuntimeError):
    pass


def client():
    global _client
    with _lock:
        if _client is None:
            if not settings.llm_ready:
                raise LLMNotConfigured(
                    "Set LLM_API_KEY and ONCE_MODEL (and LLM_BASE_URL for the LiteLLM proxy) in .env"
                )
            init_tracing()
            from openai import OpenAI  # imported after neatlogs.init, as the SDK requires

            _client = neatlogs.wrap(OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url, max_retries=3))
        return _client


def chat(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict] | None = None,
    model: str | None = None,
    json_mode: bool = False,
):
    kwargs: dict[str, Any] = {"model": model or settings.model, "messages": messages, "temperature": 0.2}
    if tools:
        kwargs["tools"] = tools
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = client().chat.completions.create(**kwargs)
    return response.choices[0].message
