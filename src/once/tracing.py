"""neatlogs wiring.

``init_tracing()`` must run before the OpenAI client is constructed. When no
NEATLOGS_API_KEY is set, spans are still created locally but export is disabled,
and ``tracing_status()`` says so instead of pretending traces were sent.
"""

from __future__ import annotations

import os
import threading

import neatlogs

from once.config import settings

_lock = threading.Lock()
_state = {"initialized": False, "exporting": False}


def init_tracing() -> None:
    with _lock:
        if _state["initialized"]:
            return
        exporting = bool(settings.neatlogs_api_key)
        neatlogs.init(
            api_key=settings.neatlogs_api_key or "local-only",
            workflow_name="once-support-desk",
            tags=["neathack-2026", "once"],
            disable_export=not exporting,
        )
        _state.update(initialized=True, exporting=exporting)


def tracing_status() -> dict:
    return {
        "exporting": _state["exporting"],
        "dashboard": settings.neatlogs_app_url,
        "readback": bool(settings.neatlogs_token and settings.neatlogs_project_id),
    }


def current_trace_id() -> str | None:
    """The trace id of the active neatlogs span, read from its W3C traceparent."""
    carrier: dict[str, str] = {}
    if not neatlogs.inject_trace_context(carrier):
        return None
    parts = carrier.get("traceparent", "").split("-")
    return parts[1] if len(parts) == 4 else None


def trace_url(trace_id: str | None) -> str | None:
    if not trace_id or not _state["exporting"]:
        return None
    template = os.getenv("NEATLOGS_TRACE_URL")
    if template:
        return template.format(trace_id=trace_id, project_id=settings.neatlogs_project_id or "")
    return f"{settings.neatlogs_app_url}/traces?traceId={trace_id}"


def flush() -> None:
    if _state["initialized"]:
        neatlogs.flush(timeout_millis=10000)
