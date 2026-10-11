"""The Once SDK: what a company uses to put its agent behind Once.

A company integrates by building a ``Guard``:

* ``@guard.agent``   their existing agent, which calls tools through a ``Session``
* ``@guard.action``  each write the agent may propose, with a read-back ``verify``
* ``@guard.check``   their business checks (policy, plan limits, ...)
* ``guard.sources``  their help center, so Once can tell current articles from outdated ones
* ``guard.case``     distinctive cases that encode trade-offs they chose on purpose

Once then runs every ticket through the loop: act, check, fix what's mechanical,
ask what's a choice, commit, read back, remember.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

import neatlogs

from once.ledger import Ledger
from once.memory import PolicyMemory


@dataclass
class Finding:
    code: str
    category: str  # neatlogs taxonomy: "context" | "decision" | "execution" | "trajectory"
    route: str  # "mechanical" (Once fixes it) | "choice" (Once asks a person)
    title: str
    detail: str
    evidence: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    correction: str | None = None  # instruction for the agent's next attempt
    tier: str = "deterministic"
    source: str = "once"  # "once" for built-in checks, otherwise the integrator's check name

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Choice:
    """A business decision a check hands to a person, with the facts a rule can match on."""

    domain: str
    question: str
    facts: dict[str, Any]
    options: list[dict[str, str]]  # [{"value": "refund", "label": "Refund in full"}]
    conditions: list[dict[str, Any]]  # suggested rule scope: [{"field", "op", "value", "label"}]
    highlights: list[tuple[str, str]] = field(default_factory=list)  # short label/value pairs for the card


class Session:
    """One agent attempt. The integrator's agent calls tools through it."""

    def __init__(self, guard: Guard, ticket: dict, number: int, guidance: list[str], rules: list[str]) -> None:
        self.guard = guard
        self.ticket = ticket
        self.number = number
        self.guidance = guidance  # corrections from review of the previous attempt
        self.rules = rules  # remembered decisions, in plain language
        self.ledger = Ledger(prefix=f"a{number}")
        self.staged: list[dict] = []
        self.decision_request: dict | None = None
        self.draft = ""
        self.error: str | None = None

    def call(self, name: str, fn: Callable[[], Any], args: dict | None = None, *, kind: str = "tool") -> Any:
        """Run a read-only tool and record it. ``kind="source"`` marks help-center lookups."""
        return self.ledger.record(kind, name, args or {}, lambda: _tool_span(fn))

    def propose(self, action: str, **params: Any) -> dict:
        """Stage a write. Nothing runs until Once's checks pass."""

        def stage() -> dict:
            spec = self.guard.actions.get(action)
            if not spec:
                raise ValueError(f"'{action}' is not a registered action")
            if spec.validate:
                spec.validate(params)
            self.staged.append({"type": action, **params})
            return {"status": "proposed", "type": action, **params}

        return self.ledger.record("tool", f"propose_{action}", params, lambda: _tool_span(stage))

    def ask(self, question: str, options: list[str]) -> dict:
        """The agent's own request for a human decision."""

        def record() -> dict:
            self.decision_request = {"question": question, "options": options}
            return {"status": "sent_to_support_lead"}

        return self.ledger.record("tool", "request_decision", {"question": question, "options": options}, record)

    # Views the checks use.

    def steps(self, name: str | None = None, kind: str | None = None):
        return [s for s in self.ledger.steps if (name is None or s.name == name) and (kind is None or s.kind == kind)]

    def result(self, name: str):
        """The first successful result of a tool, or None."""
        for step in self.steps(name):
            if step.ok:
                return step.result
        return None


@neatlogs.span(kind="TOOL", name="tool_call")
def _tool_span(fn: Callable[[], Any]) -> Any:
    return fn()


class Sources(Protocol):
    """A help center Once can audit. ``status`` is "current" | "outdated" | "unmarked"."""

    def status(self, article_id: str) -> tuple[str, str | None]: ...  # (status, superseded_by)

    def title(self, article_id: str) -> str: ...

    def body(self, article_id: str) -> str: ...

    def repair(self, stale_id: str, current_id: str) -> None: ...


@dataclass
class ActionSpec:
    name: str
    commit: Callable[..., dict]
    verify: Callable[[dict, dict], tuple[bool, str]] | None  # (params, commit result) -> (landed, detail)
    validate: Callable[[dict], None] | None
    description: str


@dataclass
class CheckSpec:
    name: str
    fn: Callable[[CheckContext], list[Finding]]
    description: str


@dataclass
class DriftCase:
    id: str
    title: str
    why: str
    ticket: dict
    expect: Callable[[Any, Guard], tuple[bool, str]]  # (ticket run, guard on a fresh environment)


@dataclass
class CheckContext:
    ticket: dict
    session: Session
    memory: PolicyMemory
    guard: Guard


class Guard:
    def __init__(self, company: str, memory: PolicyMemory, *, config: dict | None = None) -> None:
        self.company = company
        self.memory = memory
        self.config = config or {}
        self.actions: dict[str, ActionSpec] = {}
        self.checks: list[CheckSpec] = []
        self.cases: list[DriftCase] = []
        self.sources: Sources | None = None
        self._agent: Callable[[Session], None] | None = None
        self.env: Any = None  # the integrator's own state (clients, fixtures), opaque to Once

    # Registration -------------------------------------------------------------

    def agent(self, fn: Callable[[Session], None]) -> Callable[[Session], None]:
        self._agent = fn
        return fn

    def action(self, name: str, *, verify=None, validate=None):
        def register(fn: Callable[..., dict]) -> Callable[..., dict]:
            self.actions[name] = ActionSpec(name, fn, verify, validate, (fn.__doc__ or "").strip())
            return fn

        return register

    def check(self, fn: Callable[[CheckContext], list[Finding]]):
        self.checks.append(CheckSpec(fn.__name__, fn, (fn.__doc__ or "").strip()))
        return fn

    def case(self, id: str, title: str, why: str, ticket: dict):
        def register(fn):
            self.cases.append(DriftCase(id, title, why, ticket, fn))
            return fn

        return register

    # Running ------------------------------------------------------------------

    def attempt(self, ticket: dict, number: int, guidance: list[str]) -> Session:
        if not self._agent:
            raise RuntimeError(f"{self.company} has not registered an agent with @guard.agent")
        session = Session(self, ticket, number, guidance, [r.describe for r in self.memory.active()])
        started = time.time()
        try:
            _agent_span(self._agent, session)
        except Exception as exc:  # the agent's crash is a finding, not a desk crash
            session.error = f"{type(exc).__name__}: {exc}"
        session.ledger.elapsed_ms = int((time.time() - started) * 1000)
        return session

    def describe(self) -> dict:
        return {
            "company": self.company,
            "actions": [
                {"name": a.name, "verify": a.verify is not None, "description": a.description}
                for a in self.actions.values()
            ],
            "checks": [{"name": c.name, "description": c.description} for c in self.checks],
            "cases": [{"id": c.id, "title": c.title, "why": c.why} for c in self.cases],
            "sources": self.sources is not None,
        }


@neatlogs.span(kind="AGENT", name="customer_agent")
def _agent_span(agent: Callable[[Session], None], session: Session) -> None:
    agent(session)
