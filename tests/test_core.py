"""Deterministic tests: world, knowledge base parsing, policy oracle and checks.

These do not call a model. The full loop is exercised by `once demo` and
`once drift` against the real LiteLLM proxy.
"""

from datetime import date

import pytest

from once.agent import Attempt
from once.checker import Checker
from once.ledger import Ledger
from once.policy import PolicyMemory, expected_refund, refund_window_days
from once.world.kb import KnowledgeBase, SearchIndex, parse_article
from once.world.store import World, WorldError

TODAY = date(2026, 10, 11)

STALE_HTML = """<div class="banner"><strong>Outdated.</strong> superseded on March 4. See the
<a href="refund-policy-v3.0.html">current refund policy</a>.</div><h1>Refund Policy</h1>
<p class="meta">Article ID <code>refund-policy-v2.1</code> · Last updated February 18, 2026</p>
<p>You may request a refund within <strong>30 days</strong> of the original transaction date.</p>"""

CURRENT_HTML = """<div class="banner success"><strong>Current.</strong> Effective March 4, 2026.</div>
<h1>Refund Policy</h1><p class="meta">Last updated March 4, 2026</p>
<p>You may request a refund within <strong>14 days</strong> of the original transaction date.</p>"""

SLA_HTML = """<h1>Starter Plan Support SLA</h1><p>Starter plan customers receive email support with a
24 hour response window. Phone callbacks are available only on Business plans.</p>"""


class FakeKB(KnowledgeBase):
    def __init__(self):
        super().__init__("https://example.invalid")
        pages = {
            "refund-policy-v2.1": STALE_HTML,
            "refund-policy-v3.0": CURRENT_HTML,
            "starter-support-sla": SLA_HTML,
            "billing-dispute-sop": "<h1>Billing</h1><p>x</p>",
            "password-reset": "<h1>Reset</h1><p>x</p>",
            "checkout-outage-runbook": "<h1>Checkout</h1><p>x</p>",
        }
        self._articles = {k: parse_article(k, v, k) for k, v in pages.items()}


@pytest.fixture
def world():
    return World.seeded(today=TODAY)


@pytest.fixture
def kb():
    return FakeKB()


def attempt_with(world, steps, draft="", staged=None):
    attempt = Attempt(number=1, ledger=Ledger("a1"), draft=draft, staged=staged or [])
    for name, args, fn in steps:
        attempt.ledger.record("tool", name, args, fn)
    return attempt


def test_parse_article_status_and_supersession():
    stale = parse_article("refund-policy-v2.1", STALE_HTML, "u")
    assert stale.status == "outdated" and stale.superseded_by == "refund-policy-v3.0"
    assert "Outdated" not in stale.body and "30 days" in stale.body
    assert parse_article("refund-policy-v3.0", CURRENT_HTML, "u").status == "current"


def test_refund_window_follows_supersession(kb):
    assert refund_window_days(kb) == (14, "refund-policy-v3.0")


def test_seeded_index_returns_stale_policy_until_repaired(kb):
    index = SearchIndex(kb)
    assert index.search("refund policy")[0]["article_id"] == "refund-policy-v2.1"
    index.replace("refund-policy-v2.1", "refund-policy-v3.0")
    assert index.search("refund policy")[0]["article_id"] == "refund-policy-v3.0"


def test_address_write_is_accepted_but_fault_makes_job_fail(world):
    result = world.request_address_change("O-5001", "88 River Road")
    assert result["status"] == "accepted"
    assert world.address_job(result["job_id"])["status"] == "failed"
    assert world.order("O-5001")["shipping_address"] != "88 River Road"
    world.request_address_change("O-5001", "88 River Road")
    assert world.order("O-5001")["shipping_address"] == "88 River Road"


def test_refund_cannot_exceed_order_total(world):
    world.refund("O-5006", 320.0, "dead pixel")
    with pytest.raises(WorldError):
        world.refund("O-5006", 1.0, "again")


