"""Command line: serve the console, run the demo queue headless, drift, repeat runs."""

from __future__ import annotations

import argparse
import json
import os
import sys

VERBOSE = os.getenv("ONCE_VERBOSE") == "1"


def _print_run(run) -> None:
    print(f"\n== {run.ticket_id}: {run.status}  trace={run.trace_id or '-'}")
    for attempt in run.attempts:
        codes = ", ".join(f["code"] for f in attempt["findings"]) or "clean"
        print(f"   attempt {attempt['number']}: {codes}")
        if VERBOSE:
            for step in attempt["steps"]:
                print(f"      {step['id']} {step['name']} {json.dumps(step['args'])[:90]} ok={step['ok']}")
            print(f"      draft: {attempt['draft'][:300]!r}")
        for f in attempt.get("post_commit", []):
            print(f"   after commit: {f['code']}")
    for fix in run.fixes:
        mark = "verified" if fix.get("verified") else "unverified"
        print(f"   fix [{mark}]: {fix['action']}")
    if run.applied_rule:
        print(f"   applied remembered rule {run.applied_rule}")
    if run.choice:
        print(f"   ASK: {run.choice['finding']['detail']}")
    if run.error:
        print(f"   error: {run.error}")
    if run.reply:
        print("   reply: " + run.reply.replace("\n", "\n          "))


def cmd_serve(args) -> None:
    import uvicorn

    uvicorn.run("once.api:app", host=args.host, port=args.port, reload=False)


def cmd_kb(_args) -> None:
    from once.policy import refund_window_days
    from once.world.kb import KnowledgeBase

    kb = KnowledgeBase()
    for article in kb.all():
        print(json.dumps(article.summary()))
    print("current refund window:", refund_window_days(kb))


def cmd_demo(args) -> None:
    from once.loop import Loop
    from once.policy import PolicyMemory
    from once.tracing import flush, init_tracing
    from once.world.kb import KnowledgeBase, SearchIndex
    from once.world.store import World

    init_tracing()
    kb = KnowledgeBase()
    world, index = World.seeded(), SearchIndex(kb)
    memory = PolicyMemory.ephemeral()
    tickets = json.load(open("data/tickets.json"))["queue"]
    if args.ticket:
        tickets = [t for t in tickets if t["id"] in args.ticket]
    loop = Loop(world, kb, index, memory)
    for ticket in tickets:
        _print_run(loop.resolve(ticket))
    flush()


def cmd_repeat(args) -> None:
    """Run one ticket N times on a fresh, stale-seeded index; report appear/caught rates."""
    from once.loop import Loop
    from once.policy import PolicyMemory
    from once.tracing import flush, init_tracing
    from once.world.kb import KnowledgeBase, SearchIndex
    from once.world.store import World

    init_tracing()
    kb = KnowledgeBase()
    ticket = next(t for t in json.load(open("data/tickets.json"))["queue"] if t["id"] == args.ticket)
    appeared = caught = clean_final = 0
    for i in range(args.n):
        loop = Loop(World.seeded(), kb, SearchIndex(kb), PolicyMemory.ephemeral())
        run = loop.resolve(ticket)
        first = {f["code"] for f in run.attempts[0]["findings"]} if run.attempts else set()
        hit = bool(first & {"stale_source", "wrong_window", "wrong_outcome"})
        appeared += hit
        caught += hit and run.status == "resolved"
        clean_final += run.status == "resolved"
        print(f"run {i + 1}: first-attempt findings={sorted(first) or 'clean'} final={run.status}")
    print(
        f"\nfailure appeared {appeared}/{args.n}; caught and fixed {caught}/{appeared}; resolved {clean_final}/{args.n}"
    )
    flush()


def cmd_drift(_args) -> None:
    from once.drift import run_drift
    from once.policy import PolicyMemory
    from once.tracing import flush, init_tracing

    init_tracing()
    summary = run_drift(PolicyMemory())
    for r in summary["results"]:
        print(f"{'PASS' if r['passed'] else 'FAIL'} {r['id']} {r['title']}: {r['detail']}")
    print(f"\n{summary['passed']}/{summary['total']} distinctive cases hold")
    flush()
    sys.exit(0 if summary["passed"] == summary["total"] else 1)


def main() -> None:
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "neatlogs"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="once")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="Run the API and console")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.set_defaults(fn=cmd_serve)
    sub.add_parser("kb", help="Show the live knowledge base as Once sees it").set_defaults(fn=cmd_kb)
    demo = sub.add_parser("demo", help="Run the seeded queue headless")
    demo.add_argument("ticket", nargs="*")
    demo.set_defaults(fn=cmd_demo)
    repeat = sub.add_parser("repeat", help="Repeat one ticket and report catch rate")
    repeat.add_argument("ticket", nargs="?", default="T-102")
    repeat.add_argument("-n", type=int, default=10)
    repeat.set_defaults(fn=cmd_repeat)
    sub.add_parser("drift", help="Run the distinctive-case drift check").set_defaults(fn=cmd_drift)
    args = parser.parse_args()
    args.fn(args)
