import { AnimatePresence, motion } from "motion/react";
import {
  ArrowSquareOut,
  CheckCircle,
  EnvelopeSimple,
  Flask,
  HandPalm,
  Minus,
  Play,
  Plus,
  ArrowsClockwise,
  ShieldCheck,
  WarningCircle,
  Wrench,
  XCircle,
} from "@phosphor-icons/react";
import { useState } from "react";
import type { AttemptRecord, DeskEvent, Finding, Fix, Run, Step, Ticket } from "../types";
import { Button, CategoryTag, Empty, StatusTag } from "./ui";
import { cx } from "../lib";

function short(value: unknown, max = 70): string {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

const KIND_LABEL: Record<Step["kind"], string> = {
  tool: "tool",
  source: "source",
  commit: "write",
  verify: "read-back",
  llm: "model",
};

function StepRow({ step }: { step: Step }) {
  const [open, setOpen] = useState(false);
  const args = Object.values(step.args).filter((v) => typeof v === "string" || typeof v === "number");
  return (
    <li className="border-b border-line last:border-b-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 px-3.5 py-2 text-left font-mono text-[12px] transition-colors hover:bg-subtle focus-visible:bg-subtle focus-visible:outline-none"
      >
        <span className="w-6 shrink-0 text-faint">{step.id.split(".")[1]}</span>
        <span className="w-[70px] shrink-0 text-[10.5px] uppercase tracking-[0.05em] text-faint">{KIND_LABEL[step.kind]}</span>
        <span className="shrink-0 text-ink-strong">{step.name}</span>
        <span className="min-w-0 flex-1 truncate text-muted">{args.map((a) => short(a, 44)).join(" · ")}</span>
        {step.ok ? (
          <CheckCircle weight="fill" className="size-4 shrink-0 text-green-fg/70" />
        ) : (
          <XCircle weight="fill" className="size-4 shrink-0 text-red-fg" />
        )}
        {open ? <Minus className="size-3.5 shrink-0 text-faint" /> : <Plus className="size-3.5 shrink-0 text-faint" />}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.pre
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="scrollbar-thin max-h-56 overflow-auto border-t border-line bg-subtle px-4 py-3 font-mono text-[11px] leading-relaxed text-gray-fg"
          >
            {JSON.stringify({ args: step.args, result: step.result }, null, 2)}
          </motion.pre>
        )}
      </AnimatePresence>
    </li>
  );
}

function FindingRow({ finding, fix }: { finding: Finding; fix?: Fix }) {
  const isChoice = finding.route === "choice";
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="border-b border-line py-3.5 last:border-b-0"
    >
      <div className="flex flex-wrap items-center gap-2">
        <CategoryTag category={finding.category} />
        {finding.tier === "judge" && <span className="font-mono text-[10.5px] text-muted">tier-2 judge</span>}
        <span className="text-[14px] font-medium text-ink-strong">{finding.title}</span>
      </div>
      <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">{finding.detail}</p>
      {typeof finding.data.fault_label === "string" && (
        <p className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-gray-bg px-2 py-1 font-mono text-[11px] text-gray-fg">
          <Flask weight="bold" className="size-3.5" /> {finding.data.fault_label}
        </p>
      )}
      <div className="mt-2.5 flex items-start gap-2 text-[13px]">
        {isChoice ? (
          <>
            <HandPalm weight="bold" className="mt-0.5 size-4 shrink-0 text-yellow-fg" />
            <span className="text-ink">A business choice. Sent to you.</span>
          </>
        ) : fix ? (
          <>
            <Wrench weight="bold" className="mt-0.5 size-4 shrink-0 text-green-fg" />
            <span className="text-ink">
              <span className="font-medium">Fixed by Once.</span> {fix.action}
            </span>
          </>
        ) : (
          <span className="text-muted">Mechanical</span>
        )}
      </div>
    </motion.div>
  );
}

