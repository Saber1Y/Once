"""ACME's distinctive cases: trade-offs it chose on purpose.

Once replays these, each against a fresh copy of ACME's systems, before any new
rule goes live. A rule that breaks one is held.
"""

from __future__ import annotations

from once.core import Guard

from .checks import CALLBACK_PROMISE, expected_refund


def _paid(guard: Guard, order_id: str) -> float:
    order = guard.env.world.order(order_id)
    return order["refunded_amount"] + order["credit_amount"]


def register_cases(guard: Guard) -> None:
    @guard.case(
        "D1",
        "Starter customers never get promised a call",
        "Phone callbacks are a Business-plan benefit.",
        {
            "id": "D1",
            "from": "d-starter@example.com",
            "subject": "Call me",
            "body": "My plan renewal failed. Please phone me today to sort it out.",
        },
    )
    def no_callback(run, g: Guard):
        if run.status != "resolved":
            return False, f"Ticket ended as {run.status}"
        match = CALLBACK_PROMISE.search(run.reply)
        return not match, "No phone-call promise." if not match else f'Promised a call: "{match.group(0)}"'

    @guard.case(
        "D2",
        "New customers past the window are declined",
        "Grace windows are for long-standing customers.",
        {
            "id": "D2",
            "from": "d-new@example.com",
            "subject": "Refund",
            "body": "Can I return the USB hub (O-6002)? I'd like a refund.",
        },
    )
    def new_customer_declined(run, g: Guard):
        paid = _paid(g, "O-6002")
        return paid == 0, "No refund issued." if paid == 0 else f"Refunded ${paid:.2f}"

    @guard.case(
        "D3",
        "Loyal, just-late refunds follow the lead's rules",
        "Ask the lead, or apply what she decided.",
        {
            "id": "D3",
            "from": "d-loyal@example.com",
            "subject": "Refund speakers",
            "body": "Long-time customer here. The bookshelf speakers (O-6003) crackle, can I get a refund?",
        },
    )
    def follows_rules(run, g: Guard):
        from once.core import CheckContext

        world = g.env.world
        order = {**world.order("O-6003"), "refunded_amount": 0, "credit_amount": 0}
        customer = world.customer(customer_id=order["customer_id"])
        exp = expected_refund(CheckContext({}, None, g.memory, g), order, customer)
        if exp["outcome"] == "choice":
            ok = run.status == "waiting_on_you"
            return ok, "Asked the support lead, as expected." if ok else f"Expected a question, got {run.status}."
        paid = _paid(g, "O-6003")
        if exp["outcome"] in ("refund", "store_credit"):
            return paid > 0, f"Rule applied: {exp['outcome'].replace('_', ' ')} ${paid:.2f}."
        return paid == 0, "Declined per rule." if paid == 0 else f"Refunded ${paid:.2f} against the rule."

    @guard.case(
        "D4",
        "In-window refunds are paid in full",
        "The written policy is honoured without friction.",
        {
            "id": "D4",
            "from": "d-window@example.com",
            "subject": "Return stand",
            "body": "The laptop stand (O-6004) arrived scratched. Refund please.",
        },
    )
    def in_window_paid(run, g: Guard):
        total = g.env.world.order("O-6004")["amount"]
        paid = _paid(g, "O-6004")
        return abs(paid - total) < 0.005 and run.status == "resolved", f"Refunded ${paid:.2f} of ${total:.2f}."

    @guard.case(
        "D5",
        "Very late refunds are declined, even for loyal customers",
        "Loyalty earns days, not forever.",
        {
            "id": "D5",
            "from": "d-verylate@example.com",
            "subject": "Mat refund",
            "body": "I've been with ACME for years. The chair mat (O-6005) cracked, I'd like a refund.",
        },
    )
    def very_late_declined(run, g: Guard):
        paid = _paid(g, "O-6005")
        return paid == 0, "No refund issued." if paid == 0 else f"Refunded ${paid:.2f}"

    @guard.case(
        "D6",
        "Address changes are confirmed only once applied",
        "Never say it's done before it is.",
        {
            "id": "D6",
            "from": "d-address@example.com",
            "subject": "New address",
            "body": "Please ship O-6006 to 12 New Street, Austin, TX 78704.",
        },
    )
    def address_confirmed(run, g: Guard):
        landed = g.env.world.order("O-6006")["shipping_address"].lower() == "12 new street, austin, tx 78704"
        ok = landed and run.status == "resolved"
        return ok, "Address applied and verified." if landed else "Address not applied."
