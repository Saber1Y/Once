"""The desk: one connected company, its ticket queue, decisions and policy memory.

All loop work runs on one worker thread so tickets resolve in order and the
company's systems stay consistent. Drift checks fan out to fresh copies.
"""

from __future__ import annotations

import json
import queue
import threading
import uuid
from datetime import UTC, datetime

from once import integrations
from once.config import DATA_DIR, RUNS_DIR
from once.drift import run_drift
from once.events import EventBus
from once.loop import Loop, TicketRun
from once.memory import PolicyMemory
from once.tracing import flush, init_tracing, tracing_status


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Desk:
    def __init__(self, spec: str | None = None) -> None:
        init_tracing()
        self.integration = integrations.load(spec)
        self.files = integrations.source_files(self.integration)
        self.bus = EventBus()
        company = self.integration.CONFIG["company"]
        self.memory = PolicyMemory(DATA_DIR / "tenants" / company.lower() / "policies.json")
        self.jobs: queue.Queue = queue.Queue()
        self.lock = threading.RLock()
        self._busy = False
        self._reset_state()
        threading.Thread(target=self._worker, name="once-worker", daemon=True).start()

    # -- state ---------------------------------------------------------------

    def _reset_state(self) -> None:
        self.guard = self.integration.create_guard(self.memory)
        self.tickets: dict[str, dict] = {}
        for t in self.integration.demo_tickets():
            self.tickets[t["id"]] = {"ticket": t, "status": "queued", "runs": [], "source": "seed"}
        self.decisions: dict[str, dict] = {}
        self.drift: dict | None = None

    def reset(self) -> None:
        with self.lock:
            self.memory.clear()
            self._reset_state()
            self.bus.clear()
        self.bus.emit("desk.reset")

    def snapshot(self) -> dict:
        with self.lock:
            index = getattr(self.guard.env, "index", None)
            return {
                "company": self.guard.company,
                "tickets": [self._ticket_view(tid) for tid in self.tickets],
                "decisions": list(self.decisions.values()),
                "policies": [r.__dict__ | {"describe": r.describe} for r in self.memory.rules],
                "index": list(index.article_ids) if index else [],
                "drift": self.drift,
                "stats": self.stats(),
                "tracing": tracing_status(),
                "busy": not self.jobs.empty() or self._busy,
            }

    def integration_view(self) -> dict:
        return {
            **self.guard.describe(),
            "config": self.integration.CONFIG,
            "files": self.files,
            "module": self.integration.__name__,
        }

    def _ticket_view(self, ticket_id: str) -> dict:
        entry = self.tickets[ticket_id]
        latest = entry["runs"][-1] if entry["runs"] else None
        return {
            "id": ticket_id,
            **entry["ticket"],
            "status": entry["status"],
            "source": entry["source"],
            "latest": latest,
            "runs": len(entry["runs"]),
        }

    def stats(self) -> dict:
        runs = [r for e in self.tickets.values() for r in e["runs"]]
        fixes = [f for r in runs for f in r["fixes"]]
        sources = {rule.id: rule.source_ticket for rule in self.memory.rules}
        return {
            "resolved": sum(e["status"] == "resolved" for e in self.tickets.values()),
            "waiting": sum(e["status"] == "waiting_on_you" for e in self.tickets.values()),
            "fixed_alone": len(fixes),
            "fixed_verified": sum(f.get("verified", False) for f in fixes),
            "asked": len(self.decisions),
            "rules": len(self.memory.active()),
            "rule_reuses": sum(
                1 for r in runs if sources.get(r.get("applied_rule") or "", r["ticket_id"]) != r["ticket_id"]
            ),
        }

    # -- worker --------------------------------------------------------------

    def _worker(self) -> None:
        while True:
            job, args = self.jobs.get()
            self._busy = True
            try:
                getattr(self, f"_job_{job}")(*args)
            except Exception as exc:
                self.bus.emit("desk.error", job=job, error=f"{type(exc).__name__}: {exc}")
            finally:
                self._busy = False
                flush()

    def run_queue(self) -> None:
        for tid, entry in self.tickets.items():
            if entry["status"] in ("queued", "failed"):
                entry["status"] = "pending"
                self.jobs.put(("resolve", (tid, None)))

    def run_ticket(self, ticket_id: str) -> None:
        self.tickets[ticket_id]["status"] = "pending"
        self.jobs.put(("resolve", (ticket_id, None)))

    def add_ticket(self, sender: str, subject: str, body: str) -> str:
        tid = f"T-{uuid.uuid4().hex[:4].upper()}"
        with self.lock:
            self.tickets[tid] = {
                "ticket": {"id": tid, "from": sender, "subject": subject, "body": body},
                "status": "pending",
                "runs": [],
                "source": "custom",
            }
        self.bus.emit("ticket.added", ticket_id=tid)
        self.jobs.put(("resolve", (tid, None)))
        return tid

    def _job_resolve(self, ticket_id: str, memory: PolicyMemory | None) -> None:
        entry = self.tickets[ticket_id]
        entry["status"] = "running"
        guard = self.guard
        if memory is not None:  # a one-off answer: same systems, extra rule for this ticket only
            original, guard.memory = guard.memory, memory
        try:
            run = Loop(guard, emit=self.bus.emit).resolve(entry["ticket"])
        finally:
            if memory is not None:
                guard.memory = original
        self._save_run(run)
        with self.lock:
            entry["runs"].append(run.to_dict())
            entry["status"] = run.status
            if run.status == "waiting_on_you":
                self._open_decision(entry["ticket"], run)
        self.bus.emit("desk.updated")

    def _save_run(self, run: TicketRun) -> None:
        RUNS_DIR.mkdir(exist_ok=True)
        path = RUNS_DIR / f"{run.ticket_id}-{datetime.now().strftime('%H%M%S')}.json"
        path.write_text(json.dumps(run.to_dict(), indent=2, default=str))

    # -- decisions -----------------------------------------------------------

    def _open_decision(self, ticket: dict, run: TicketRun) -> None:
        finding = run.choice["finding"]
        choice = finding["data"]["choice"]
        decision = {
            "id": f"Q-{uuid.uuid4().hex[:5]}",
            "ticket_id": ticket["id"],
            "status": "open",
            "created_at": _now(),
            "domain": choice["domain"],
            "question": choice["question"],
            "facts": choice["facts"],
            "highlights": [list(h) for h in choice["highlights"]],
            "options": choice["options"],
            "conditions": choice["conditions"],
            "why": finding["detail"],
            "evidence": run.choice["evidence"],
            "agent_question": run.choice["agent_question"],
            "decided_by": self.guard.config.get("decisions", {}).get("decided_by", "Support lead"),
            "trace_url": run.trace_url,
            "attempts": [],
        }
        self.decisions[decision["id"]] = decision
        self.bus.emit("decision.opened", decision=decision)

    def answer(self, decision_id: str, outcome: str, scope: str, values: dict[str, float]) -> None:
        self.jobs.put(("answer", (decision_id, outcome, scope, values)))

    def _job_answer(self, decision_id: str, outcome: str, scope: str, values: dict[str, float]) -> None:
        decision = self.decisions[decision_id]
        labels = {o["value"]: o["label"] for o in decision["options"]}
        conditions = [
            {**c, "value": type(c["value"])(values.get(c["field"], c["value"]))} for c in decision["conditions"]
        ]
        rule = self.memory.new_rule(
            domain=decision["domain"],
            conditions=conditions,
            outcome=outcome,
            outcome_label=labels[outcome].replace(" in full", "").replace(" politely", ""),
            question=decision["question"],
            source_ticket=decision["ticket_id"],
            decided_by=decision["decided_by"],
        )
        if scope == "once":
            decision.update(status="answered", answered_at=_now(), scope="once", rule=rule.__dict__)
            self.bus.emit("decision.answered", decision=decision)
            self._job_resolve(decision["ticket_id"], PolicyMemory.ephemeral(self.memory.active() + [rule]))
            return

        rule.status = "candidate"
        decision["status"] = "checking"
        self.bus.emit("decision.checking", decision=decision, rule=rule.__dict__ | {"describe": rule.describe})
        candidate = PolicyMemory.ephemeral(self.memory.active() + [rule])
        candidate.rules[-1].status = "active"
        drift = run_drift(self.integration.create_guard, candidate, emit=self.bus.emit)
        decision["attempts"].append({"rule": rule.__dict__ | {"describe": rule.describe}, "drift": drift, "at": _now()})
        self.drift = drift | {"at": _now(), "rule": rule.describe}
        if drift["passed"] == drift["total"]:
            rule.status = "active"
            self.memory.add(rule)
            decision.update(status="answered", answered_at=_now(), scope="always", rule=rule.__dict__)
            self.bus.emit("decision.answered", decision=decision)
            self._job_resolve(decision["ticket_id"], None)
        else:
            rule.status = "held"
            failed = [r for r in drift["results"] if not r["passed"]]
            rule.held_reason = "; ".join(f"{r['id']} {r['title']}: {r['detail']}" for r in failed)
            self.memory.add(rule)
            decision["status"] = "held"
            self.bus.emit("decision.held", decision=decision, failed=failed)

    def check_drift(self) -> None:
        self.jobs.put(("drift", ()))

    def _job_drift(self) -> None:
        drift = run_drift(self.integration.create_guard, self.memory, emit=self.bus.emit)
        self.drift = drift | {"at": _now(), "rule": None}
