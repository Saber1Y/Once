"""The Once loop: act, check, fix what's mechanical, ask what's a choice, commit, verify.

It runs any company's ``Guard``. One ticket = one neatlogs WORKFLOW trace; each
agent attempt is an AGENT span inside it, so the failed attempt and the fixed one
sit side by side in the trace.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import neatlogs

from once import checks
from once.core import CheckContext, Finding, Guard, Session
from once.tracing import current_trace_id, trace_url

MAX_ATTEMPTS = 4
MAX_WRITE_RETRIES = 2

Emit = Callable[..., Any]


@dataclass
class TicketRun:
    ticket_id: str
    company: str
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
    def __init__(self, guard: Guard, emit: Emit | None = None) -> None:
        self.guard = guard
        self.emit = emit or (lambda *a, **k: None)

    @neatlogs.span(kind="WORKFLOW", name="once_resolve_ticket")
    def resolve(self, ticket: dict) -> TicketRun:
        run = TicketRun(ticket_id=ticket["id"], company=self.guard.company)
        run.trace_id = current_trace_id()
        run.trace_url = trace_url(run.trace_id)
        neatlogs.log("{company} ticket {ticket_id}", company=self.guard.company, ticket_id=ticket["id"])
        self.emit("ticket.started", ticket_id=ticket["id"], trace_id=run.trace_id, trace_url=run.trace_url)
        try:
            self._resolve(ticket, run)
        except Exception as exc:  # surfaced in the console, never hidden
            run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"
            self.emit("ticket.failed", ticket_id=ticket["id"], error=run.error)
        return run

    def _resolve(self, ticket: dict, run: TicketRun) -> None:
        guidance: list[str] = []
        for number in range(1, MAX_ATTEMPTS + 1):
            self.emit("attempt.started", ticket_id=ticket["id"], attempt=number)
            session = self.guard.attempt(ticket, number, guidance)
            ctx = CheckContext(ticket, session, self.guard.memory, self.guard)
            everything = checks.before_commit(ctx)
            for f in everything:
                if f.data.get("rule_id"):
                    run.applied_rule = f.data["rule_id"]
            findings = [f for f in everything if f.route != "info"]  # "info" notes never block a reply
            record = self._record(run, session, findings)
            record["notes"] = [f.to_dict() for f in everything if f.route == "info"]
            self.emit("attempt.checked", ticket_id=ticket["id"], attempt=record)

            choices = [f for f in findings if f.route == "choice"]
            if choices:
                # Repair causes now so the resumed ticket doesn't hit them again.
                self._fix_before_commit(ticket, run, [f for f in findings if f.code == "outdated_source"], number)
                run.status = "waiting_on_you"
                run.choice = {
                    "finding": choices[0].to_dict(),
                    "evidence": [s.to_dict() for s in session.ledger.steps if s.id in choices[0].evidence],
                    "agent_question": session.decision_request,
                }
                self.emit("ticket.waiting", ticket_id=ticket["id"], choice=run.choice)
                return

            mechanical = [f for f in findings if f.route == "mechanical"]
            if mechanical:
                guidance = guidance + self._fix_before_commit(ticket, run, mechanical, number)
                continue

            if number > 1:
                self._verified(ticket, run, number, "Re-run passed every check that failed before.")
            commits = self._commit(session)
            run.commits += commits
            post = checks.after_commit(ctx, commits)
            if post:
                record["post_commit"] = [f.to_dict() for f in post]
                self.emit(
                    "attempt.post_checked", ticket_id=ticket["id"], attempt=number, findings=record["post_commit"]
                )
                facts = self._fix_after_commit(ticket, run, post, session)
                session.draft = self._redraft(ticket, session.draft, facts)
                self._verified(
                    ticket,
                    run,
                    number,
                    "Writes read back from the system of record; reply rewritten from verified facts.",
                )
            elif checks.needs_judge(session, findings):
                judged = checks.judge(session)
                if judged:
                    record["judge"] = [f.to_dict() for f in judged]
                    self._log_fix(ticket, run, number, judged[0], "Rewrote the reply without the unsupported claim.")
                    session.draft = self._redraft(
                        ticket, session.draft, [f"Remove or correct: {f.detail}" for f in judged]
                    )
            run.reply = session.draft
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

    def _record(self, run: TicketRun, session: Session, findings: list[Finding]) -> dict:
        record = {
            "number": session.number,
            "steps": [s.to_dict() for s in session.ledger.steps],
            "staged": session.staged,
            "draft": session.draft,
            "decision_request": session.decision_request,
            "findings": [f.to_dict() for f in findings],
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
        guidance = []
        for f in findings:
            if f.code == "outdated_source" and self.guard.sources and f.data.get("current"):
                self.guard.sources.repair(f.data["stale"], f.data["current"])
                self._log_fix(
                    ticket,
                    run,
                    attempt,
                    f,
                    f"Repaired the search index: replaced {f.data['stale']} with {f.data['current']}.",
                )
            else:
                guidance.append(f.correction or f"Fix this problem: {f.detail}")
                self._log_fix(ticket, run, attempt, f, "Re-running the agent with a precise correction.")
        return guidance

    @neatlogs.span(kind="CHAIN", name="commit_actions")
    def _commit(self, session: Session) -> list[dict]:
        commits = []
        for action in session.staged:
            spec = self.guard.actions[action["type"]]
            params = {k: v for k, v in action.items() if k != "type"}
            result = session.ledger.record(
                "commit", f"commit_{spec.name}", params, lambda s=spec, p=params: s.commit(**p)
            )
            step = session.ledger.steps[-1]
            commits.append({"action": action, "result": result, "ok": step.ok, "step_id": step.id})
        return commits

    @neatlogs.span(kind="CHAIN", name="fix_after_commit")
    def _fix_after_commit(self, ticket: dict, run: TicketRun, findings: list[Finding], session: Session) -> list[str]:
        facts = []
        for f in findings:
            action = f.data["action"]
            label = action["type"].replace("_", " ")
            if f.code == "side_effect_missing":
                landed, tries, detail = self._retry_write(session, action)
                if landed:
                    facts.append(f"The {label} is confirmed applied ({detail}). It is safe to say it is done.")
                    self._log_fix(
                        ticket,
                        run,
                        session.number,
                        f,
                        f"Retried the write and read it back: applied after {tries} "
                        f"retr{'y' if tries == 1 else 'ies'}.",
                    )
                else:
                    facts.append(
                        f"The {label} failed after retries ({detail}). Do NOT say it is done: tell the customer it "
                        "is in progress and that we will email a confirmation."
                    )
                    self._log_fix(ticket, run, session.number, f, "Retries failed: reply rewritten to be honest.")
            elif f.code == "commit_failed":
                facts.append(f"The {label} did not go through: {f.detail}. Do not say it was done.")
                self._log_fix(ticket, run, session.number, f, "Reply rewritten: the write did not go through.")
        return facts

    def _retry_write(self, session: Session, action: dict) -> tuple[bool, int, str]:
        spec = self.guard.actions[action["type"]]
        params = {k: v for k, v in action.items() if k != "type"}
        detail = ""
        for tries in range(1, MAX_WRITE_RETRIES + 1):
            result = session.ledger.record("commit", f"retry_{spec.name}", params, lambda: spec.commit(**params))
            verdict = session.ledger.record(
                "verify", f"read_back_{spec.name}", params, lambda r=result: list(spec.verify(action, r))
            )
            landed, detail = (verdict[0], verdict[1]) if isinstance(verdict, list) else (False, str(verdict))
            if landed:
                return True, tries, detail
        return False, MAX_WRITE_RETRIES, detail

    @neatlogs.span(kind="CHAIN", name="redraft_reply")
    def _redraft(self, ticket: dict, draft: str, facts: list[str]) -> str:
        from once.llm import chat

        lines = "\n".join(f"- {f}" for f in facts)
        message = chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You rewrite customer-support replies so every statement is true. Keep the tone, signature "
                        "and length, change only what the verified facts contradict. Return only the reply text."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Ticket: {ticket['body']}\n\nDraft reply:\n{draft}\n\n"
                        f"Verified facts (override the draft):\n{lines}"
                    ),
                },
            ]
        )
        return (message.content or "").strip()
