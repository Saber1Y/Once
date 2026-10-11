"""How ACME puts its existing support agent behind Once.

This is the whole integration: point Once at the help center, hand it the agent,
register each write with a read-back, add ACME's business checks, and list the
trade-offs ACME never wants to lose.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from once import Guard, PolicyMemory

from .agent import run_agent
from .cases import register_cases
from .checks import plan_promises, refund_policy
from .helpcenter import HelpCenterSources, KnowledgeBase, SearchIndex
from .world import World

CONFIG = yaml.safe_load((Path(__file__).parent / "once.yaml").read_text())


@dataclass
class AcmeEnv:
    """ACME's own systems. Drift replays get a fresh copy, so they never touch real orders."""

    world: World
    kb: KnowledgeBase
    index: SearchIndex

    @classmethod
    def fresh(cls, kb: KnowledgeBase | None = None) -> AcmeEnv:
        kb = kb or KnowledgeBase(CONFIG["help_center"])
        return cls(World.seeded(), kb, SearchIndex(kb))


def create_guard(memory: PolicyMemory, env: AcmeEnv | None = None) -> Guard:
    env = env or AcmeEnv.fresh()
    guard = Guard(CONFIG["company"], memory, config=CONFIG)
    guard.env = env

    # 1. The help center, so Once can tell current articles from outdated ones.
    guard.sources = HelpCenterSources(env.kb, env.index)

    # 2. ACME's existing agent.
    guard.agent(lambda session: run_agent(session, env))

    # 3. Every write the agent may propose, with a read-back from the order system.
    def order_exists(params: dict) -> None:
        env.world.order(params["order_id"])

    def money_landed(action: dict, result: dict) -> tuple[bool, str]:
        order = env.world.order(action["order_id"])
        paid = order["refunded_amount"] + order["credit_amount"]
        return paid >= action["amount"] - 0.005, f"order shows ${paid:.2f} returned"

    def address_landed(action: dict, result: dict) -> tuple[bool, str]:
        job = env.world.address_job(result["job_id"])
        now = env.world.order(action["order_id"])["shipping_address"]
        return now.lower() == action["new_address"].lower(), f"job {job['status']}, order ships to {now}"

    @guard.action("refund", verify=money_landed, validate=order_exists)
    def refund(order_id: str, amount: float, reason: str) -> dict:
        """Refund to the original payment method."""
        return env.world.refund(order_id, amount, reason)

    @guard.action("store_credit", verify=money_landed, validate=order_exists)
    def store_credit(order_id: str, amount: float, reason: str) -> dict:
        """Issue store credit instead of a refund."""
        return env.world.refund(order_id, amount, reason, kind="store_credit")

    @guard.action("address_change", verify=address_landed, validate=order_exists)
    def address_change(order_id: str, new_address: str) -> dict:
        """Change an order's shipping address (applied by a background job)."""
        return env.world.request_address_change(order_id, new_address)

    # 4. ACME's business checks.
    guard.check(refund_policy)
    guard.check(plan_promises)

    # 5. Trade-offs ACME chose on purpose, replayed before any new rule goes live.
    register_cases(guard)
    return guard


def demo_tickets() -> list[dict]:
    import json

    return json.loads((Path(__file__).parent / "data" / "tickets.json").read_text())["queue"]