def test_oracle_outcomes(world):
    memory = PolicyMemory.ephemeral()
    cases = {
        "O-5006": "refund",
        "O-5002": "decline",
        "O-5003": "needs_choice",
        "O-5009": "needs_choice",
        "O-5010": "decline",
        "O-5008": "decline",
    }
    for order_id, want in cases.items():
        order = world.order(order_id)
        customer = world.customer(customer_id=order["customer_id"])
        assert expected_refund(order, customer, 14, memory).outcome == want, order_id


def test_remembered_rule_covers_next_case(world):
    memory = PolicyMemory.ephemeral()
    memory.rules.append(
        memory.new_rule(
            kind="refund_exception",
            min_tenure_years=2,
            max_days_over=7,
            outcome="refund",
            question="q",
            source_ticket="T-103",
            decided_by="Maya",
        )
    )
    order = world.order("O-5009")
    exp = expected_refund(order, world.customer(customer_id=order["customer_id"]), 14, memory)
    assert exp.outcome == "refund" and exp.rule_id
    order = world.order("O-5010")  # 10 days over: outside the rule
    assert expected_refund(order, world.customer(customer_id=order["customer_id"]), 14, memory).outcome == "decline"


def test_checker_flags_stale_source_and_wrong_outcome(world, kb):
    index = SearchIndex(kb)
    attempt = attempt_with(
        world,
        [
            ("lookup_customer", {"email": "tom@example.com"}, lambda: world.customer(email="tom@example.com")),
            ("get_order", {"order_id": "O-5002"}, lambda: world.order("O-5002")),
            ("search_kb", {"query": "refund policy"}, lambda: index.search("refund policy")),
        ],
        draft="Good news, you're within our 30-day window so I've refunded $249.00.",
        staged=[{"type": "refund", "order_id": "O-5002", "amount": 249.0, "reason": "fit"}],
    )
    ticket = {"id": "T-102", "subject": "Refund for headphones", "body": "Can I get a refund?"}
    findings, _ = Checker(world, kb, PolicyMemory.ephemeral()).before_commit(ticket, attempt)
    codes = {f.code for f in findings}
    assert {"stale_source", "wrong_outcome"} <= codes
    assert all(f.route == "mechanical" for f in findings)


def test_checker_routes_gray_zone_to_choice(world, kb):
    attempt = attempt_with(
        world,
        [
            ("lookup_customer", {"email": "grace@example.com"}, lambda: world.customer(email="grace@example.com")),
            ("get_order", {"order_id": "O-5003"}, lambda: world.order("O-5003")),
        ],
        draft="Unfortunately we can't refund this.",
    )
    ticket = {"id": "T-103", "subject": "Refund request", "body": "I'd like a refund"}
    findings, _ = Checker(world, kb, PolicyMemory.ephemeral()).before_commit(ticket, attempt)
    assert [f.route for f in findings] == ["choice"]


def test_checker_blocks_callback_promise_for_starter(world, kb):
    attempt = attempt_with(
        world,
        [
            ("lookup_customer", {"email": "luis@example.com"}, lambda: world.customer(email="luis@example.com")),
        ],
        draft="So sorry! One of our engineers will call you within the hour.",
    )
    findings, _ = Checker(world, kb, PolicyMemory.ephemeral()).before_commit(
        {"id": "T-104", "subject": "URGENT call me", "body": "call me"}, attempt
    )
    assert [f.code for f in findings] == ["forbidden_promise"]


def test_checker_catches_false_success_after_failed_write(world, kb):
    attempt = attempt_with(
        world,
        [
            ("lookup_customer", {"email": "priya@example.com"}, lambda: world.customer(email="priya@example.com")),
        ],
        draft="Done! Your address has been updated to 88 River Road.",
    )
    action = {"type": "address_change", "order_id": "O-5001", "new_address": "88 River Road"}
    result = world.request_address_change("O-5001", "88 River Road")
    commits = [{"action": action, "result": result, "ok": True, "step_id": "a1.2"}]
    findings = Checker(world, kb, PolicyMemory.ephemeral()).after_commit(attempt, commits)
    assert findings[0].code == "side_effect_missing" and findings[0].data["claimed_success"]
