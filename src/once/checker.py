"""Check: compare what the agent said and proposed with what is actually true.

Deterministic checks run first and decide almost everything. The cheap tier-2
judge runs only when the draft contains numeric claims the deterministic checks
could not account for. Every finding is sorted into the neatlogs failure
taxonomy (context, decision, execution, trajectory) and marked as either
mechanical (Once fixes it) or a choice (Once asks the support lead).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

import neatlogs

from once.agent import Attempt
from once.config import settings
from once.policy import Expectation, PolicyMemory, expected_refund, refund_window_days
from once.world.kb import KnowledgeBase
from once.world.store import World

REFUND_WORDS = re.compile(r"\b(refund|return|money back|reimburse)", re.I)
CALLBACK_PROMISE = re.compile(
    r"\b(will|'ll|shall|going to)\b(?![^.]{0,20}\bnot\b)[^.]{0,40}\b(call|phone|ring) (you|back)\b"
    r"|\b(schedul|arrang)\w*[^.]{0,30}\b(call|callback|phone)\b"
    r"|\bcall you (back|shortly|soon|now|today)\b",
    re.I,
)
SUCCESS_CLAIM = {
    "address_change": re.compile(
        r"\b(updated|changed|corrected|now ship|will ship to|has been (updated|changed))\b", re.I
    ),
    "refund": re.compile(r"\b(refunded|processed|issued|approved)\b", re.I),
}
DOLLARS = re.compile(r"\$\s?(\d[\d,]*(?:\.\d{2})?)")
WINDOW_CLAIM = re.compile(r"\b(\d{1,3})[- ]day\b|\bwithin (\d{1,3}) days\b", re.I)


@dataclass
class Finding:
    code: str
    category: str  # "context" | "decision" | "execution" | "trajectory"
    route: str  # "mechanical" | "choice"
    title: str
    detail: str
    evidence: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    tier: str = "deterministic"

    def to_dict(self) -> dict:
        return asdict(self)


class Checker:
    def __init__(self, world: World, kb: KnowledgeBase, memory: PolicyMemory) -> None:
        self.world = world
        self.kb = kb
        self.memory = memory

    # -- pre-commit ----------------------------------------------------------

    @neatlogs.span(kind="CHAIN", name="check_before_commit")
    def before_commit(self, ticket: dict, attempt: Attempt) -> tuple[list[Finding], dict[str, Expectation]]:
        findings: list[Finding] = []
        findings += self._stale_sources(attempt)
        expectations = self._refund_expectations(ticket, attempt)
        findings += self._refund_outcomes(attempt, expectations)
        findings += self._promises(attempt)
        if not any(f.code == "stale_source" for f in findings):
            findings += self._window_claims(attempt, expectations)
        findings += self._amount_claims(attempt)
        if attempt.error:
            findings.append(Finding("no_reply", "trajectory", "mechanical", "Agent did not finish", attempt.error))
        return findings, expectations

    def _stale_sources(self, attempt: Attempt) -> list[Finding]:
        findings = []
        for article_id in attempt.kb_articles():
            page = self.kb.page(article_id)
            if page.status == "outdated":
                steps = [
                    s.id
                    for s in attempt.ledger.find("search_kb")
                    if any(h.get("article_id") == article_id for h in s.result or [])
                ]
                findings.append(
                    Finding(
                        "stale_source",
                        "context",
                        "mechanical",
                        "Answered from an outdated policy",
                        f"The agent retrieved '{page.title}' ({article_id}). The live help center marks it "
                        f"outdated and superseded by {page.superseded_by}.",
                        evidence=steps,
                        data={"stale": article_id, "current": page.superseded_by},
                    )
                )
        return findings

    def _refund_expectations(self, ticket: dict, attempt: Attempt) -> dict[str, Expectation]:
        customer = attempt.customer()
        if not customer:
            return {}
        is_refund_ticket = bool(REFUND_WORDS.search(ticket["subject"] + " " + ticket["body"]))
        order_ids = list(attempt.orders_seen())
        for action in attempt.staged:
            if action["type"] in ("refund", "store_credit") and action["order_id"] not in order_ids:
                order_ids.append(action["order_id"])
                is_refund_ticket = True
        if not is_refund_ticket:
            return {}
        window, _ = refund_window_days(self.kb)
        out = {}
        for order_id in order_ids:
            order = self.world.order(order_id)
            if order["customer_id"] != customer["id"]:
                continue
            out[order_id] = expected_refund(order, customer, window, self.memory)
        return out

    def _refund_outcomes(self, attempt: Attempt, expectations: dict[str, Expectation]) -> list[Finding]:
        findings = []
        for order_id, exp in expectations.items():
            staged = [
                a for a in attempt.staged if a["order_id"] == order_id and a["type"] in ("refund", "store_credit")
            ]
            proposal_steps = [
                s.id
                for s in attempt.ledger.steps
                if s.name in ("propose_refund", "propose_store_credit") and s.args.get("order_id") == order_id
            ]
            order_steps = [s.id for s in attempt.ledger.find("get_order") if s.args.get("order_id") == order_id]
            if exp.outcome == "needs_choice":
                findings.append(
                    Finding(
                        "needs_choice",
                        "decision",
                        "choice",
                        "This is a business decision",
                        exp.reason,
                        evidence=order_steps + [s.id for s in attempt.ledger.find("lookup_customer")],
                        data={"order_id": order_id, "days_over": exp.days_over, "window_days": exp.window_days},
                    )
                )
                continue
            if attempt.decision_request:
                findings.append(
                    Finding(
                        "needless_escalation",
                        "trajectory",
                        "mechanical",
                        "Asked about a case policy already covers",
                        f"The agent asked the support lead, but {exp.reason}",
                        evidence=[s.id for s in attempt.ledger.find("request_decision")],
                        data={"order_id": order_id, "expected": exp.outcome},
                    )
                )
            want = exp.outcome
            have = staged[0]["type"] if staged else "decline"
            if want == "already_refunded":
                want = "decline"
            if want != have:
                findings.append(
                    Finding(
                        "wrong_outcome",
                        "decision",
                        "mechanical",
                        "Proposed the wrong outcome for this refund",
                        f"Expected {want.replace('_', ' ')} but the agent proposed "
                        f"{have.replace('_', ' ')}. {exp.reason}",
                        evidence=proposal_steps or order_steps,
                        data={"order_id": order_id, "expected": want, "proposed": have, "rule_id": exp.rule_id},
                    )
                )
            elif staged and want in ("refund", "store_credit"):
                order = self.world.order(order_id)
                if abs(staged[0]["amount"] - order["amount"]) > 0.005:
                    findings.append(
                        Finding(
                            "wrong_amount",
                            "execution",
                            "mechanical",
                            "Proposed the wrong amount",
                            f"Proposed ${staged[0]['amount']:.2f}; the order total is ${order['amount']:.2f}.",
                            evidence=proposal_steps,
                            data={"order_id": order_id, "expected_amount": order["amount"]},
                        )
                    )
        return findings

    def _promises(self, attempt: Attempt) -> list[Finding]:
        customer = attempt.customer()
        if not customer or customer["plan"] != "Starter":
            return []
        match = CALLBACK_PROMISE.search(attempt.draft)
        if not match:
            return []
        return [
            Finding(
                "forbidden_promise",
                "decision",
                "mechanical",
                "Promised a phone call the plan doesn't include",
                f'The draft says "{match.group(0).strip()}". The Starter plan SLA (starter-support-sla) '
                "allows email support only: acknowledge the urgency without promising a callback.",
                evidence=[s.id for s in attempt.ledger.find("lookup_customer")],
                data={"quote": match.group(0).strip()},
            )
        ]

    def _window_claims(self, attempt: Attempt, expectations: dict[str, Expectation]) -> list[Finding]:
        if not expectations:
            return []
        window = next(iter(expectations.values())).window_days
        claimed = {int(a or b) for a, b in WINDOW_CLAIM.findall(attempt.draft)}
        wrong = sorted(n for n in claimed if n != window and n >= 7)
        if not wrong:
            return []
        return [
            Finding(
                "wrong_window",
                "context",
                "mechanical",
                "Quoted the wrong refund window",
                f"The draft mentions a {wrong[0]}-day window; the current policy is {window} days.",
                data={"claimed": wrong[0], "window": window},
            )
        ]

    def _amount_claims(self, attempt: Attempt) -> list[Finding]:
        known = set()
        for step in attempt.ledger.find("get_order"):
            if step.ok:
                known.add(round(float(step.result["amount"]), 2))
        for action in attempt.staged:
            if "amount" in action:
                known.add(round(action["amount"], 2))
        claimed = {round(float(m.replace(",", "")), 2) for m in DOLLARS.findall(attempt.draft)}
        unknown = sorted(claimed - known)
        if not unknown or not known:
            return []
        return [
            Finding(
                "unsupported_amount",
                "context",
                "mechanical",
                "Stated an amount no tool returned",
                f"The draft mentions ${unknown[0]:.2f}, which doesn't match any order or proposed amount.",
                data={"amount": unknown[0]},
            )
        ]

    # -- post-commit ---------------------------------------------------------

    @neatlogs.span(kind="CHAIN", name="verify_after_commit")
    def after_commit(self, attempt: Attempt, commits: list[dict]) -> list[Finding]:
        findings = []
        for commit in commits:
            action, result = commit["action"], commit["result"]
            if action["type"] == "address_change":
                order = self.world.order(action["order_id"])
                job = self.world.address_job(result["job_id"]) if result.get("job_id") else None
                landed = order["shipping_address"].strip().lower() == action["new_address"].strip().lower()
                if not landed:
                    claimed = bool(SUCCESS_CLAIM["address_change"].search(attempt.draft))
                    findings.append(
                        Finding(
                            "side_effect_missing",
                            "execution",
                            "mechanical",
                            "Would have confirmed an update that failed"
                            if claimed
                            else "The address change didn't land",
                            f"The address service returned '{result.get('status')}', but the background job "
                            f"{'failed: ' + job['error'] if job and job['error'] else 'did not apply the change'}. "
                            + ("The draft tells the customer it's done." if claimed else ""),
                            evidence=[commit["step_id"]],
                            data={
                                "order_id": action["order_id"],
                                "new_address": action["new_address"],
                                "job": job,
                                "claimed_success": claimed,
                                "fault_label": self.world.fault_label(action["order_id"], "address_write"),
                            },
                        )
                    )
            elif action["type"] in ("refund", "store_credit") and not commit["ok"]:
                findings.append(
                    Finding(
                        "commit_failed",
                        "execution",
                        "mechanical",
                        "The refund didn't go through",
                        str(result),
                        evidence=[commit["step_id"]],
                        data={"order_id": action["order_id"]},
                    )
                )
        return findings

    # -- tier 2 --------------------------------------------------------------

    def needs_judge(self, attempt: Attempt, findings: list[Finding]) -> bool:
        if findings or not settings.judge_model:
            return False
        return bool(re.search(r"\d", attempt.draft))

    @neatlogs.span(kind="CHAIN", name="tier2_judge")
    def judge(self, attempt: Attempt) -> list[Finding]:
        from once.llm import chat

        evidence = [s.to_dict() for s in attempt.ledger.steps]
        prompt = (
            "You check a customer-support reply against the tool results it was based on.\n"
            "List statements in the reply that state a specific fact (number, date, status, "
            "timeframe) that the tool results do not support. Generic courtesy is fine.\n"
            'Return JSON: {"unsupported": [{"quote": "...", "why": "..."}]}\n\n'
            f"TOOL RESULTS:\n{json.dumps(evidence, default=str)[:12000]}\n\nREPLY:\n{attempt.draft}"
        )
        message = chat([{"role": "user", "content": prompt}], model=settings.judge_model, json_mode=True)
        try:
            items = json.loads(message.content or "{}").get("unsupported", [])
        except json.JSONDecodeError:
            return []
        return [
            Finding(
                "unsupported_claim",
                "context",
                "mechanical",
                "Stated something no tool returned",
                f'"{i.get("quote", "")}": {i.get("why", "")}',
                data={"quote": i.get("quote", "")},
                tier="judge",
            )
            for i in items[:3]
            if i.get("quote")
        ]
