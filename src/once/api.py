"""HTTP API for the Once console."""

from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from once.config import ROOT, settings
from once.desk import Desk

app = FastAPI(title="Once")
desk = Desk()


class Answer(BaseModel):
    outcome: Literal["refund", "store_credit", "decline"]
    scope: Literal["once", "always"]
    min_tenure_years: float = Field(ge=0, le=50)
    max_days_over: int = Field(ge=1, le=365)


class NewTicket(BaseModel):
    sender: str = Field(min_length=3, max_length=200)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)


@app.get("/api/state")
def state() -> dict:
    return desk.snapshot() | {"llm_ready": settings.llm_ready, "today": settings.today.isoformat()}


@app.get("/api/tickets/{ticket_id}")
def ticket(ticket_id: str) -> dict:
    entry = desk.tickets.get(ticket_id)
    if not entry:
        raise HTTPException(404, "No such ticket")
    return {"id": ticket_id, **entry}


def _require_llm() -> None:
    if not settings.llm_ready:
        raise HTTPException(409, "LLM is not configured: set LLM_API_KEY and ONCE_MODEL in .env")


@app.post("/api/run")
def run_queue() -> dict:
    _require_llm()
    desk.run_queue()
    return {"ok": True}


@app.post("/api/tickets/{ticket_id}/run")
def run_ticket(ticket_id: str) -> dict:
    _require_llm()
    if ticket_id not in desk.tickets:
        raise HTTPException(404, "No such ticket")
    desk.run_ticket(ticket_id)
    return {"ok": True}


@app.post("/api/tickets")
def add_ticket(body: NewTicket) -> dict:
    _require_llm()
    return {"id": desk.add_ticket(body.sender, body.subject, body.body)}


@app.post("/api/decisions/{decision_id}")
def answer(decision_id: str, body: Answer) -> dict:
    decision = desk.decisions.get(decision_id)
    if not decision:
        raise HTTPException(404, "No such decision")
    if decision["status"] not in ("open", "held"):
        raise HTTPException(409, f"Decision is {decision['status']}")
    decision["status"] = "checking" if body.scope == "always" else "answering"
    desk.answer(decision_id, body.outcome, body.scope, body.min_tenure_years, body.max_days_over)
    return {"ok": True}


@app.post("/api/drift")
def drift() -> dict:
    _require_llm()
    desk.check_drift()
    return {"ok": True}


@app.post("/api/reset")
def reset() -> dict:
    desk.reset()
    return {"ok": True}


@app.get("/api/events")
async def events(request: Request):
    async def stream():
        queue = desk.bus.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": "message", "data": json.dumps(event, default=str)}
        finally:
            desk.bus.unsubscribe(queue)

    return EventSourceResponse(stream())


@app.get("/api/history")
def history() -> list[dict]:
    return desk.bus.history[-500:]


_dist = ROOT / "web" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        target = _dist / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(_dist / "index.html")
