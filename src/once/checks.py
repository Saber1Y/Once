"""Built-in checks, the same for every company, plus the runner for integrator checks.

Built-in (no configuration needed):

* ``outdated_source``      the answer rests on a help-center article marked outdated
* ``side_effect_missing``  a write was accepted but reading it back shows it never landed
* ``unsupported_amount``   the reply states an amount no tool returned
* ``needless_escalation``  the agent asked a person about something no check calls a choice
* ``no_reply``             the agent crashed or never finished

Deterministic checks decide almost everything. The tier-2 judge runs only when
nothing deterministic fired and the reply contains specifics worth checking.
"""

from __future__ import annotations

import json
import re

import neatlogs

from once.config import settings
from once.core import CheckContext, Finding, Session

SUCCESS_CLAIM = re.compile(
    r"\b(updated|changed|corrected|processed|issued|refunded|completed|applied|has been|have been|is now)\b", re.I
)
DOLLARS = re.compile(r"\$\s?(\d[\d,]*(?:\.\d{2})?)")
NUMBERED_FACT = re.compile(r"\b\d+[- ](?:days?|hours?|business days)\b", re.I)
_STOP = {"the", "a", "an", "to", "of", "and", "or", "your", "how", "for", "plan", "policy", "article"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _STOP}


def outdated_sources(ctx: CheckContext) -> list[Finding]:
    sources = ctx.guard.sources
    if not sources:
        return []
    ticket_words = _words(ctx.ticket["subject"] + " " + ctx.ticket["body"])
    findings, seen = [], set()
    for step in ctx.session.steps(kind="source"):
        hits = step.result if isinstance(step.result, list) else [step.result]
        for hit in hits:
            article_id = hit.get("article_id") if isinstance(hit, dict) else None
            if not article_id or article_id in seen:
                continue
            seen.add(article_id)
            status, superseded_by = sources.status(article_id)
            if status != "outdated":
                continue
            quoted = any(
                f.lower() in ctx.session.draft.lower() for f in NUMBERED_FACT.findall(sources.body(article_id))
            )
            relevant = bool(_words(sources.title(article_id)) & ticket_words)
            if not (quoted or relevant):
                continue
            findings.append(
                Finding(
                    "outdated_source",
                    "context",
                    "mechanical",
                    "Answered from an outdated article",
                    f"The agent used '{sources.title(article_id)}' ({article_id}). The live help center marks it "
                    f"outdated and superseded by {superseded_by}.",
                    evidence=[step.id],
                    data={"stale": article_id, "current": superseded_by},
                )
            )
    return findings


def unsupported_amounts(session: Session) -> list[Finding]:
    known: set[float] = set()
    for step in session.ledger.steps:
        if step.ok:
            for match in re.findall(r"\d+(?:\.\d+)?", json.dumps(step.result, default=str)):
                known.add(round(float(match), 2))
    for action in session.staged:
        for value in action.values():
            if isinstance(value, int | float):
                known.add(round(float(value), 2))
    claimed = {round(float(m.replace(",", "")), 2) for m in DOLLARS.findall(session.draft)}
    unknown = sorted(claimed - known)
    if not unknown:
        return []
    return [
        Finding(
            "unsupported_amount",
            "context",
            "mechanical",
            "Stated an amount no tool returned",
            f"The reply mentions ${unknown[0]:.2f}, which no tool result or proposed action contains.",
            data={"amount": unknown[0]},
            correction=f"Do not mention ${unknown[0]:.2f}; only state amounts the tools returned.",
        )
    ]


@neatlogs.span(kind="CHAIN", name="check_before_commit")
def before_commit(ctx: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    for spec in ctx.guard.checks:
        for finding in spec.fn(ctx):
            finding.source = spec.name
            findings.append(finding)
    findings = outdated_sources(ctx) + findings
    if ctx.session.decision_request and not any(f.route == "choice" for f in findings):
        covered = next((f for f in findings if f.data.get("rule_id")), None)
        findings.append(
            Finding(
                "needless_escalation",
                "trajectory",
                "mechanical",
                "Asked a person about something already decided" if covered else "Escalated a routine request",
                "The agent asked the support lead, but "
                + (
                    "a remembered rule already covers this case."
                    if covered
                    else f"none of {ctx.guard.company}'s checks treat this as a business decision."
                ),
                evidence=[s.id for s in ctx.session.steps("request_decision")],
                correction="Do not ask for a decision; resolve the ticket yourself"
                + (" using the remembered rule." if covered else "."),
            )
        )
    findings += unsupported_amounts(ctx.session)
    if ctx.session.error:
        findings.append(
            Finding(
                "no_reply",
                "trajectory",
                "mechanical",
                "The agent did not finish",
                ctx.session.error,
                correction="Finish with the reply to the customer.",
            )
        )
    return findings


@neatlogs.span(kind="CHAIN", name="verify_after_commit")
def after_commit(ctx: CheckContext, commits: list[dict]) -> list[Finding]:
    findings = []
    for commit in commits:
        spec = ctx.guard.actions[commit["action"]["type"]]
        if not commit["ok"]:
            findings.append(
                Finding(
                    "commit_failed",
                    "execution",
                    "mechanical",
                    f"The {spec.name.replace('_', ' ')} didn't go through",
                    str(commit["result"]),
                    evidence=[commit["step_id"]],
                    data={"action": commit["action"]},
                )
            )
            continue
        if not spec.verify:
            continue
        landed, detail = spec.verify(commit["action"], commit["result"])
        if landed:
            continue
        claimed = bool(SUCCESS_CLAIM.search(ctx.session.draft))
        findings.append(
            Finding(
                "side_effect_missing",
                "execution",
                "mechanical",
                "Would have confirmed a write that failed" if claimed else "A write didn't land",
                f"The {spec.name.replace('_', ' ')} was accepted, but reading it back shows it did not land: {detail}"
                + (" The draft tells the customer it's done." if claimed else ""),
                evidence=[commit["step_id"]],
                data={"action": commit["action"], "claimed_success": claimed, "detail": detail},
            )
        )
    return findings


def needs_judge(session: Session, findings: list[Finding]) -> bool:
    return not findings and bool(settings.judge_model) and bool(re.search(r"\d", session.draft))


@neatlogs.span(kind="CHAIN", name="tier2_judge")
def judge(session: Session) -> list[Finding]:
    from once.llm import chat

    evidence = [s.to_dict() for s in session.ledger.steps]
    prompt = (
        "You check a customer-support reply against the tool results it was based on.\n"
        "List statements in the reply that state a specific fact (number, date, status, "
        "timeframe) that the tool results do not support. Generic courtesy is fine.\n"
        'Return JSON: {"unsupported": [{"quote": "...", "why": "..."}]}\n\n'
        f"TOOL RESULTS:\n{json.dumps(evidence, default=str)[:12000]}\n\nREPLY:\n{session.draft}"
    )
    message = chat([{"role": "user", "content": prompt}], model=settings.judge_model, json_mode=True)
    try:
        items = json.loads(message.content or "{}").get("unsupported", [])
    except json.JSONDecodeError:
        return []
    return [
        Finding(
            "unsupported_claim",
            "context",
            "mechanical",
            "Stated something no tool returned",
            f'"{i.get("quote", "")}": {i.get("why", "")}',
            data={"quote": i.get("quote", "")},
            tier="judge",
        )
        for i in items[:3]
        if i.get("quote")
    ]
