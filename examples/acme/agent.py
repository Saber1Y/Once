"""ACME's support agent.

This is ACME's code, not Once's. The only Once-specific part is that tools go
through the ``Session``: reads with ``session.call``, writes with
``session.propose`` (staged until Once's checks pass), and human decisions with
``session.ask``.
"""

from __future__ import annotations

import json
from typing import Any

from once.core import Session
from once.llm import chat

MAX_TURNS = 10

SYSTEM_PROMPT = """You are the support agent for ACME, an online store. Today is {today}.

Resolve the customer's ticket end to end:
1. Look up the customer by their email and look up any order they mention.
2. Search the knowledge base for the policy that applies and base your answer on it.
3. Propose the actions that resolve the ticket (refund, store credit, address change).
   Proposed actions are executed by the system right after you send your reply.
4. Address changes on unshipped orders, password help and billing questions are
   routine: handle them yourself. If a refund falls outside the written policy and
   the right outcome is a business judgement, call request_decision instead of guessing.
5. Finish with the reply email to the customer as plain text (no subject line),
   signed "ACME Support". Be concise and accurate. Never promise anything the
   policy or the customer's plan does not allow.
{rules}{guidance}"""

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


def run_agent(session: Session, env) -> None:
    """ACME's agent loop: model + tools, until it writes the reply."""
    rules = ""
    if session.rules:
        rules = "\nDecisions the support lead has already made (follow them):\n" + "\n".join(
            f"- {r}" for r in session.rules
        )
    guidance = ""
    if session.guidance:
        guidance = "\nCorrections from review of your previous attempt (must follow):\n" + "\n".join(
            f"- {g}" for g in session.guidance
        )
    ticket = session.ticket
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(today=env.world.today.isoformat(), rules=rules, guidance=guidance),
        },
        {
            "role": "user",
            "content": f"Ticket {ticket['id']} from {ticket['from']}\nSubject: {ticket['subject']}\n\n{ticket['body']}",
        },
    ]
    for _ in range(MAX_TURNS):
        message = chat(messages, tools=TOOLS)
        messages.append(message.model_dump(exclude_none=True))
        if not message.tool_calls:
            session.draft = (message.content or "").strip()
            return
        for call in message.tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = dispatch(session, env, call.function.name, args)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)})
    session.error = "The agent did not finish within the turn limit."


def dispatch(session: Session, env, name: str, args: dict) -> Any:
    if name == "search_kb":
        return session.call("search_kb", lambda: env.index.search(args.get("query", "")), args, kind="source")
    if name == "lookup_customer":
        return session.call("lookup_customer", lambda: env.world.customer(email=args.get("email", "")), args)
    if name == "get_order":
        return session.call("get_order", lambda: env.world.order(args.get("order_id", "")), args)
    if name == "propose_refund":
        return session.propose(
            "refund",
            order_id=args.get("order_id", ""),
            amount=float(args.get("amount", 0)),
            reason=args.get("reason", ""),
        )
    if name == "propose_store_credit":
        return session.propose(
            "store_credit",
            order_id=args.get("order_id", ""),
            amount=float(args.get("amount", 0)),
            reason=args.get("reason", ""),
        )
    if name == "propose_address_change":
        return session.propose(
            "address_change", order_id=args.get("order_id", ""), new_address=args.get("new_address", "")
        )
    if name == "request_decision":
        return session.ask(args.get("question", ""), list(args.get("options", [])))
    return {"error": f"Unknown tool {name}"}
