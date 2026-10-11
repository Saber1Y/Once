"""Policy memory: a person's answers, stored as versioned rules over facts.

A rule is ``domain + conditions -> outcome``, for example
``refund_exception: tenure_years >= 2 and days_over <= 7 -> refund``. Checks ask
the memory before routing a case to a person, so the same question is never
asked twice. Rules are company data, stored per tenant.
"""

from __future__ import annotations

import json
import operator
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt, "==": operator.eq}


@dataclass
class Rule:
    id: str
    version: int
    domain: str
    conditions: list[dict[str, Any]]  # [{"field", "op", "value", "label"}]
    outcome: str
    outcome_label: str
    question: str
    source_ticket: str
    decided_by: str
    status: str = "active"  # "active" | "held" | "candidate"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    held_reason: str | None = None

    def matches(self, domain: str, facts: dict[str, Any]) -> bool:
        if domain != self.domain:
            return False
        for c in self.conditions:
            value = facts.get(c["field"])
            if value is None or not OPS[c["op"]](value, c["value"]):
                return False
        return True

    @property
    def describe(self) -> str:
        parts = [c["label"].format(value=_fmt(c["value"])) for c in self.conditions]
        return f"{self.outcome_label} when {' and '.join(parts)}."


def _fmt(value: Any) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


class PolicyMemory:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.rules: list[Rule] = []
        if path and path.exists():
            self.rules = [Rule(**r) for r in json.loads(path.read_text())]

    @classmethod
    def ephemeral(cls, rules: list[Rule] | None = None) -> PolicyMemory:
        memory = cls()
        memory.rules = [Rule(**asdict(r)) for r in (rules or [])]
        return memory

    def active(self) -> list[Rule]:
        return [r for r in self.rules if r.status == "active"]

    def lookup(self, domain: str, facts: dict[str, Any]) -> Rule | None:
        """The newest active rule covering these facts."""
        for rule in reversed(self.active()):
            if rule.matches(domain, facts):
                return rule
        return None

    def new_rule(self, **kwargs: Any) -> Rule:
        version = max((r.version for r in self.rules), default=0) + 1
        return Rule(id=f"P-{uuid.uuid4().hex[:6]}", version=version, **kwargs)

    def add(self, rule: Rule) -> None:
        with self._lock:
            self.rules.append(rule)
            self.save()

    def clear(self) -> None:
        with self._lock:
            self.rules = []
            self.save()

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(r) for r in self.rules]
        self.path.write_text(json.dumps(data, indent=2))
        self.path.with_suffix(".yaml").write_text(
            yaml.safe_dump({"policies": data}, sort_keys=False, allow_unicode=True)
        )
