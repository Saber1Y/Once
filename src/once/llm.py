"""OpenAI-compatible model client (LiteLLM proxy, Gemini, ...), wrapped by neatlogs.

Free tiers have tight per-minute quotas, so calls go through a per-model rate
limiter (``LLM_RPM``) and a 429 waits out the provider's stated retry delay
before trying again. Waits are logged; a call that still fails raises.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import deque
from typing import Any

import neatlogs

from once.config import settings
from once.tracing import init_tracing

log = logging.getLogger("once.llm")

_client = None
_lock = threading.Lock()
MAX_RATE_RETRIES = 4


class LLMNotConfigured(RuntimeError):
    pass


class _RateLimiter:
    """Sliding-window limiter: at most ``rpm`` calls per model per 60 seconds."""

    def __init__(self, rpm: int) -> None:
        self.rpm = rpm
        self.calls: dict[str, deque[float]] = {}
        self.lock = threading.Lock()

    def wait(self, model: str) -> None:
        if self.rpm <= 0:
            return
        while True:
            with self.lock:
                window = self.calls.setdefault(model, deque())
                now = time.monotonic()
                while window and now - window[0] >= 60:
                    window.popleft()
                if len(window) < self.rpm:
                    window.append(now)
                    return
                delay = 60 - (now - window[0]) + 0.05
            log.info("rate limit: waiting %.1fs for %s", delay, model)
            time.sleep(delay)


_limiter = _RateLimiter(int(os.getenv("LLM_RPM", "0") or 0))


def client():
    global _client
    with _lock:
        if _client is None:
            if not settings.llm_ready:
                raise LLMNotConfigured("Set LLM_API_KEY, LLM_BASE_URL and ONCE_MODEL in .env")
            init_tracing()
            from openai import OpenAI  # imported after neatlogs.init, as the SDK requires

            _client = neatlogs.wrap(OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url, max_retries=2))
        return _client


def _retry_delay(exc: Exception) -> float | None:
    match = re.search(r"retry in ([\d.]+)s|'retryDelay': '(\d+)s'", str(exc))
    if not match:
        return None
    return float(match.group(1) or match.group(2))


def chat(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict] | None = None,
    model: str | None = None,
    json_mode: bool = False,
):
    from openai import RateLimitError

    model = model or settings.model
    kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0.2}
    if tools:
        kwargs["tools"] = tools
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    for attempt in range(MAX_RATE_RETRIES + 1):
        _limiter.wait(model)
        try:
            response = client().chat.completions.create(**kwargs)
            return response.choices[0].message
        except RateLimitError as exc:
            delay = _retry_delay(exc)
            if delay is None or attempt == MAX_RATE_RETRIES or "perday" in str(exc).lower().replace(" ", ""):
                raise
            log.warning("429 from %s: waiting %.0fs as the provider asked", model, delay)
            time.sleep(delay + 1)
    raise RuntimeError("unreachable")
