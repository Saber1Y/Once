"""ACME's business checks, registered with Once through ``@guard.check``.

Once supplies the generic checks (outdated sources, writes that didn't land,
unsupported amounts, needless escalation). These encode what only ACME knows:
its refund policy, where refunds stop being policy and become a choice, and what
each support plan includes.
"""

from __future__ import annotations

import math
import re

from once.core import CheckContext, Choice, Finding

REFUND_WORDS = re.compile(r"\b(refund|return|money back|reimburse)", re.I)
CALLBACK_PROMISE = re.compile(
    r"\b(will|'ll|shall|going to)\b(?![^.]{0,20}\bnot\b)[^.]{0,40}\b(call|phone|ring) (you|back)\b"
    r"|\b(schedul|arrang)\w*[^.]{0,30}\b(call|callback|phone)\b"
    r"|\bcall you (back|shortly|soon|now|today)\b",
    re.I,
)
# Only phrasing that states the refund window itself, not e.g. "a 7-day grace period" from a remembered rule.
WINDOW_CLAIM = re.compile(
    r"\b(\d{1,3})[- ]day (?:refund |return )?(?:window|policy)\b"
    r"|\bwithin (\d{1,3}) days of (?:the |your )?(?:original |date of )?(?:purchase|transaction|order|delivery)",
    re.I,
)

OUTCOME_LABELS = {"refund": "Refund in full", "store_credit": "Offer store credit", "decline": "Decline politely"}
RULE_LABELS = {"refund": "Refund", "store_credit": "Offer store credit", "decline": "Decline"}


def refund_window(ctx: CheckContext) -> tuple[int, str]:
    """The refund window from the *current* help-center article, never from what the agent retrieved."""
    sources = ctx.guard.sources
    article = sources.current("refund-policy-v2.1")
    match = re.search(r"within (\d+) days", sources.body(article))
    if not match:
        raise RuntimeError(f"Could not read the refund window from {article}")
    return int(match.group(1)), article


def expected_refund(ctx: CheckContext, order: dict, customer: dict) -> dict:
    window, _ = refund_window(ctx)
    days_over = order["days_since_purchase"] - window
    facts = {"tenure_years": customer["tenure_years"], "days_over": days_over}
    if order["refunded_amount"] + order["credit_amount"] >= order["amount"]:
        return {"outcome": "decline", "reason": "This order has already been refunded.", "window": window, **facts}
    if days_over <= 0:
        return {"outcome": "refund", "reason": f"Inside the {window}-day window.", "window": window, **facts}
    rule = ctx.memory.lookup("refund_exception", facts)
    if rule:
        return {
            "outcome": rule.outcome,
            "reason": f"Remembered rule v{rule.version}: {rule.describe}",
            "window": window,
            "rule_id": rule.id,
            **facts,
        }
    cfg = ctx.guard.config.get("choice_boundary", {}).get("refund_exception", {})
    if facts["tenure_years"] >= cfg.get("min_tenure_years", 1) and days_over <= cfg.get("max_days_over", 7):
        return {
            "outcome": "choice",
            "reason": f"{days_over} days past the {window}-day window, customer for "
            f"{facts['tenure_years']:g} years. No written policy or remembered rule covers this.",
            "window": window,
            **facts,
        }
    return {
        "outcome": "decline",
        "reason": f"{days_over} days past the {window}-day window.",
        "window": window,
        **facts,
    }


