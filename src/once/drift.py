"""Drift check: replay ACME's distinctive cases before a new rule goes live.

Each case runs the full loop in its own fresh world, so nothing a replay does
touches the live queue. Assertions encode trade-offs ACME chose on purpose; a
candidate rule that breaks one is held instead of applied.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import neatlogs

from once.loop import Loop, TicketRun
from once.policy import PolicyMemory, expected_refund, refund_window_days
from once.world.kb import KnowledgeBase, SearchIndex
from once.world.store import World


@dataclass
class Case:
    id: str
    title: str
    why: str
    ticket: dict
    check: Callable[[TicketRun, World, PolicyMemory, KnowledgeBase], tuple[bool, str]]


def _refunded(world: World, order_id: str) -> float:
    order = world.order(order_id)
    return order["refunded_amount"] + order["credit_amount"]


def _no_callback(run: TicketRun, world, memory, kb) -> tuple[bool, str]:
    from once.checker import CALLBACK_PROMISE

    if run.status != "resolved":
        return False, f"Ticket ended as {run.status}"
    match = CALLBACK_PROMISE.search(run.reply)
    return (not match, "No phone-call promise." if not match else f'Promised a call: "{match.group(0)}"')


def _no_refund(order_id: str):
    def check(run: TicketRun, world, memory, kb):
        amount = _refunded(world, order_id)
        return amount == 0, "No refund issued." if amount == 0 else f"Refunded ${amount:.2f}"

    return check


def _full_refund(order_id: str):
    def check(run: TicketRun, world, memory, kb):
        order = world.order(order_id)
        amount = _refunded(world, order_id)
        ok = abs(amount - order["amount"]) < 0.005 and run.status == "resolved"
        return ok, f"Refunded ${amount:.2f} of ${order['amount']:.2f}."

    return check


def _follows_rules(order_id: str):
    def check(run: TicketRun, world, memory, kb):
        order = world.order(order_id)
        customer = world.customer(customer_id=order["customer_id"])
        window, _ = refund_window_days(kb)
        exp = expected_refund({**order, "refunded_amount": 0, "credit_amount": 0}, customer, window, memory)
        if exp.outcome == "needs_choice":
            return (
                run.status == "waiting_on_you",
                "Asked the support lead, as expected."
                if run.status == "waiting_on_you"
                else f"Expected a question, got {run.status}.",
            )
        amount = _refunded(world, order_id)
        if exp.outcome in ("refund", "store_credit"):
            return amount > 0, f"Rule applied: {exp.outcome.replace('_', ' ')} ${amount:.2f}."
        return amount == 0, "Declined per rule." if amount == 0 else f"Refunded ${amount:.2f} against the rule."

    return check


def _address_applied(order_id: str, address: str):
    def check(run: TicketRun, world, memory, kb):
        landed = world.order(order_id)["shipping_address"].lower() == address.lower()
        detail = "Address applied and verified." if landed else "Address not applied."
        return landed and run.status == "resolved", detail

    return check


CASES: list[Case] = [
    Case(
        "D1",
        "Starter customers never get promised a call",
        "Phone callbacks are a Business-plan benefit.",
        {
            "id": "D1",
            "from": "d-starter@example.com",
            "subject": "Call me",
            "body": "My plan renewal failed. Please phone me today to sort it out.",
        },
        _no_callback,
    ),
    Case(
        "D2",
        "New customers past the window are declined",
        "Grace windows are for long-standing customers only.",
        {
            "id": "D2",
            "from": "d-new@example.com",
            "subject": "Refund",
            "body": "Can I return the USB hub (O-6002)? I'd like a refund.",
        },
        _no_refund("O-6002"),
    ),
    Case(
        "D3",
        "Loyal, just-late refunds follow the lead's rules",
        "Either ask the lead or apply the rule she already made.",
        {
            "id": "D3",
            "from": "d-loyal@example.com",
            "subject": "Refund speakers",
            "body": "Long-time customer here. The bookshelf speakers (O-6003) crackle, can I get a refund?",
        },
        _follows_rules("O-6003"),
    ),
    Case(
        "D4",
        "In-window refunds are paid in full",
        "The written policy is honoured without friction.",
        {
            "id": "D4",
            "from": "d-window@example.com",
            "subject": "Return stand",
            "body": "The laptop stand (O-6004) arrived scratched. Refund please.",
        },
        _full_refund("O-6004"),
    ),
    Case(
        "D5",
        "Very late refunds are declined, even for loyal customers",
        "Loyalty earns days, not an open-ended window.",
        {
            "id": "D5",
            "from": "d-verylate@example.com",
            "subject": "Mat refund",
            "body": "I've been with ACME for years. The chair mat (O-6005) cracked, I'd like a refund.",
        },
        _no_refund("O-6005"),
    ),
    Case(
        "D6",
        "Address changes are confirmed only once applied",
        "Never tell a customer something is done before it is.",
        {
            "id": "D6",
            "from": "d-address@example.com",
            "subject": "New address",
            "body": "Please ship O-6006 to 12 New Street, Austin, TX 78704.",
        },
        _address_applied("O-6006", "12 New Street, Austin, TX 78704"),
    ),
]


@neatlogs.span(kind="WORKFLOW", name="drift_check")
def run_drift(memory: PolicyMemory, emit=None, cases: list[Case] | None = None) -> dict:
    emit = emit or (lambda *a, **k: None)
    cases = cases or CASES
    emit("drift.started", total=len(cases), rules=[r.describe() for r in memory.active()])

    def one(case: Case) -> dict:
        world = World.seeded()
        kb = KnowledgeBase()
        loop = Loop(world, kb, SearchIndex(kb), PolicyMemory.ephemeral(memory.active()))
        run = loop.resolve(case.ticket)
        try:
            ok, detail = case.check(run, world, loop.memory, kb)
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        result = {
            "id": case.id,
            "title": case.title,
            "why": case.why,
            "passed": ok,
            "detail": detail,
            "status": run.status,
            "trace_url": run.trace_url,
            "fixes": len(run.fixes),
        }
        emit("drift.case", result=result)
        return result

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(one, cases))
    summary = {"passed": sum(r["passed"] for r in results), "total": len(results), "results": results}
    emit("drift.finished", **summary)
    return summary
