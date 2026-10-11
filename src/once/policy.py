"""ACME policy: the current written policy, the choice boundary, and remembered rules.

* The refund window comes from the *current* help-center article (following
  superseded-by links), never from what the agent happened to retrieve.
* ``needs_choice`` is ACME's escalation boundary: a refund just outside the window
  for a long-standing customer is a business decision, not a bug.
* ``PolicyMemory`` stores Maya's answers as versioned rules so the same question
  is never asked twice.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from once.config import DATA_DIR
from once.world.kb import KnowledgeBase

# ACME's escalation boundary. Outside this, the written policy decides on its own.
CHOICE_MIN_TENURE_YEARS = 1.0
CHOICE_MAX_DAYS_OVER = 7

POLICY_FILE = DATA_DIR / "policies.json"
POLICY_EXPORT = DATA_DIR / "policies.yaml"


def current_article(kb: KnowledgeBase, article_id: str) -> str:
    """Follow superseded-by links until reaching the current article."""
    seen = set()
    while article_id not in seen:
        seen.add(article_id)
        page = kb.page(article_id)
        if page.status != "outdated" or not page.superseded_by:
            return article_id
        article_id = page.superseded_by
    return article_id


def refund_window_days(kb: KnowledgeBase) -> tuple[int, str]:
    article_id = current_article(kb, "refund-policy-v2.1")
    match = re.search(r"within (\d+) days", kb.page(article_id).body)
    if not match:
        raise RuntimeError(f"Could not read the refund window from {article_id}")
    return int(match.group(1)), article_id


@dataclass
class Rule:
    id: str
    version: int
    kind: str  # "refund_exception"
    min_tenure_years: float
    max_days_over: int
    outcome: str  # "refund" | "store_credit" | "decline"
    question: str
    source_ticket: str
    decided_by: str
    status: str = "active"  # "active" | "held" | "candidate"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    held_reason: str | None = None

    def matches(self, tenure_years: float, days_over: int) -> bool:
        return (
            self.kind == "refund_exception"
            and tenure_years >= self.min_tenure_years
            and 0 < days_over <= self.max_days_over
        )

    def describe(self) -> str:
        verb = {"refund": "Refund", "store_credit": "Offer store credit", "decline": "Decline"}[self.outcome]
        return (
            f"{verb} when a customer of {self.min_tenure_years:g}+ years is up to "
            f"{self.max_days_over} days past the refund window."
        )


@dataclass
class Expectation:
    outcome: str  # "refund" | "store_credit" | "decline" | "needs_choice" | "already_refunded"
    reason: str
    window_days: int
    days_over: int
    rule_id: str | None = None


class PolicyMemory:
    def __init__(self, path: Path | None = POLICY_FILE, export: Path | None = POLICY_EXPORT) -> None:
        self.path = path
        self.export = export
        self._lock = threading.RLock()
        self.rules: list[Rule] = []
        if path and path.exists():
            self.rules = [Rule(**r) for r in json.loads(path.read_text())]

    @classmethod
    def ephemeral(cls, rules: list[Rule] | None = None) -> PolicyMemory:
        memory = cls(path=None, export=None)
        memory.rules = [Rule(**asdict(r)) for r in (rules or [])]
        return memory

    def active(self) -> list[Rule]:
        return [r for r in self.rules if r.status == "active"]

    def find(self, tenure_years: float, days_over: int) -> Rule | None:
        for rule in reversed(self.active()):
            if rule.matches(tenure_years, days_over):
                return rule
        return None

    def new_rule(self, **kwargs) -> Rule:
        version = max((r.version for r in self.rules), default=0) + 1
        return Rule(id=f"P-{uuid.uuid4().hex[:6]}", version=version, **kwargs)

    def add(self, rule: Rule) -> None:
        with self._lock:
            self.rules.append(rule)
            self.save()

    def update(self, rule: Rule) -> None:
        with self._lock:
            self.rules = [rule if r.id == rule.id else r for r in self.rules]
            self.save()

    def clear(self) -> None:
        with self._lock:
            self.rules = []
            self.save()

    def save(self) -> None:
        if not self.path:
            return
        data = [asdict(r) for r in self.rules]
        self.path.write_text(json.dumps(data, indent=2))
        if self.export:
            self.export.write_text(yaml.safe_dump({"policies": data}, sort_keys=False, allow_unicode=True))


def expected_refund(order: dict, customer: dict, window_days: int, memory: PolicyMemory) -> Expectation:
    days = order["days_since_purchase"]
    days_over = days - window_days
    if order["refunded_amount"] + order["credit_amount"] >= order["amount"]:
        return Expectation("already_refunded", "This order has already been refunded.", window_days, days_over)
    if days_over <= 0:
        return Expectation(
            "refund", f"Purchased {days} days ago, inside the {window_days}-day window.", window_days, days_over
        )
    tenure = customer["tenure_years"]
    rule = memory.find(tenure, days_over)
    if rule:
        return Expectation(
            rule.outcome,
            f"{days_over} days past the window; remembered rule v{rule.version} applies: {rule.describe()}",
            window_days,
            days_over,
            rule.id,
        )
    if tenure >= CHOICE_MIN_TENURE_YEARS and days_over <= CHOICE_MAX_DAYS_OVER:
        return Expectation(
            "needs_choice",
            f"{days_over} days past the {window_days}-day window, customer for {tenure:g} years. "
            "No written policy or remembered rule covers this.",
            window_days,
            days_over,
        )
    return Expectation("decline", f"{days_over} days past the {window_days}-day window.", window_days, days_over)
