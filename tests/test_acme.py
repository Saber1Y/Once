"""ACME integration tests: its systems, help center and business checks. No model is called."""

from datetime import date

import pytest
from acme.checks import CALLBACK_PROMISE
from acme.helpcenter import KnowledgeBase, SearchIndex, parse_article
from acme.integration import AcmeEnv, create_guard
from acme.world import World, WorldError

from once import PolicyMemory
from once.checks import after_commit, before_commit
from once.core import CheckContext, Session

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
def guard():
    kb = FakeKB()
    return create_guard(PolicyMemory.ephemeral(), AcmeEnv(World.seeded(today=TODAY), kb, SearchIndex(kb)))


def session(guard, ticket, steps, draft="", staged=()):
    s = Session(guard, ticket, 1, [], [])
    for name, fn, kind in steps:
        s.call(name, fn, {}, kind=kind)
    s.draft = draft
    s.staged = list(staged)
    return s


def codes(guard, ticket, s):
    return [f.code for f in before_commit(CheckContext(ticket, s, guard.memory, guard)) if f.route != "info"]


def test_help_center_parsing_and_supersession(guard):
    stale = parse_article("refund-policy-v2.1", STALE_HTML, "u")
    assert stale.status == "outdated" and stale.superseded_by == "refund-policy-v3.0"
    assert "Outdated" not in stale.body and "30 days" in stale.body
    assert guard.sources.current("refund-policy-v2.1") == "refund-policy-v3.0"


def test_seeded_index_serves_the_outdated_policy_until_repaired(guard):
    assert guard.env.index.search("refund policy")[0]["article_id"] == "refund-policy-v2.1"
    guard.sources.repair("refund-policy-v2.1", "refund-policy-v3.0")
    assert guard.env.index.search("refund policy")[0]["article_id"] == "refund-policy-v3.0"


def test_address_write_is_accepted_but_the_injected_fault_fails_the_job(guard):
    world = guard.env.world
    result = world.request_address_change("O-5001", "88 River Road")
    assert result["status"] == "accepted" and world.address_job(result["job_id"])["status"] == "failed"
    world.request_address_change("O-5001", "88 River Road")
    assert world.order("O-5001")["shipping_address"] == "88 River Road"


def test_refund_cannot_exceed_the_order(guard):
    guard.env.world.refund("O-5006", 320.0, "dead pixel")
    with pytest.raises(WorldError):
        guard.env.world.refund("O-5006", 1.0, "again")


def test_stale_policy_and_wrong_refund_are_blocked(guard):
    w, idx = guard.env.world, guard.env.index
    ticket = {"id": "T-102", "subject": "Refund for headphones", "body": "Can I get a refund?"}
    s = session(
        guard,
        ticket,
        [
            ("lookup_customer", lambda: w.customer(email="tom@example.com"), "tool"),
            ("get_order", lambda: w.order("O-5002"), "tool"),
            ("search_kb", lambda: idx.search("refund policy"), "source"),
        ],
        draft="You're within our 30-day window, so I've refunded $249.00.",
        staged=[{"type": "refund", "order_id": "O-5002", "amount": 249.0, "reason": "fit"}],
    )
    assert set(codes(guard, ticket, s)) == {"outdated_source", "wrong_outcome"}


def test_loyal_just_late_refund_is_a_choice_then_a_rule(guard):
    w = guard.env.world
    ticket = {"id": "T-103", "subject": "Refund request", "body": "I'd like a refund"}
    steps = [
        ("lookup_customer", lambda: w.customer(email="grace@example.com"), "tool"),
        ("get_order", lambda: w.order("O-5003"), "tool"),
    ]
    findings = before_commit(CheckContext(ticket, session(guard, ticket, steps), guard.memory, guard))
    [choice] = [f for f in findings if f.route == "choice"]
    c = choice.data["choice"]
    assert c.domain == "refund_exception" and c.facts == {"tenure_years": 4.1, "days_over": 2}

    guard.memory.rules.append(
        guard.memory.new_rule(
            domain="refund_exception",
            conditions=[{**cond, "value": cond["value"]} for cond in c.conditions],
            outcome="refund",
            outcome_label="Refund",
            question=c.question,
            source_ticket="T-103",
            decided_by="Maya",
        )
    )
    elena = [
        ("lookup_customer", lambda: w.customer(email="elena@example.com"), "tool"),
        ("get_order", lambda: w.order("O-5009"), "tool"),
    ]
    staged = [{"type": "refund", "order_id": "O-5009", "amount": 480.0, "reason": "back pain"}]
    t109 = {"id": "T-109", "subject": "Chair refund", "body": "can I get my money back?"}
    assert codes(guard, t109, session(guard, t109, elena, staged=staged)) == []


def test_starter_customers_are_never_promised_a_call(guard):
    w = guard.env.world
    ticket = {"id": "T-104", "subject": "URGENT call me", "body": "call me"}
    s = session(
        guard,
        ticket,
        [("lookup_customer", lambda: w.customer(email="luis@example.com"), "tool")],
        draft="So sorry! One of our engineers will call you within the hour.",
    )
    assert codes(guard, ticket, s) == ["forbidden_promise"]
    assert not CALLBACK_PROMISE.search("We will not call you, sorry.")


def test_address_change_that_never_lands_is_caught(guard):
    w = guard.env.world
    s = session(guard, {"id": "T-101"}, [], draft="Done! Your address has been updated.")
    action = {"type": "address_change", "order_id": "O-5001", "new_address": "88 River Road"}
    result = guard.actions["address_change"].commit(order_id="O-5001", new_address="88 River Road")
    commits = [{"action": action, "result": result, "ok": True, "step_id": "a1.1"}]
    [finding] = after_commit(CheckContext({"id": "T-101"}, s, guard.memory, guard), commits)
    assert finding.code == "side_effect_missing" and finding.data["claimed_success"]
    assert w.order("O-5001")["shipping_address"] != "88 River Road"


def test_window_check_ignores_grace_periods_but_catches_stale_windows(guard):
    from acme.checks import WINDOW_CLAIM

    assert not WINDOW_CLAIM.search("You are within the 7-day grace period, so I refunded you.")
    assert WINDOW_CLAIM.search("Refunds are accepted within 30 days of purchase.")
    assert WINDOW_CLAIM.search("Our 30-day refund window covers this.")
    assert WINDOW_CLAIM.search("Our 14-day policy is strict, but as a 4-year customer you qualify.") is not None