function AttemptBlock({ attempt, fixes, last }: { attempt: AttemptRecord; fixes: Fix[]; last: boolean }) {
  const [showDraft, setShowDraft] = useState(attempt.findings.length > 0);
  const findings = [...attempt.findings, ...(attempt.post_commit ?? []), ...(attempt.judge ?? [])];
  const clean = findings.length === 0;
  return (
    <div className="relative pl-7">
      <span
        className={cx(
          "absolute left-0 top-[5px] size-[11px] rounded-full border-2",
          clean ? "border-green-fg bg-green-bg" : "border-red-fg bg-red-bg",
        )}
      />
      {!last && <span className="absolute -bottom-6 left-[5px] top-5 w-px bg-line" />}
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[15px] font-semibold tracking-[-0.01em] text-ink-strong">Attempt {attempt.number}</span>
        <span className={cx("text-[12.5px]", clean ? "text-green-fg" : "text-red-fg")}>
          {clean ? "Passed every check" : `${findings.length} finding${findings.length > 1 ? "s" : ""}`}
        </span>
      </div>
      <ul className="mt-3 overflow-hidden rounded-lg border border-line">
        {attempt.steps.map((s) => (
          <StepRow key={s.id} step={s} />
        ))}
        {attempt.steps.length === 0 && <li className="px-3.5 py-2 font-mono text-[12px] text-muted">No tool calls</li>}
      </ul>
      {attempt.draft && (
        <div className="mt-3">
          <button
            onClick={() => setShowDraft((s) => !s)}
            className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-muted hover:text-ink-strong"
          >
            {showDraft ? <Minus className="size-3.5" /> : <Plus className="size-3.5" />}
            Agent's draft{!clean && ", blocked"}
          </button>
          {showDraft && (
            <p
              className={cx(
                "mt-2 whitespace-pre-wrap border-l-2 pl-4 text-[13.5px] leading-relaxed",
                clean ? "border-line text-ink" : "border-red-bg text-muted line-through decoration-red-fg/30",
              )}
            >
              {attempt.draft}
            </p>
          )}
        </div>
      )}
      {findings.length > 0 && (
        <div className="mt-3">
          {findings.map((f, i) => (
            <FindingRow key={`${f.code}-${i}`} finding={f} fix={fixes.find((x) => x.code === f.code)} />
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
    "attempt.started": `The agent is working, attempt ${last?.attempt ?? ""}`,
    "attempt.checked": "Checking every claim against the tool results",
    "fix.applied": "Applying a fix",
    "fix.verified": "Verifying the fix",
    "attempt.post_checked": "Reading side effects back",
  };
  return (
    <div className="flex items-center gap-2.5 rounded-lg bg-blue-bg px-4 py-3 text-[13px] text-blue-fg">
      <span className="breathe size-2 rounded-full bg-blue-fg" />
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
      <section className="flex items-center justify-center rounded-xl border border-line bg-surface">
        <Empty icon={<EnvelopeSimple weight="bold" />} title="Pick a ticket">
          Select a ticket to follow the loop: act, check, fix or ask, verify.
        </Empty>
      </section>
    );
  }
  const run: Run | null = ticket.latest;
  const live = events.filter((e) => e.ticket_id === ticket.id);
  const running = ticket.status === "running" || ticket.status === "pending";
  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-line bg-surface">
      <div className="flex items-center justify-between gap-3 border-b border-line px-6 py-3.5">
        <span className="font-mono text-[11px] text-muted">{ticket.id}</span>
        <div className="flex items-center gap-3">
          {run?.trace_id && (
            <a
              href={run.trace_url ?? undefined}
              target="_blank"
              rel="noreferrer"
              title={run.trace_url ? "Open in neatlogs" : "Trace export is off: set NEATLOGS_API_KEY"}
              className={cx(
                "inline-flex items-center gap-1 font-mono text-[11px]",
                run.trace_url ? "text-ink-strong underline decoration-line underline-offset-4 hover:decoration-ink-strong" : "pointer-events-none text-muted",
              )}
            >
              neatlogs trace {run.trace_id.slice(0, 8)}
              {run.trace_url && <ArrowSquareOut className="size-3.5" />}
            </a>
          )}
          <StatusTag status={ticket.status} />
        </div>
      </div>

      <div className="scrollbar-thin min-h-0 flex-1 space-y-7 overflow-y-auto px-6 pb-24 pt-6 md:px-8">
        <div>
          <h2 className="text-[24px] font-semibold leading-[1.2] tracking-[-0.025em] text-ink-strong">{ticket.subject}</h2>
          <p className="mt-1 text-[13px] text-muted">from {ticket.from}</p>
          <blockquote className="mt-4 border-l-2 border-ink-strong/80 pl-4 text-[15px] leading-relaxed text-ink">
            {ticket.body}
          </blockquote>
        </div>

        {running && <LiveLine events={live} />}

        {!run && !running && (
          <div className="flex items-center justify-between gap-4 rounded-lg border border-dashed border-line px-5 py-4">
            <p className="text-[13.5px] text-muted">This ticket hasn't been run yet.</p>
            <Button onClick={() => onRun(ticket.id)} disabled={!canRun}>
              <Play weight="fill" className="size-3.5" /> Run ticket
            </Button>
          </div>
        )}

        {run && (
          <div className="space-y-8">
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
            className="flex w-full items-center justify-between gap-3 rounded-lg bg-yellow-bg px-4 py-3.5 text-left text-[13.5px] text-yellow-fg transition-transform active:scale-[0.99]"
          >
            <span className="flex items-center gap-2 font-medium">
              <HandPalm weight="bold" className="size-4" /> This is a business decision. Once is waiting for you.
            </span>
            <span className="text-[12.5px] underline underline-offset-4">Decide</span>
          </button>
        )}

        {run?.status === "failed" && (
          <div className="flex items-start gap-2 rounded-lg bg-red-bg px-4 py-3 text-[13.5px] text-red-fg">
            <WarningCircle weight="bold" className="mt-0.5 size-4 shrink-0" /> {run.error}
          </div>
        )}

        {run?.status === "resolved" && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            className="rounded-lg border border-line bg-subtle"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-3">
              <span className="inline-flex items-center gap-1.5 text-[13px] font-medium text-green-fg">
                <ShieldCheck weight="bold" className="size-4" /> Sent to the customer
              </span>
              <div className="flex flex-wrap gap-4 text-[12px] text-muted">
                {run.fixes.length > 0 && (
                  <span>
                    {run.fixes.filter((f) => f.verified).length} of {run.fixes.length} fixes verified
                  </span>
                )}
                {run.applied_rule && (
                  <span className="inline-flex items-center gap-1 text-yellow-fg">
                    <ArrowsClockwise weight="bold" className="size-3.5" /> used your rule
                  </span>
                )}
              </div>
            </div>
            <p className="whitespace-pre-wrap px-5 py-4 text-[14.5px] leading-relaxed text-ink">{run.reply}</p>
            {run.commits.length > 0 && (
              <div className="flex flex-wrap gap-2 border-t border-line px-5 py-3">
                {run.commits.map((c) => (
                  <code key={c.step_id} className="rounded-md bg-gray-bg px-2 py-0.5 font-mono text-[11px] text-gray-fg">
                    {String(c.action.type)} · {String(c.action.order_id)}
                    {typeof c.action.amount === "number" && ` · $${c.action.amount.toFixed(2)}`}
                  </code>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </div>
    </section>
  );
}
