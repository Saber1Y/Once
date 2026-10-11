# Once

![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)
![Tests](https://img.shields.io/badge/tests-14%20passing-brightgreen)
![Tracing](https://img.shields.io/badge/tracing-neatlogs-blue)
![Loop](https://img.shields.io/badge/loop-act%20%E2%86%92%20check%20%E2%86%92%20fix%20or%20ask%20%E2%86%92%20remember-blueviolet)
![Stack](https://img.shields.io/badge/stack-Python%20SDK%20+%20FastAPI%20+%20React-orange)

**Fixes what's mechanical. Asks what's a choice. Only needs you once.**

AI agents that take actions fail quietly: they confirm writes that never landed, answer from outdated policy, and promise things the customer's plan doesn't include.
Self-healing loops that auto-fix everything make it worse, because they slowly erase the trade-offs that make a company distinctive.
Once is a reliability layer a company puts its existing agent behind.
It checks every claim and action against the company's real systems, fixes the mechanical failures itself, asks a person only when a failure is really a business choice, and remembers the answer so it never asks twice.

Repo: https://github.com/Saber1Y/Once · Demo company: ACME, the fictional store from neatlogs' own `support-copilot-demo-kb` fixture.

[See it in one command](#see-it-in-one-command) · [Integrate your agent](#integrate-your-agent) · [Architecture](#architecture) · [Honesty table](#whats-real-vs-pending---the-honesty-table) · [The one-flow demo](#the-one-flow-demo)

Built for neatHack 2026 (single track: build an agent that works). MIT licensed.
ACME is a fictional store; nothing here processes real customers or real payments.

## Table of contents

- [See it in one command](#see-it-in-one-command)
- [Screenshots](#screenshots)
- [The one rule](#the-one-rule)
- [Integrate your agent](#integrate-your-agent)
- [What Once does](#what-once-does)
  - [Check](#check)
  - [Fix what's mechanical](#fix-whats-mechanical)
  - [Ask what's a choice](#ask-whats-a-choice)
  - [Remember](#remember)
  - [Guard against drift](#guard-against-drift)
- [Architecture](#architecture)
- [Component by component](#component-by-component)
- [Safety, enforced in code](#safety-enforced-in-code)
- [How it uses neatlogs, Entire and cfo.ai](#how-it-uses-neatlogs-entire-and-cfoai)
- [Engineering decisions & the hard problems](#engineering-decisions--the-hard-problems)
- [What's real vs pending - the honesty table](#whats-real-vs-pending---the-honesty-table)
- [Tests](#tests)
- [Run it locally](#run-it-locally)
- [The one-flow demo](#the-one-flow-demo)
- [Configuration](#configuration)
- [Project layout](#project-layout)
- [Tech stack, credits, roadmap](#tech-stack-credits-roadmap)
- [Disclaimer & license](#disclaimer--license)

## See it in one command

```bash
cd Once && cp .env.example .env  # add your model key and neatlogs key
make install && make serve       # console on http://127.0.0.1:8787
```

```bash
cd Once && make dev  # optional: Vite dev server on :5173, proxies /api to :8787
```

Open **Integration** to see how ACME plugs its agent in, then open the **ACME desk** and press **Run queue**.
Two tickets fail on purpose and get fixed, one stops and asks you, and a later one is resolved with your answer without asking again.

## Screenshots

The demo video shows the console live.
The first traced run, with trace ids, drift results and the held rule, is written up in [docs/evidence/live-run-2026-10-11.md](docs/evidence/live-run-2026-10-11.md), and every claim maps to evidence in [claims.yaml](claims.yaml).

## The one rule

**Nothing reaches the customer, and nothing irreversible happens, until it has been checked against what is actually true.**

1. *Staged actions.* The agent proposes writes; Once commits them only after the pre-commit checks pass.
2. *Read-back verification.* After commit, every write is read back from the system of record. "Accepted" is not "done".
3. *Current truth, not retrieved truth.* Policy checks use the live help center and follow superseded-by links, never whatever the agent happened to retrieve.

## Integrate your agent

A company integrates in one file.
This is ACME's, abridged from [examples/acme/integration.py](examples/acme/integration.py):

```python
from once import Guard, PolicyMemory

def create_guard(memory: PolicyMemory, env=None) -> Guard:
    guard = Guard("ACME", memory, config=CONFIG)

    # 1. The help center, so Once can tell current articles from outdated ones.
    guard.sources = HelpCenterSources(env.kb, env.index)

    # 2. ACME's existing agent. Its tools go through a Once session.
    guard.agent(lambda session: run_agent(session, env))

    # 3. Every write the agent may propose, with a read-back from the order system.
    @guard.action("address_change", verify=address_landed, validate=order_exists)
    def address_change(order_id: str, new_address: str) -> dict:
        return env.world.request_address_change(order_id, new_address)

    # 4. ACME's business checks.
    guard.check(refund_policy)
    guard.check(plan_promises)

    # 5. Trade-offs ACME chose on purpose, replayed before any new rule goes live.
    register_cases(guard)
    return guard
```

Inside the agent, the only Once-specific code is how tools are called:

```python
session.call("search_kb", lambda: index.search(query), {"query": query}, kind="source")  # read
session.propose("refund", order_id="O-5002", amount=249.0, reason="fit")                # staged write
session.ask("Refund a loyal customer 2 days late?", ["Refund", "Decline"])               # human decision
```

Point Once at an integration with `ONCE_INTEGRATION=acme.integration` (the default).
The console's **Integration** screen shows the connected company, its systems, its writes and read-backs, its checks, its distinctive cases and its source files.

## What Once does

### Check

| Check | Owner | Catches | Category |
| --- | --- | --- | --- |
| `outdated_source` | Once | The answer rests on a help-center article marked outdated | context |
| `side_effect_missing` | Once | A write was accepted but reading it back shows it never landed | execution |
| `unsupported_amount` | Once | The reply states an amount no tool returned | context |
| `needless_escalation` | Once | The agent asked a person about something no check calls a choice, or a remembered rule covers | trajectory |
| `no_reply` | Once | The agent crashed or never finished | trajectory |
| tier-2 judge | Once | Unsupported specifics, only when nothing deterministic fired | context |
| `refund_policy` | ACME | Refunds against the current policy, remembered rules and ACME's choice boundary | decision |
| `plan_promises` | ACME | A phone call promised to a Starter-plan customer | decision |

Categories are the four clusters from neatlogs' [How to read a trace](https://neatlogs.com/blog/how-to-read-a-trace).
Deterministic checks decide almost everything; the model judge grades the fewest traces, as neatlogs argues [here](https://neatlogs.com/blog/your-strongest-llm-judge-should-grade-the-fewest-traces).

### Fix what's mechanical

- Outdated source: Once repairs the company's search index through `sources.repair`, so later tickets don't hit it either.
- Write that didn't land: Once retries, reads it back with the action's `verify`, and rewrites the reply from verified facts.
- Anything else a check flags: the check supplies a precise `correction` and Once re-runs the agent before anything is committed.

A fix counts as verified only when the re-run passes the checks that failed, or the write reads back correctly.

### Ask what's a choice

A check returns a `Choice`: a question, the facts, the options, and a suggested rule scope.
Once pauses the ticket and shows the decision-maker a plain-language card with only the trace steps that matter.

### Remember

Answers become versioned rules over facts, for example `refund_exception: tenure_years >= 2 and days_over <= 7 -> refund`, stored per company in `data/tenants/<company>/policies.json` (and `.yaml`).
Checks call `memory.lookup(domain, facts)` first, so the next matching ticket is resolved without asking.

### Guard against drift

Before a rule is saved, Once replays the company's distinctive cases, each against a fresh copy of its systems.
A rule that breaks one (for example "refund anyone, any time") is held, with the failing cases shown on the card.

## Architecture

Two decisions shape everything:

1. **The product and the customer are separate.** `src/once` is the layer; `examples/acme` is a company integrating it.
2. **Checks trust the system of record, not the agent**: the live help center for policy, the order system for writes.

```mermaid
flowchart LR
    T[Ticket] --> A[Company's agent<br/>via Session]
    A --> C{Checks<br/>built-in + company}
    C -- mechanical --> F[Fix cause<br/>re-run]
    F --> A
    C -- choice --> Q[Ask the decision-maker]
    Q --> D{Drift check<br/>distinctive cases}
    D -- holds --> M[Remember rule]
    D -- breaks --> H[Hold rule]
    M --> A
    C -- clean --> K[Commit writes]
    K --> V{Read back}
    V -- missing --> R[Retry + rewrite<br/>from facts]
    V -- ok --> S[Send reply]
    R --> S
```

| Tier | Runs | Can it move money? | Responsibility |
| --- | --- | --- | --- |
| Company agent | Its own model and prompts | No, it only proposes | Resolve the ticket |
| Checks | Deterministic code, tier-2 judge rarely | No | Decide what's true |
| Loop | Worker thread | Yes, through the company's registered actions, after checks pass | Commit, verify, fix, route |
| Desk / API | FastAPI | No | Queue, decisions, integration view, events |
| Console | React | No | Show the loop, collect decisions |

## Component by component

| Module | Responsibility |
| --- | --- |
| `src/once/core.py` | The SDK: `Guard`, `Session`, `Finding`, `Choice` |
| `src/once/checks.py` | Built-in checks and the check runner |
| `src/once/loop.py` | Act, check, fix, ask, commit, verify |
| `src/once/memory.py` | Versioned rules over facts |
| `src/once/drift.py` | Parallel replay of a company's distinctive cases |
| `src/once/integrations.py` | Loads a company's integration module |
| `src/once/desk.py` / `api.py` | Worker, decisions, REST + server-sent events |
| `src/once/tracing.py` / `llm.py` | neatlogs wiring, rate-limited OpenAI-compatible client |
| `examples/acme/integration.py` | ACME's integration: the five steps |
| `examples/acme/agent.py` | ACME's own support agent |
| `examples/acme/checks.py` / `cases.py` | ACME's business checks and distinctive cases |
| `examples/acme/world.py` / `helpcenter.py` | ACME's order system (fixture) and help center (live neatlogs fixture) |
| `web/src` | Console: desk, decision cards, policy memory, drift board, integration screen |

## Safety, enforced in code

| Claim | How it's enforced |
| --- | --- |
| The agent can't run arbitrary writes | Only actions registered with `@guard.action` can be staged; others are rejected |
| No wrong refund is committed | Writes are staged; `refund_policy` re-runs the agent before commit |
| No "done" for undone work | Every action's `verify` reads the write back; replies are rewritten from verified facts |
| No outdated policy | Every source the agent used is checked against its live status |
| Refunds can't exceed the order | ACME's order system rejects amounts above the refundable balance |
| Rules can't silently erode trade-offs | Candidate rules run the drift check and are held on any failure |

## How it uses neatlogs, Entire and cfo.ai

- **neatlogs:** every ticket is a `WORKFLOW` trace with the company agent as an `AGENT` span, tools as `TOOL` spans, Once's checks and fixes as `CHAIN` spans, and LLM calls auto-captured via `neatlogs.wrap`. The product answers neatlogs' stated open problems: [seeing isn't fixing](https://neatlogs.com/manifesto), [self-healing is self-defeating](https://neatlogs.com/blog/self-healing-is-self-defeating), and the detection gap where an agent "confirmed an update after the write failed".
- **Entire:** checkpoints capture the Claude Code sessions that built Once and are pushed with each commit.
- **cfo.ai:** the business plan (price per verified resolution, inference cost, margin) lives in `docs/business-plan.md`.

## Engineering decisions & the hard problems

**The layer has to be honest about what it can't know.**
Once can't know a company's refund policy, so business rules are the company's checks; Once supplies the loop, the generic checks, the memory and the drift replay.

**Async writes make the lie realistic.**
ACME's address service returns `accepted` and applies the change in a background job, like many real APIs.
An injected fault makes the first job fail, so the agent's natural "your address is updated" becomes a false claim that only read-back can catch.

**The stale policy is the one neatlogs built.**
Their demo seeds retrieval with the outdated 30-day policy to manufacture a regression.
ACME's index does the same, and Once catches it by checking the live page's own status instead of trusting retrieval.

**Rules are facts, not prose.**
A remembered decision is a set of conditions over facts the check provides, so it matches deterministically and can be replayed against distinctive cases before it goes live.

## What's real vs pending - the honesty table

| Capability | Status |
| --- | --- |
| Once SDK, checks, loop, memory, drift | Real - unit-tested against a toy company and against ACME |
| ACME help center | Real - live neatlogs fixture pages, cached for offline runs |
| ACME orders, customers, refunds | Fixture data in SQLite, labelled as such |
| Failed address write on T-101 and D6 | Injected fault, labelled in the console |
| Model calls, checks, fixes, decisions, drift | Real on every run |
| neatlogs trace export | Real when `NEATLOGS_API_KEY` is set; otherwise spans stay local and the console says so |
| End-to-end run with a real model | Real - Gemini via its OpenAI-compatible endpoint, traced in neatlogs ([evidence](docs/evidence/live-run-2026-10-11.md)) |
| Entire checkpoints | Real - enabled on the repo, checkpoints pushed with commits |
| neatlogs trace deep links | Not yet established - dashboard route is configurable via `NEATLOGS_TRACE_URL` |
| Trace readback via Public API | Not yet established - planned behind `NEATLOGS_TOKEN` |
| Real helpdesk and commerce connectors | Not yet established - ACME's systems are fixtures |
| Run against the neatHack LiteLLM proxy | Not yet established - same code path, pending the team key |

Tier-2 judge rewrites are recorded as unverified fixes, because nothing independently re-checks the judge's own claim.

## Tests

| Suite | Tests | Covers |
| --- | --- | --- |
| `tests/test_once.py` | 6 | Built-in checks, choice routing, read-back, unregistered actions, fact-based memory, against a toy company |
| `tests/test_acme.py` | 8 | ACME's help center, order system, refund policy, choice-then-rule, plan promises, failed address write |

```bash
cd Once && make test  # pytest
cd Once && make lint  # ruff, eslint, tsc
```

Live-model checks: `make demo` (headless queue), `make drift` (distinctive cases), `make repeat` (stale-policy appear and catch rate over 10 runs).

## Run it locally

### 1. Backend

```bash
cd Once
uv sync
cp .env.example .env  # fill in keys
uv run once kb        # sanity check: ACME's help center as Once sees it
uv run once serve     # http://127.0.0.1:8787
```

### 2. Console

```bash
cd Once/web
npm ci
npm run build  # served by the backend, or:
npm run dev    # http://localhost:5173
```

### 3. Headless

```bash
cd Once
uv run once demo T-101 T-102  # run selected tickets and print the loop
uv run once drift             # replay ACME's distinctive cases
```

## The one-flow demo

1. Open **Integration**: ACME is connected; the five steps are highlighted in `integration.py`.
2. Open the **ACME desk** and press **Run queue**.
3. T-101: ACME's agent drafts "address updated"; read-back shows the write failed (injected fault); Once retries, verifies, and rewrites the reply.
4. T-102: the agent answers from the outdated 30-day policy and proposes a $249 refund; Once blocks it, repairs the index, and re-runs with the current 14-day policy.
5. T-103: a four-year customer two days past the window; Once asks you.
6. Answer "Refund in full", make it a rule; the drift check replays six cases and saves rule v1.
7. T-109: a three-year customer four days late; resolved with your rule, no question asked.
8. Optional: answer a decision with a too-broad rule (0 years, 30 days) and watch the drift check hold it.

## Configuration

| Variable | Purpose |
| --- | --- |
| `ONCE_INTEGRATION` | Integration module (default `acme.integration`) |
| `LLM_BASE_URL` | OpenAI-compatible endpoint (LiteLLM proxy, Gemini, ...) |
| `LLM_API_KEY` | Model key |
| `ONCE_MODEL` | Model for the agent and rewrites |
| `ONCE_JUDGE_MODEL` | Cheaper model for the tier-2 judge (defaults to `ONCE_MODEL`) |
| `LLM_RPM` | Client-side requests per minute per model (0 = unlimited) |
| `NEATLOGS_API_KEY` | neatlogs project key; without it traces stay local |
| `NEATLOGS_TRACE_URL` | Optional trace link template, e.g. `https://app.neatlogs.com/...{trace_id}` |

## Project layout

```text
Once/
├── src/once/             # THE PRODUCT
│   ├── core.py           # SDK: Guard, Session, Finding, Choice
│   ├── checks.py         # built-in checks
│   ├── loop.py           # act, check, fix, ask, commit, verify
│   ├── memory.py         # rules over facts
│   ├── drift.py          # distinctive-case replay
│   ├── integrations.py   # load a company's integration
│   ├── desk.py, api.py   # worker, decisions, HTTP + SSE
│   └── tracing.py, llm.py
├── examples/acme/        # A CUSTOMER
│   ├── integration.py    # the five-step integration
│   ├── once.yaml         # ACME's config and choice boundary
│   ├── agent.py          # ACME's own agent
│   ├── checks.py, cases.py
│   ├── world.py, helpcenter.py
│   └── data/             # fixture orders, faults, demo tickets
├── tests/                # product tests + ACME tests
├── docs/                 # PRD, evidence
└── web/                  # React console
```

## Tech stack, credits, roadmap

### Tech stack

Python 3.13, neatlogs SDK, OpenAI SDK (any OpenAI-compatible endpoint), FastAPI, SQLite, React 19, Vite, Tailwind CSS 4, Motion, Phosphor icons.

### Credits

The ACME help center is neatlogs' public `support-copilot-demo-kb` fixture.
The failure taxonomy and the "ask once, remember" loop follow ideas neatlogs published on their blog.

### Roadmap

- Design partners: support teams already running an AI agent, with Shopify, Stripe and Zendesk connectors.
- A decision inbox in Slack and Teams, so decision-makers never open a dashboard.
- A TypeScript SDK and helpdesk marketplace apps.
- Beyond support: finance ops, IT helpdesk and any agent that issues refunds, credits, access or orders.
- Trace readback through the neatlogs Public API as the verification source.

## Disclaimer & license

Once is a hackathon project; the demo company ACME runs on fixture data, and nothing here processes real customers, orders or payments or gives legal or financial advice.

**MIT License.**
