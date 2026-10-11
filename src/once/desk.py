"""The support desk: queue, worker thread, decisions and policy memory.

All loop work runs on one worker thread so tickets resolve in order and the
world stays consistent. Drift checks fan out to their own isolated worlds.
"""

from __future__ import annotations

import json
import math
import queue
import threading
import uuid
from datetime import UTC, datetime

from once.config import DATA_DIR, RUNS_DIR
from once.drift import run_drift
from once.events import EventBus
from once.loop import Loop, TicketRun
from once.policy import PolicyMemory, Rule
from once.tracing import flush, init_tracing, tracing_status
from once.world.kb import KnowledgeBase, SearchIndex
from once.world.store import World

TICKETS_FILE = DATA_DIR / "tickets.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Desk:
    def __init__(self) -> None:
        init_tracing()
        self.bus = EventBus()
        self.kb = KnowledgeBase()
        self.memory = PolicyMemory()
        self.jobs: queue.Queue = queue.Queue()
        self.lock = threading.RLock()
        self._reset_state()
        threading.Thread(target=self._worker, name="once-worker", daemon=True).start()

    # -- state ---------------------------------------------------------------

    def _reset_state(self) -> None:
        self.world = World.seeded()
        self.index = SearchIndex(self.kb)
        self.tickets: dict[str, dict] = {}
        for t in json.loads(TICKETS_FILE.read_text())["queue"]:
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
            return {
                "tickets": [self._ticket_view(tid) for tid in self.tickets],
                "decisions": list(self.decisions.values()),
                "policies": [r.__dict__ | {"describe": r.describe()} for r in self.memory.rules],
                "index": list(self.index.article_ids),
                "drift": self.drift,
                "stats": self.stats(),
                "tracing": tracing_status(),
                "busy": not self.jobs.empty() or self._busy,
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
        return {
            "resolved": sum(e["status"] == "resolved" for e in self.tickets.values()),
            "waiting": sum(e["status"] == "waiting_on_you" for e in self.tickets.values()),
            "fixed_alone": len(fixes),
            "fixed_verified": sum(f.get("verified", False) for f in fixes),
            "asked": len(self.decisions),
            "rules": len(self.memory.active()),
            "rule_reuses": sum(1 for r in runs if r.get("applied_rule")),
        }

    # -- worker --------------------------------------------------------------

    _busy = False

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
        loop = Loop(self.world, self.kb, self.index, memory or self.memory, emit=self.bus.emit)
        run = loop.resolve(entry["ticket"])
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
        choice = run.choice
        customer, order, finding = choice["customer"], choice["order"], choice["finding"]
        days_over = finding["data"]["days_over"]
        decision = {
            "id": f"Q-{uuid.uuid4().hex[:5]}",
            "ticket_id": ticket["id"],
            "status": "open",
            "created_at": _now(),
            "question": (
                f"{customer['name']} has been a customer for {customer['tenure_years']:g} years and is "
                f"{days_over} day{'s' if days_over != 1 else ''} past the "
                f"{finding['data']['window_days']}-day refund window for the {order['product']} "
                f"(${order['amount']:.2f}). Refund, store credit, or decline?"
            ),
            "facts": {
                "customer": customer["name"],
                "plan": customer["plan"],
                "tenure_years": customer["tenure_years"],
                "product": order["product"],
                "amount": order["amount"],
                "days_since_purchase": order["days_since_purchase"],
                "window_days": finding["data"]["window_days"],
                "days_over": days_over,
            },
            "why": finding["detail"],
            "evidence": choice["evidence"],
            "agent_question": choice["agent_question"],
            "options": [
                {"value": "refund", "label": "Refund in full"},
                {"value": "store_credit", "label": "Offer store credit"},
                {"value": "decline", "label": "Decline politely"},
            ],
            "suggested_scope": {
                "min_tenure_years": float(min(2, math.floor(customer["tenure_years"]))),
                "max_days_over": max(days_over, 7),
            },
            "trace_url": run.trace_url,
            "attempts": [],
        }
        self.decisions[decision["id"]] = decision
        self.bus.emit("decision.opened", decision=decision)

    def answer(
        self,
        decision_id: str,
        outcome: str,
        scope: str,
        min_tenure_years: float,
        max_days_over: int,
        decided_by: str = "Maya",
    ) -> None:
        self.jobs.put(("answer", (decision_id, outcome, scope, min_tenure_years, max_days_over, decided_by)))

    def _job_answer(
        self, decision_id: str, outcome: str, scope: str, min_tenure_years: float, max_days_over: int, decided_by: str
    ) -> None:
        decision = self.decisions[decision_id]
        rule = self.memory.new_rule(
            kind="refund_exception",
            min_tenure_years=float(min_tenure_years),
            max_days_over=int(max_days_over),
            outcome=outcome,
            question=decision["question"],
            source_ticket=decision["ticket_id"],
            decided_by=decided_by,
        )
        if scope == "once":
            rule.status = "active"
            decision.update(status="answered", answered_at=_now(), scope="once", rule=rule.__dict__)
            self.bus.emit("decision.answered", decision=decision)
            self._job_resolve(decision["ticket_id"], PolicyMemory.ephemeral(self.memory.active() + [rule]))
            return

        rule.status = "candidate"
        decision["status"] = "checking"
        self.bus.emit("decision.checking", decision=decision, rule=rule.__dict__ | {"describe": rule.describe()})
        candidate = PolicyMemory.ephemeral(self.memory.active() + [Rule(**{**rule.__dict__, "status": "active"})])
        drift = run_drift(candidate, emit=self.bus.emit)
        attempt = {"rule": rule.__dict__ | {"describe": rule.describe()}, "drift": drift, "at": _now()}
        decision["attempts"].append(attempt)
        self.drift = drift | {"at": _now(), "rule": rule.describe()}
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
        drift = run_drift(self.memory, emit=self.bus.emit)
        self.drift = drift | {"at": _now(), "rule": None}
