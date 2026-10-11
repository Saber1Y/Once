import { AnimatePresence, motion } from "motion/react";
import {
  ArrowUpRight,
  Ban,
  Check,
  ChevronDown,
  CircleAlert,
  FlaskConical,
  Hand,
  Mail,
  Play,
  Repeat2,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { useState } from "react";
import type { AttemptRecord, DeskEvent, Finding, Fix, Run, Step, Ticket } from "../types";
import { Button, CategoryTag, Dot, Empty, HudLabel, Panel, StatusTag } from "./ui";
import { cx } from "../lib";

function short(value: unknown, max = 70): string {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function StepRow({ step }: { step: Step }) {
  const [open, setOpen] = useState(false);
  const kindColor = {
    tool: "text-info",
    commit: "text-warn",
    verify: "text-primary",
    llm: "text-agent",
  }[step.kind];
  const args = Object.values(step.args).filter((v) => typeof v === "string" || typeof v === "number");
  return (
    <li>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left font-mono text-[12px] transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring/60"
      >
        <span className="w-9 shrink-0 text-[10px] text-muted-foreground/70">{step.id.split(".")[1]}</span>
        <span className={cx("shrink-0", kindColor)}>{step.name}</span>
        <span className="min-w-0 flex-1 truncate text-muted-foreground">{args.map((a) => short(a, 40)).join(" · ")}</span>
        {step.ok ? (
          <Check className="size-3.5 shrink-0 text-primary/80" />
        ) : (
          <CircleAlert className="size-3.5 shrink-0 text-danger" />
        )}
        <ChevronDown className={cx("size-3 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.pre
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="scrollbar-thin mx-2 mb-1 max-h-56 overflow-auto rounded-lg border border-border bg-[#09090b] p-3 font-mono text-[11px] leading-relaxed text-muted-foreground"
          >
            {JSON.stringify({ args: step.args, result: step.result }, null, 2)}
          </motion.pre>
        )}
      </AnimatePresence>
    </li>
  );
}

function FindingCard({ finding, fix }: { finding: Finding; fix?: Fix }) {
  const isChoice = finding.route === "choice";
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className={cx(
        "rounded-xl border p-3.5",
        isChoice ? "border-warn/30 bg-warn/[0.06]" : "border-danger/25 bg-danger/[0.05]",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <CategoryTag category={finding.category} />
        {finding.tier === "judge" && (
          <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-agent">tier-2 judge</span>
        )}
        <span className="text-sm font-medium">{finding.title}</span>
      </div>
      <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">{finding.detail}</p>
      {typeof finding.data.fault_label === "string" && (
        <p className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2 py-1 font-mono text-[10px] text-muted-foreground">
          <FlaskConical className="size-3" /> {finding.data.fault_label}
        </p>
      )}
      <div className="mt-2.5 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]">
        {isChoice ? (
          <span className="inline-flex items-center gap-1.5 text-warn">
            <Hand className="size-3" /> A choice: sent to you
          </span>
        ) : fix ? (
          <span className="inline-flex items-center gap-1.5 text-primary">
            <Wrench className="size-3" /> Mechanical: fixed by Once
          </span>
        ) : (
          <span className="text-muted-foreground">Mechanical</span>
        )}
      </div>
      {fix && (
        <div className="mt-2 flex items-start gap-2 border-t border-border pt-2 text-[13px]">
          <span className="text-foreground/90">{fix.action}</span>
        </div>
      )}
    </motion.div>
  );
}

function AttemptBlock({ attempt, fixes, last }: { attempt: AttemptRecord; fixes: Fix[]; last: boolean }) {
  const [showDraft, setShowDraft] = useState(attempt.findings.length > 0);
  const findings = [...attempt.findings, ...(attempt.post_commit ?? []), ...(attempt.judge ?? [])];
  const clean = findings.length === 0;
  return (
    <div className="relative pl-6">
      <span
        className={cx(
          "absolute left-0 top-1 flex size-3.5 items-center justify-center rounded-full border",
          clean ? "border-primary/50 bg-primary/20" : "border-danger/50 bg-danger/20",
        )}
      />
      {!last && <span className="absolute bottom-[-12px] left-[6.5px] top-5 w-px bg-border" />}
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
          Attempt {attempt.number}
        </span>
        <span className={cx("font-mono text-[10px] uppercase tracking-[0.14em]", clean ? "text-primary" : "text-danger")}>
          {clean ? "passed checks" : `${findings.length} finding${findings.length > 1 ? "s" : ""}`}
        </span>
      </div>
      <ul className="mt-2 rounded-xl border border-border bg-black/20 p-1">
        {attempt.steps.map((s) => (
          <StepRow key={s.id} step={s} />
        ))}
        {attempt.steps.length === 0 && <li className="px-2 py-1.5 font-mono text-[12px] text-muted-foreground">no tool calls</li>}
      </ul>
      {attempt.draft && (
        <div className="mt-2">
          <button
            onClick={() => setShowDraft((s) => !s)}
            className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground hover:text-foreground"
          >
            <ChevronDown className={cx("size-3 transition-transform", showDraft && "rotate-180")} />
            Agent's draft {!clean && "(blocked)"}
          </button>
          {showDraft && (
            <p
              className={cx(
                "mt-1.5 whitespace-pre-wrap rounded-xl border px-3.5 py-3 text-[13px] leading-relaxed",
                clean ? "border-border text-foreground/80" : "border-danger/20 text-muted-foreground line-through decoration-danger/40",
              )}
            >
              {attempt.draft}
            </p>
          )}
        </div>
      )}
      {findings.length > 0 && (
        <div className="mt-3 space-y-2">
          {findings.map((f, i) => (
            <FindingCard key={`${f.code}-${i}`} finding={f} fix={fixes.find((x) => x.code === f.code)} />
          ))}
        </div>
      )}
    </div>
  );
}

function LiveLine({ events }: { events: DeskEvent[] }) {
  const last = events[events.length - 1];
  const label: Record<string, string> = {
    "ticket.started": "Reading the ticket",
    "attempt.started": `Agent working (attempt ${last?.attempt ?? ""})`,
    "attempt.checked": "Checking claims against tool results",
    "fix.applied": "Applying a fix",
    "fix.verified": "Verifying the fix",
    "attempt.post_checked": "Reading side effects back",
  };
  return (
    <div className="flex items-center gap-2 rounded-xl border border-primary/30 bg-primary/[0.06] px-3.5 py-2.5 font-mono text-[11px] uppercase tracking-[0.14em] text-primary">
      <Dot className="bg-primary" pulse />
      {label[last?.type] ?? "Working"}
    </div>
  );
}

export function TicketDetail({
  ticket,
  events,
  canRun,
  onRun,
  onJumpToDecision,
}: {
  ticket: Ticket | null;
  events: DeskEvent[];
  canRun: boolean;
  onRun: (id: string) => void;
  onJumpToDecision: () => void;
}) {
  if (!ticket) {
    return (
      <Panel className="flex items-center justify-center">
        <Empty icon={<Mail />} title="Pick a ticket">
          Select a ticket from the queue to watch the loop: act, check, fix or ask, verify.
        </Empty>
      </Panel>
    );
  }
  const run: Run | null = ticket.latest;
  const live = events.filter((e) => e.ticket_id === ticket.id);
  const running = ticket.status === "running" || ticket.status === "pending";
  return (
    <Panel className="flex min-h-0 flex-col">
      <div className="border-b border-border px-5 py-3.5">
        <HudLabel
          icon={<Play />}
          right={
            <div className="flex items-center gap-3">
              {run?.trace_id && (
                <a
                  href={run.trace_url ?? undefined}
                  target="_blank"
                  rel="noreferrer"
                  title={run.trace_url ? "Open in neatlogs" : "Trace export is off: set NEATLOGS_API_KEY"}
                  className={cx(
                    "inline-flex items-center gap-1 font-mono text-[10px]",
                    run.trace_url ? "text-primary hover:underline" : "pointer-events-none text-muted-foreground",
                  )}
                >
                  trace {run.trace_id.slice(0, 8)} {run.trace_url && <ArrowUpRight className="size-3" />}
                </a>
              )}
              <StatusTag status={ticket.status} />
            </div>
          }
        >
          The loop · {ticket.id}
        </HudLabel>
      </div>

      <div className="scrollbar-thin min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-5">
        <div>
          <p className="text-lg font-semibold tracking-[-0.02em]">{ticket.subject}</p>
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{ticket.from}</p>
          <p className="mt-3 rounded-xl border border-border bg-muted/30 px-4 py-3 text-[14px] leading-relaxed text-foreground/85">
            {ticket.body}
          </p>
        </div>

        {running && <LiveLine events={live} />}

        {!run && !running && (
          <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-border px-4 py-5">
            <p className="text-sm text-muted-foreground">Not run yet.</p>
            <Button variant="secondary" onClick={() => onRun(ticket.id)} disabled={!canRun}>
              <Play className="size-3.5" /> Run this ticket
            </Button>
          </div>
        )}

        {run && (
          <div className="space-y-5">
            {run.attempts.map((a, i) => (
              <AttemptBlock
                key={`${run.trace_id}-${a.number}`}
                attempt={a}
                fixes={run.fixes.filter((f) => f.attempt === a.number)}
                last={i === run.attempts.length - 1}
              />
            ))}
          </div>
        )}

        {run?.status === "waiting_on_you" && (
          <button
            onClick={onJumpToDecision}
            className="flex w-full items-center justify-between rounded-xl border border-warn/40 bg-warn/[0.08] px-4 py-3 text-left transition-colors hover:bg-warn/[0.12]"
          >
            <span className="flex items-center gap-2 text-sm font-medium text-warn">
              <Hand className="size-4" /> This one is a business decision. Once is waiting on you.
            </span>
            <ArrowUpRight className="size-4 text-warn" />
          </button>
        )}

        {run?.status === "failed" && (
          <div className="flex items-start gap-2 rounded-xl border border-danger/40 bg-danger/[0.08] px-4 py-3 text-sm text-danger">
            <Ban className="mt-0.5 size-4 shrink-0" /> {run.error}
          </div>
        )}

        {run?.status === "resolved" && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-xl border border-primary/30 bg-primary/[0.05] p-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-primary">
                <ShieldCheck className="size-3.5" /> Sent to customer
              </span>
              <div className="flex flex-wrap gap-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                {run.fixes.length > 0 && (
                  <span>
                    {run.fixes.filter((f) => f.verified).length}/{run.fixes.length} fixes verified
                  </span>
                )}
                {run.applied_rule && (
                  <span className="inline-flex items-center gap-1 text-warn">
                    <Repeat2 className="size-3" /> applied your rule
                  </span>
                )}
              </div>
            </div>
            <p className="mt-3 whitespace-pre-wrap text-[14px] leading-relaxed">{run.reply}</p>
            {run.commits.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2 border-t border-border pt-3">
                {run.commits.map((c) => (
                  <span key={c.step_id} className="rounded-md border border-border bg-muted/40 px-2 py-1 font-mono text-[10px] text-muted-foreground">
                    {String(c.action.type)} · {String(c.action.order_id)}
                    {typeof c.action.amount === "number" && ` · $${c.action.amount.toFixed(2)}`}
                  </span>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </div>
    </Panel>
  );
}
