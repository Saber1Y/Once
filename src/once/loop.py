"""The Once loop: act, check, classify, route, fix, verify.

One ticket = one neatlogs WORKFLOW trace. Each agent attempt is an AGENT span
inside it, so the failed attempt and the fixed one sit side by side in the trace.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import neatlogs

from once.agent import Attempt, SupportAgent
from once.checker import Checker, Finding
from once.policy import PolicyMemory
from once.tracing import current_trace_id, trace_url
from once.world.kb import KnowledgeBase, SearchIndex
from once.world.store import World

MAX_ATTEMPTS = 4
MAX_SIDE_EFFECT_RETRIES = 2

Emit = Callable[..., Any]


@dataclass
class TicketRun:
    ticket_id: str
    status: str = "running"  # running | resolved | waiting_on_you | failed
    trace_id: str | None = None
    trace_url: str | None = None
    attempts: list[dict] = field(default_factory=list)
    fixes: list[dict] = field(default_factory=list)
    commits: list[dict] = field(default_factory=list)
    reply: str = ""
    choice: dict | None = None
    applied_rule: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class Loop:
    def __init__(
        self, world: World, kb: KnowledgeBase, index: SearchIndex, memory: PolicyMemory, emit: Emit | None = None
    ) -> None:
        self.world = world
        self.kb = kb
        self.index = index
        self.memory = memory
        self.emit = emit or (lambda *a, **k: None)
        self.agent = SupportAgent(world, index, kb, memory)
        self.checker = Checker(world, kb, memory)

    @neatlogs.span(kind="WORKFLOW", name="resolve_ticket")
    def resolve(self, ticket: dict) -> TicketRun:
        run = TicketRun(ticket_id=ticket["id"])
        run.trace_id = current_trace_id()
        run.trace_url = trace_url(run.trace_id)
        neatlogs.log("ticket {ticket_id}", ticket_id=ticket["id"])
        self.emit("ticket.started", ticket_id=ticket["id"], trace_id=run.trace_id, trace_url=run.trace_url)
        try:
            self._resolve(ticket, run)
        except Exception as exc:  # surface, never hide: the console shows the error
            run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"
            self.emit("ticket.failed", ticket_id=ticket["id"], error=run.error)
        return run

    def _resolve(self, ticket: dict, run: TicketRun) -> None:
        corrections: list[str] = []
        for number in range(1, MAX_ATTEMPTS + 1):
            self.emit("attempt.started", ticket_id=ticket["id"], attempt=number)
            attempt = self.agent.run(ticket, number, corrections)
            findings, expectations = self.checker.before_commit(ticket, attempt)
            for exp in expectations.values():
                if exp.rule_id:
                    run.applied_rule = exp.rule_id
            record = self._record(run, attempt, findings, phase="before_commit")
            self.emit("attempt.checked", ticket_id=ticket["id"], attempt=record)

            choices = [f for f in findings if f.route == "choice"]
            if choices:
                stale = [f for f in findings if f.code == "stale_source"]
                if stale:  # repair the cause now so the resumed ticket doesn't hit it again
                    self._fix_before_commit(ticket, run, stale, number)
                run.status = "waiting_on_you"
                run.choice = {
                    "finding": choices[0].to_dict(),
                    "evidence": [s.to_dict() for s in attempt.ledger.steps if s.id in choices[0].evidence],
                    "customer": attempt.customer(),
                    "order": self.world.order(choices[0].data["order_id"]),
                    "agent_question": attempt.decision_request,
                }
                self.emit("ticket.waiting", ticket_id=ticket["id"], choice=run.choice)
                return

            mechanical = [f for f in findings if f.route == "mechanical"]
            if mechanical:
                corrections = corrections + self._fix_before_commit(ticket, run, mechanical, number)
                continue

            if number > 1:
                self._verified(ticket, run, number, "Re-run passed every check that failed before.")
            commits = self._commit(attempt)
            run.commits += commits
            post = self.checker.after_commit(attempt, commits)
            if post:
                record["post_commit"] = [f.to_dict() for f in post]
                self.emit(
                    "attempt.post_checked", ticket_id=ticket["id"], attempt=number, findings=record["post_commit"]
                )
                facts = self._fix_after_commit(ticket, run, post, attempt)
                attempt.draft = self.agent.redraft(ticket, attempt.draft, facts)
                again, _ = self.checker.before_commit(ticket, attempt)
                again = [f for f in again if f.code in ("forbidden_promise", "unsupported_amount", "wrong_window")]
                if again:
                    attempt.draft = self.agent.redraft(ticket, attempt.draft, facts + [f.detail for f in again])
                self._verified(ticket, run, number, "Reply rewritten from verified facts; side effects read back.")
            elif self.checker.needs_judge(attempt, findings):
                judged = self.checker.judge(attempt)
                if judged:
                    record["judge"] = [f.to_dict() for f in judged]
                    self._log_fix(ticket, run, number, judged[0], "Rewrote the reply without the unsupported claim.")
                    attempt.draft = self.agent.redraft(
                        ticket, attempt.draft, [f"Remove or correct: {f.detail}" for f in judged]
                    )
            run.reply = attempt.draft
            run.status = "resolved"
            self.emit(
                "ticket.resolved",
                ticket_id=ticket["id"],
                reply=run.reply,
                commits=run.commits,
                applied_rule=run.applied_rule,
                attempts=len(run.attempts),
            )
            return
        run.status = "failed"
        run.error = f"Still failing checks after {MAX_ATTEMPTS} attempts."
        self.emit("ticket.failed", ticket_id=ticket["id"], error=run.error)

    # -- helpers ---------------------------------------------------------------

    def _record(self, run: TicketRun, attempt: Attempt, findings: list[Finding], phase: str) -> dict:
        record = {
            "number": attempt.number,
            "steps": [s.to_dict() for s in attempt.ledger.steps],
            "staged": attempt.staged,
            "draft": attempt.draft,
            "decision_request": attempt.decision_request,
            "findings": [f.to_dict() for f in findings],
            "phase": phase,
        }
        run.attempts.append(record)
        return record

    def _log_fix(self, ticket: dict, run: TicketRun, attempt: int, finding: Finding, action: str) -> None:
        fix = {
            "attempt": attempt,
            "code": finding.code,
            "category": finding.category,
            "title": finding.title,
            "action": action,
            "verified": False,
        }
        run.fixes.append(fix)
        self.emit("fix.applied", ticket_id=ticket["id"], fix=fix)

    def _verified(self, ticket: dict, run: TicketRun, attempt: int, how: str) -> None:
        for fix in run.fixes:
            if not fix["verified"]:
                fix["verified"] = True
                fix["verified_by"] = how
        self.emit("fix.verified", ticket_id=ticket["id"], attempt=attempt, how=how)

    @neatlogs.span(kind="CHAIN", name="fix_before_commit")
    def _fix_before_commit(self, ticket: dict, run: TicketRun, findings: list[Finding], attempt: int) -> list[str]:
        corrections = []
        for f in findings:
            if f.code == "stale_source":
                self.index.replace(f.data["stale"], f.data["current"])
                self._log_fix(
                    ticket,
                    run,
                    attempt,
                    f,
                    f"Repaired the search index: replaced {f.data['stale']} with {f.data['current']}.",
                )
            elif f.code == "wrong_outcome":
                corrections.append(
                    f"For order {f.data['order_id']} the correct outcome is "
                    f"{f.data['expected'].replace('_', ' ')}. {f.detail.split('. ', 1)[-1]} "
                    "Propose exactly that, and explain it to the customer."
                )
                self._log_fix(ticket, run, attempt, f, "Re-running with the policy-correct outcome.")
            elif f.code == "wrong_amount":
                corrections.append(f"Refund the full order total of ${f.data['expected_amount']:.2f}.")
                self._log_fix(ticket, run, attempt, f, "Re-running with the correct amount.")
            elif f.code == "forbidden_promise":
                corrections.append(
                    "The customer is on the Starter plan: do not promise, offer or schedule a phone call. "
                    "Acknowledge the urgency, explain the 24-hour email support window, and ask for "
                    "troubleshooting details."
                )
                self._log_fix(ticket, run, attempt, f, "Re-running without the phone-call promise.")
            elif f.code == "wrong_window":
                corrections.append(f"The current refund window is {f.data['window']} days.")
                self._log_fix(ticket, run, attempt, f, "Re-running with the current refund window.")
            elif f.code == "unsupported_amount":
                corrections.append(f"Do not mention ${f.data['amount']:.2f}; only state amounts the tools returned.")
                self._log_fix(ticket, run, attempt, f, "Re-running without the unsupported amount.")
            elif f.code == "needless_escalation":
                corrections.append(f"Do not call request_decision. {f.detail.split('but ', 1)[-1]}")
                self._log_fix(ticket, run, attempt, f, "Re-running without escalating.")
            else:
                corrections.append(f"Fix this problem: {f.detail}")
                self._log_fix(ticket, run, attempt, f, "Re-running with the review note.")
        return corrections

    @neatlogs.span(kind="CHAIN", name="commit_actions")
    def _commit(self, attempt: Attempt) -> list[dict]:
        commits = []
        for action in attempt.staged:
            if action["type"] == "address_change":
                fn = lambda a=action: self.world.request_address_change(a["order_id"], a["new_address"])  # noqa: E731
            else:
                fn = lambda a=action: self.world.refund(a["order_id"], a["amount"], a["reason"], a["type"])  # noqa: E731
            result = attempt.ledger.record("commit", f"commit_{action['type']}", action, lambda f=fn: _commit_span(f))
            step = attempt.ledger.last()
            commits.append({"action": action, "result": result, "ok": step.ok, "step_id": step.id})
        return commits

    @neatlogs.span(kind="CHAIN", name="fix_after_commit")
    def _fix_after_commit(self, ticket: dict, run: TicketRun, findings: list[Finding], attempt: Attempt) -> list[str]:
        facts = []
        for f in findings:
            if f.code == "side_effect_missing":
                landed, job, tries = self._retry_address(attempt, f.data["order_id"], f.data["new_address"])
                order_id, address = f.data["order_id"], f.data["new_address"]
                if landed:
                    facts.append(
                        f"The address change for {order_id} to {address} is confirmed applied "
                        f"(job {job.get('id')} done, order read back). It is safe to say it's updated."
                    )
                    self._log_fix(
                        ticket,
                        run,
                        attempt.number,
                        f,
                        "Retried the write and read the order back: address applied "
                        f"after {tries} retr{'y' if tries == 1 else 'ies'}.",
                    )
                else:
                    facts.append(
                        f"The address change for {order_id} failed after retries. Do NOT say it is "
                        "updated: tell the customer it is in progress and we will email a confirmation."
                    )
                    self._log_fix(
                        ticket,
                        run,
                        attempt.number,
                        f,
                        "Retries failed: reply rewritten to be honest, follow-up flagged.",
                    )
            elif f.code == "commit_failed":
                facts.append(
                    f"The refund for {f.data['order_id']} did not go through: {f.detail}. Do not say it was processed."
                )
                self._log_fix(ticket, run, attempt.number, f, "Reply rewritten: refund did not go through.")
        return facts

    def _retry_address(self, attempt: Attempt, order_id: str, address: str) -> tuple[bool, dict, int]:
        job: dict = {}
        for tries in range(1, MAX_SIDE_EFFECT_RETRIES + 1):
            result = attempt.ledger.record(
                "commit",
                "retry_address_change",
                {"order_id": order_id, "new_address": address},
                lambda: _commit_span(lambda: self.world.request_address_change(order_id, address)),
            )
            order = attempt.ledger.record(
                "verify",
                "read_back_order",
                {"order_id": order_id},
                lambda: _verify_span(lambda: self.world.order(order_id)),
            )
            if isinstance(result, dict) and result.get("job_id"):
                job = self.world.address_job(result["job_id"])
            if order.get("shipping_address", "").strip().lower() == address.strip().lower():
                return True, job, tries
        return False, job, MAX_SIDE_EFFECT_RETRIES


@neatlogs.span(kind="TOOL", name="commit_action")
def _commit_span(fn):
    return fn()


@neatlogs.span(kind="TOOL", name="read_back")
def _verify_span(fn):
    return fn()
