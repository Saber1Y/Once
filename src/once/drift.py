"""Drift check: replay a company's distinctive cases before a new rule goes live.

Each case runs the full loop against a fresh copy of the company's systems (a new
``env`` from its integration), so a replay never touches live data. A candidate
rule that breaks any case is held instead of applied.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import neatlogs

from once.core import DriftCase, Guard
from once.loop import Loop
from once.memory import PolicyMemory


@neatlogs.span(kind="WORKFLOW", name="once_drift_check")
def run_drift(make_guard: Callable[..., Guard], memory: PolicyMemory, emit=None, workers: int = 3) -> dict:
    emit = emit or (lambda *a, **k: None)
    cases: list[DriftCase] = make_guard(PolicyMemory.ephemeral(memory.active())).cases
    emit("drift.started", total=len(cases), rules=[r.describe for r in memory.active()])

    def one(case: DriftCase) -> dict:
        guard = make_guard(PolicyMemory.ephemeral(memory.active()))  # fresh systems for every case
        run = Loop(guard).resolve(case.ticket)
        try:
            ok, detail = case.expect(run, guard)
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        result = {
            "id": case.id,
            "title": case.title,
            "why": case.why,
            "passed": ok,
            "detail": detail,
            "status": run.status,
            "trace_url": run.trace_url,
            "fixes": len(run.fixes),
        }
        emit("drift.case", result=result)
        return result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, cases))
    summary = {"passed": sum(r["passed"] for r in results), "total": len(results), "results": results}
    emit("drift.finished", **summary)
    return summary
