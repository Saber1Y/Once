"""The ACME support agent (the "Act" step of the loop).

It reads a ticket, uses tools against the fixture world and the search index,
proposes actions, and drafts a reply. Proposed actions are staged, not executed:
the loop commits them only after the pre-commit checks pass.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import neatlogs

from once.config import settings
from once.ledger import Ledger
from once.llm import chat
from once.policy import PolicyMemory
from once.world.kb import KnowledgeBase, SearchIndex
from once.world.store import World

MAX_TURNS = 10

SYSTEM_PROMPT = """You are the support agent for ACME, an online store. Today is {today}.

Resolve the customer's ticket end to end:
1. Look up the customer by their email and look up any order they mention.
2. Search the knowledge base for the policy that applies and base your answer on it.
3. Propose the actions that resolve the ticket (refund, store credit, address change).
   Proposed actions are executed by the system right after you send your reply.
4. If the right outcome is a business judgement that no policy covers, call
   request_decision instead of guessing.
5. Finish with the reply email to the customer as plain text (no subject line),
   signed "ACME Support". Be concise and accurate. Never promise anything the
   policy or the customer's plan does not allow.
{rules}{corrections}"""


@dataclass
class Attempt:
    number: int
    ledger: Ledger
    draft: str = ""
    staged: list[dict] = field(default_factory=list)
    decision_request: dict | None = None
    error: str | None = None

    def kb_articles(self) -> list[str]:
        ids: list[str] = []
        for step in self.ledger.find("search_kb"):
            for hit in step.result if isinstance(step.result, list) else []:
                if hit.get("article_id") not in ids:
                    ids.append(hit["article_id"])
        return ids

    def orders_seen(self) -> list[str]:
        ids: list[str] = []
        for step in self.ledger.find("get_order"):
            if step.ok and isinstance(step.result, dict) and step.result.get("id") not in ids:
                ids.append(step.result["id"])
        return ids

    def customer(self) -> dict | None:
        for step in self.ledger.find("lookup_customer"):
            if step.ok:
                return step.result
        return None


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": "Search the ACME help-center knowledge base.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_customer",
            "description": "Look up a customer by email.",
            "parameters": {"type": "object", "properties": {"email": {"type": "string"}}, "required": ["email"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Get an order by id, including days since purchase and refunds.",
            "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_refund",
            "description": "Propose a refund to the original payment method.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "amount": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["order_id", "amount", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_store_credit",
            "description": "Propose store credit instead of a refund.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "amount": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["order_id", "amount", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_address_change",
            "description": "Propose changing an order's shipping address.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}, "new_address": {"type": "string"}},
                "required": ["order_id", "new_address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_decision",
            "description": "Ask the support lead to decide a case that no policy covers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["question", "options"],
            },
        },
    },
]


class SupportAgent:
    def __init__(self, world: World, index: SearchIndex, kb: KnowledgeBase, memory: PolicyMemory) -> None:
        self.world = world
        self.index = index
        self.kb = kb
        self.memory = memory

    # Tools. Each is its own neatlogs TOOL span.

    @neatlogs.span(kind="TOOL", name="search_kb")
    def search_kb(self, query: str) -> list[dict]:
        return self.index.search(query)

    @neatlogs.span(kind="TOOL", name="lookup_customer")
    def lookup_customer(self, email: str) -> dict:
        return self.world.customer(email=email)

    @neatlogs.span(kind="TOOL", name="get_order")
    def get_order(self, order_id: str) -> dict:
        return self.world.order(order_id)

    def _stage(self, attempt: Attempt, action: dict) -> dict:
        self.world.order(action["order_id"])  # validate the order exists
        attempt.staged.append(action)
        return {"status": "proposed", **action}

    @neatlogs.span(kind="TOOL", name="propose_action")
    def propose(self, attempt: Attempt, action: dict) -> dict:
        return self._stage(attempt, action)

    @neatlogs.span(kind="TOOL", name="request_decision")
    def request_decision(self, attempt: Attempt, question: str, options: list[str]) -> dict:
        attempt.decision_request = {"question": question, "options": options}
        return {"status": "sent_to_support_lead"}

    def _dispatch(self, attempt: Attempt, name: str, args: dict) -> Any:
        if name == "search_kb":
            return self.search_kb(args.get("query", ""))
        if name == "lookup_customer":
            return self.lookup_customer(args.get("email", ""))
        if name == "get_order":
            return self.get_order(args.get("order_id", ""))
        if name == "propose_refund":
            return self.propose(
                attempt,
                {
                    "type": "refund",
                    "order_id": args.get("order_id", ""),
                    "amount": float(args.get("amount", 0)),
                    "reason": args.get("reason", ""),
                },
            )
        if name == "propose_store_credit":
            return self.propose(
                attempt,
                {
                    "type": "store_credit",
                    "order_id": args.get("order_id", ""),
                    "amount": float(args.get("amount", 0)),
                    "reason": args.get("reason", ""),
                },
            )
        if name == "propose_address_change":
            return self.propose(
                attempt,
                {
                    "type": "address_change",
                    "order_id": args.get("order_id", ""),
                    "new_address": args.get("new_address", ""),
                },
            )
        if name == "request_decision":
            return self.request_decision(attempt, args.get("question", ""), list(args.get("options", [])))
        raise ValueError(f"Unknown tool {name}")

    @neatlogs.span(kind="CHAIN", name="redraft_reply")
    def redraft(self, ticket: dict, draft: str, facts: list[str]) -> str:
        """Rewrite a reply after actions were committed, using only verified facts."""
        lines = "\n".join(f"- {f}" for f in facts)
        message = chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You rewrite ACME support replies so every statement is true. Keep the tone and "
                        'length, change only what the verified facts contradict, and sign "ACME Support". '
                        "Return only the reply text."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Ticket from {ticket['from']}: {ticket['body']}\n\nDraft reply:\n{draft}\n\n"
                        f"Verified facts (these override the draft):\n{lines}"
                    ),
                },
            ],
            model=settings.model,
        )
        return (message.content or "").strip()

    # The agent loop.

    def run(self, ticket: dict, number: int, corrections: list[str]) -> Attempt:
        attempt = Attempt(number=number, ledger=Ledger(prefix=f"a{number}"))
        return self._run(ticket, attempt, corrections)

    @neatlogs.span(kind="AGENT", name="support_agent", role="ACME support agent", goal="Resolve the ticket accurately")
    def _run(self, ticket: dict, attempt: Attempt, corrections: list[str]) -> Attempt:
        rules = ""
        if self.memory.active():
            lines = "\n".join(f"- {r.describe()}" for r in self.memory.active())
            rules = f"\nDecisions the support lead has already made (follow them):\n{lines}\n"
        fixes = ""
        if corrections:
            lines = "\n".join(f"- {c}" for c in corrections)
            fixes = f"\nCorrections from review of your previous attempt (must follow):\n{lines}\n"
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(today=self.world.today.isoformat(), rules=rules, corrections=fixes),
            },
            {
                "role": "user",
                "content": (
                    f"Ticket {ticket['id']} from {ticket['from']}\nSubject: {ticket['subject']}\n\n{ticket['body']}"
                ),
            },
        ]
        for _ in range(MAX_TURNS):
            message = chat(messages, tools=TOOLS, model=settings.model)
            calls = message.tool_calls or []
            messages.append(message.model_dump(exclude_none=True))
            if not calls:
                attempt.draft = (message.content or "").strip()
                return attempt
            for call in calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = attempt.ledger.record(
                    "tool",
                    call.function.name,
                    args,
                    lambda c=call, a=args: self._dispatch(attempt, c.function.name, a),
                )
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)})
        attempt.error = "The agent did not finish within the turn limit."
        return attempt