def refund_policy(ctx: CheckContext) -> list[Finding]:
    """Refunds follow the current policy, remembered rules, and ACME's choice boundary."""
    s = ctx.session
    customer = s.result("lookup_customer")
    if not customer:
        return []
    staged_refunds = [a for a in s.staged if a["type"] in ("refund", "store_credit")]
    if not (REFUND_WORDS.search(ctx.ticket["subject"] + " " + ctx.ticket["body"]) or staged_refunds):
        return []
    world = ctx.guard.env.world
    order_ids = {st.result["id"] for st in s.steps("get_order") if st.ok} | {a["order_id"] for a in staged_refunds}
    findings = []
    for order_id in sorted(order_ids):
        order = world.order(order_id)
        if order["customer_id"] != customer["id"]:
            continue
        exp = expected_refund(ctx, order, customer)
        evidence = [
            st.id for st in s.ledger.steps if st.args.get("order_id") == order_id or st.name == "lookup_customer"
        ]
        if exp["outcome"] == "choice":
            findings.append(
                Finding(
                    "needs_choice",
                    "decision",
                    "choice",
                    "This is a business decision",
                    exp["reason"],
                    evidence=evidence,
                    data={
                        "choice": Choice(
                            domain="refund_exception",
                            question=(
                                f"{customer['name']} has been a customer for {customer['tenure_years']:g} years and is "
                                f"{exp['days_over']} day{'s' if exp['days_over'] != 1 else ''} past the "
                                f"{exp['window']}-day "
                                f"refund window for the {order['product']} (${order['amount']:.2f}). "
                                "Refund, store credit, or decline?"
                            ),
                            facts={"tenure_years": exp["tenure_years"], "days_over": exp["days_over"]},
                            options=[{"value": k, "label": v} for k, v in OUTCOME_LABELS.items()],
                            conditions=[
                                {
                                    "field": "tenure_years",
                                    "op": ">=",
                                    "value": float(min(2, math.floor(exp["tenure_years"]))),
                                    "label": "the customer has been with us {value}+ years",
                                    "unit": "years",
                                },
                                {
                                    "field": "days_over",
                                    "op": "<=",
                                    "value": max(exp["days_over"], 7),
                                    "label": "they are up to {value} days past the window",
                                    "unit": "days late",
                                },
                            ],
                            highlights=[
                                ("Customer for", f"{exp['tenure_years']:g} yrs"),
                                ("Past window", f"{exp['days_over']} days"),
                                ("Order", f"${order['amount']:.2f}"),
                            ],
                        )
                    },
                )
            )
            continue
        have = staged_refunds[0]["type"] if [a for a in staged_refunds if a["order_id"] == order_id] else "decline"
        if exp["outcome"] != have:
            findings.append(
                Finding(
                    "wrong_outcome",
                    "decision",
                    "mechanical",
                    "Proposed the wrong outcome for this refund",
                    f"Expected {exp['outcome'].replace('_', ' ')} but the agent proposed "
                    f"{have.replace('_', ' ')}. {exp['reason']}",
                    evidence=evidence,
                    data={"order_id": order_id, "rule_id": exp.get("rule_id")},
                    correction=(
                        f"For order {order_id} the correct outcome is {exp['outcome'].replace('_', ' ')}. "
                        f"{exp['reason']} Propose exactly that, and explain it to the customer."
                    ),
                )
            )
            continue
        if exp.get("rule_id"):
            findings.append(
                Finding(
                    "rule_applied",
                    "decision",
                    "info",
                    "Followed a remembered rule",
                    exp["reason"],
                    data={"rule_id": exp["rule_id"]},
                )
            )
        mine = [a for a in staged_refunds if a["order_id"] == order_id]
        if mine and abs(mine[0]["amount"] - order["amount"]) > 0.005:
            findings.append(
                Finding(
                    "wrong_amount",
                    "execution",
                    "mechanical",
                    "Proposed the wrong amount",
                    f"Proposed ${mine[0]['amount']:.2f}; the order total is ${order['amount']:.2f}.",
                    evidence=evidence,
                    correction=f"Refund the full order total of ${order['amount']:.2f}.",
                )
            )
        claimed = {int(a or b) for a, b in WINDOW_CLAIM.findall(s.draft)}
        from_rules = {c["value"] for r in ctx.memory.active() for c in r.conditions}
        wrong = sorted(n for n in claimed if n != exp["window"] and n not in from_rules)
        if wrong:
            findings.append(
                Finding(
                    "wrong_window",
                    "context",
                    "mechanical",
                    "Quoted the wrong refund window",
                    f"The reply mentions a {wrong[0]}-day window; the current policy is {exp['window']} days.",
                    correction=f"The current refund window is {exp['window']} days.",
                )
            )
    return findings


def plan_promises(ctx: CheckContext) -> list[Finding]:
    """Starter-plan customers get email support only: never promise a phone call."""
    customer = ctx.session.result("lookup_customer")
    if not customer or customer["plan"] != "Starter":
        return []
    match = CALLBACK_PROMISE.search(ctx.session.draft)
    if not match:
        return []
    return [
        Finding(
            "forbidden_promise",
            "decision",
            "mechanical",
            "Promised a phone call the plan doesn't include",
            f'The reply says "{match.group(0).strip()}". The Starter plan SLA allows email support only.',
            evidence=[s.id for s in ctx.session.steps("lookup_customer")],
            correction=(
                "The customer is on the Starter plan: do not promise, offer or schedule a phone call. "
                "Acknowledge the urgency, explain the 24-hour email support window, and ask for details."
            ),
        )
    ]
