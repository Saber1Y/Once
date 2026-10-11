# Once - Product Requirements

Status: v0.1, written 2026-10-11 for neatHack 2026.
Owner: Saber1Y (solo).

## One line

Once is a support agent that fixes what is mechanical, asks about what is a choice, and only needs you once.

## Problem

neatlogs, the hackathon host, has written down the problem in public.

- "Seeing isn't fixing."
  Teams have more traces, evals and dashboards than ever, but making an agent reliable is still a manual loop of finding a failure, recovering context, finding a root cause, fixing it and verifying the fix ([manifesto](https://neatlogs.com/manifesto)).
- Engineering and the business disagree on what success means.
  Their own agent "followed its instructions precisely" and customer support still judged the outcome wrong.
- The people who know the right outcome are "outside the workflow entirely".
- Self-healing loops are self-defeating.
  An agent that auto-fixes every mistake drifts toward generic defaults and erases the trade-offs that make a company distinctive ([blog](https://neatlogs.com/blog/self-healing-is-self-defeating)).
  The proposed fix is "Automate everything that isn't a choice. Ask someone when it is. Remember the answer."
- Detections can flag a failed tool call, but they cannot tell that the agent then claimed success anyway ([blog](https://neatlogs.com/blog/how-to-read-a-trace)).
- Strong LLM judges are too expensive to run on every trace, so cheap checks should handle the clear cases ([blog](https://neatlogs.com/blog/your-strongest-llm-judge-should-grade-the-fewest-traces)).

Once is a working answer to those points, built as a real agent doing a real job.

## Users

- **Maya, support lead at ACME.**
  Knows what the right outcome is for a customer.
  Never reads a trace and never touches code.
- **Dev, the engineer who owns the agent.**
  Wires Once in once and wants evidence that fixes are real.

ACME is the fictional company from neatlogs' own `support-copilot-demo-kb` fixture.
Its help center is live at https://neatlogs.github.io/support-copilot-demo-kb/.

## The job

Once works through a queue of ACME support tickets and resolves each one end to end.
Ticket types: refunds, shipping address changes, billing disputes, and support plan questions.

## The loop (per ticket)

1. **Act.**
   The support agent searches the knowledge base, looks up the customer and order, takes actions (refund, address update) and drafts a reply.
   Every step runs inside a neatlogs trace.
2. **Check.**
   Before anything is sent, every claim in the draft is checked against what the tools actually returned.
   Deterministic checks run first.
   A cheap model runs only when a deterministic check cannot decide.
3. **Classify.**
   Each finding is sorted into the neatlogs failure taxonomy: context, decision, execution, trajectory.
4. **Route.**
   - Mechanical findings (a failed write, bad tool arguments, a stale document with a clear current version, a forbidden promise) are fixed automatically, re-run, and verified.
   - Choices (a case no policy covers, such as a loyal customer just outside the refund window) pause the ticket and go to Maya as a plain-language card with only the relevant trace steps.
5. **Remember.**
   Maya's answer is stored as a versioned policy rule scoped to the facts of the case.
   The next matching ticket is resolved without asking.
6. **Guard.**
   After every new rule or fix, Once replays a set of distinctive cases that encode ACME's chosen trade-offs.
   A change that breaks one is held instead of applied.

## Requirements

### Must have (submission)

- R1. A support agent with tool calling over the ACME fixture world, traced with the neatlogs Python SDK.
- R2. A claim checker that blocks false success claims, stale policy citations, wrong numbers and forbidden promises.
- R3. A failure classifier using the four neatlogs categories.
- R4. Automatic fixes for mechanical findings, each followed by a re-run and a verification step.
- R5. Decision cards for choices, with options and an adjustable rule scope.
- R6. A versioned policy memory that is applied before asking again.
- R7. A drift check over distinctive cases, with a pass count and the ability to hold a change.
- R8. A web console showing the ticket queue, a live loop timeline, decision cards, policy memory, drift results and links to traces.
- R9. A seeded demo queue, a reset button, and `make demo` for judges.
- R10. A `claims.yaml` mapping each product claim to evidence (trace link, test or scripted run).
- R11. Entire enabled on the repository from the first commit.
- R12. A cfo.ai business plan committed to the repo.

### Should have

- S1. Verification of fixes by reading the finalized trace back through the neatlogs Public API when a service token is configured.
- S2. A repeat-run script that reports how often the stale-policy failure appeared and how often it was caught.
- S3. A free-text ticket box so judges can try their own ticket.

### Won't have (this hackathon)

- Real email, helpdesk or payment integrations.
- Multi-tenant auth.

## Honest boundaries

- ACME orders, customers and the payment ledger are fixture data in a local SQLite database.
- The knowledge base pages are the real public neatlogs fixture, fetched live.
- The retrieval index is seeded with the outdated refund policy on purpose, exactly as neatlogs' own demo does.
- The failed address write on one seeded ticket is an injected fault, labelled as such in the UI.
- Every model call, check, fix, decision and drift run is real and traced.
- Verification falls back to the local step ledger when no neatlogs Public API token is configured, and the UI says which source was used.

## Architecture

| Part | Choice |
|---|---|
| Agent core | Python 3.13, `openai` SDK pointed at the hackathon LiteLLM proxy |
| Tracing | `neatlogs` SDK (`neatlogs.wrap` + `@neatlogs.span`) |
| Fixture world | SQLite (customers, orders, address service with fault injection) |
| Knowledge base | Live fetch of the neatlogs fixture, cached locally |
| Policy memory | SQLite, exported to `policies.yaml` |
| API | FastAPI with server-sent events for live loop steps |
| Console | Vite, React, TypeScript, Tailwind |

## Success metrics for the demo

- Every seeded failure is caught before a reply is sent.
- The stale-policy failure is caught every time it appears across repeated runs.
- The second matching loyalty ticket is resolved without a decision card.
- The drift check passes on all distinctive cases and holds a deliberately bad change.

## Milestones

1. Agent, fixture world and tracing.
2. Claim checker and classifier.
3. Auto-fix and verification.
4. Decision cards and policy memory.
5. Drift check.
6. Console.
7. Evidence, README, cfo.ai plan, demo video.
