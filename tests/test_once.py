"""Product tests: Once's built-in checks and memory, against a toy company.

The toy company here is deliberately not ACME, to show the SDK is not tied to
one integration. No model is called.
"""

from once import Choice, Finding, Guard, PolicyMemory
from once.checks import after_commit, before_commit
from once.core import CheckContext, Session
from once.memory import Rule


class ToySources:
    pages = {
        "returns-v1": ("Returns policy", "Returns within 60 days.", "outdated", "returns-v2"),
        "returns-v2": ("Returns policy", "Returns within 30 days.", "current", None),
        "shipping": ("Shipping times", "Ships in 2 days.", "current", None),
    }

    def __init__(self):
        self.repaired = []

    def status(self, article_id):
        _, _, status, newer = self.pages[article_id]
        return status, newer

    def title(self, article_id):
        return self.pages[article_id][0]

    def body(self, article_id):
        return self.pages[article_id][1]

    def repair(self, stale_id, current_id):
        self.repaired.append((stale_id, current_id))


def toy_guard(memory=None):
    guard = Guard("Toyshop", memory or PolicyMemory.ephemeral())
    guard.sources = ToySources()
    ledger = {"balance": 0}

    @guard.action("credit", verify=lambda a, r: (ledger["balance"] >= a["amount"], f"balance {ledger['balance']}"))
    def credit(amount: float) -> dict:
        return {"status": "accepted"}  # never actually applies: a write that doesn't land

    return guard


def session_with(guard, ticket, steps=(), draft="", staged=()):
    session = Session(guard, ticket, 1, [], [])
    for name, result, kind in steps:
        session.call(name, lambda r=result: r, {}, kind=kind)
    session.draft = draft
    session.staged = list(staged)
    return session


TICKET = {"id": "X-1", "from": "a@b.c", "subject": "Returns question", "body": "Can I still return my toy?"}


def test_outdated_source_is_flagged_only_when_relevant():
    guard = toy_guard()
    hit = [{"article_id": "returns-v1"}]
    s = session_with(guard, TICKET, [("search", hit, "source")], draft="Yes, within 60 days.")
    codes = [f.code for f in before_commit(CheckContext(TICKET, s, guard.memory, guard))]
    assert codes == ["outdated_source"]

    other = {"id": "X-2", "from": "a@b.c", "subject": "Where is my parcel", "body": "Tracking?"}
    s = session_with(guard, other, [("search", hit, "source")], draft="It ships in 2 days.")
    assert before_commit(CheckContext(other, s, guard.memory, guard)) == []


def test_unsupported_amount_and_routine_escalation():
    guard = toy_guard()
    s = session_with(guard, TICKET, [("order", {"total": 19.99}, "tool")], draft="We refunded $25.00.")
    s.ask("Should I refund?", ["yes", "no"])
    codes = {f.code for f in before_commit(CheckContext(TICKET, s, guard.memory, guard))}
    assert codes == {"unsupported_amount", "needless_escalation"}


def test_integrator_check_can_route_a_choice():
    guard = toy_guard()

    @guard.check
    def big_credits_are_a_choice(ctx):
        return [
            Finding(
                "needs_choice",
                "decision",
                "choice",
                "Big credit",
                "Over the limit",
                data={"choice": Choice("credit", "Approve?", {"amount": 500}, [], [])},
            )
        ]

    s = session_with(guard, TICKET)
    findings = before_commit(CheckContext(TICKET, s, guard.memory, guard))
    assert [(f.route, f.source) for f in findings] == [("choice", "big_credits_are_a_choice")]


def test_write_that_never_lands_is_caught_after_commit():
    guard = toy_guard()
    s = session_with(guard, TICKET, draft="Your credit has been applied.")
    commits = [
        {"action": {"type": "credit", "amount": 10.0}, "result": {"status": "accepted"}, "ok": True, "step_id": "a1.1"}
    ]
    [finding] = after_commit(CheckContext(TICKET, s, guard.memory, guard), commits)
    assert finding.code == "side_effect_missing" and finding.data["claimed_success"]


def test_unregistered_action_cannot_be_staged():
    guard = toy_guard()
    s = Session(guard, TICKET, 1, [], [])
    s.propose("wire_transfer", amount=1_000_000)
    assert s.staged == [] and not s.ledger.steps[-1].ok


def test_memory_rules_match_on_facts():
    memory = PolicyMemory.ephemeral()
    rule = memory.new_rule(
        domain="credit",
        conditions=[
            {"field": "amount", "op": "<=", "value": 100, "label": "the credit is up to ${value}"},
            {"field": "tenure_years", "op": ">=", "value": 2.0, "label": "the customer has {value}+ years"},
        ],
        outcome="approve",
        outcome_label="Approve",
        question="q",
        source_ticket="X-1",
        decided_by="Lead",
    )
    memory.rules.append(rule)
    assert memory.lookup("credit", {"amount": 80, "tenure_years": 3}) is rule
    assert memory.lookup("credit", {"amount": 120, "tenure_years": 3}) is None
    assert memory.lookup("refund", {"amount": 80, "tenure_years": 3}) is None
    assert rule.describe == "Approve when the credit is up to $100 and the customer has 2+ years."
    assert isinstance(PolicyMemory.ephemeral([rule]).rules[0], Rule)
