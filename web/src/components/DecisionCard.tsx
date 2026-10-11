import { motion } from "motion/react";
import { Check, ChevronDown, Hand, Loader2, ShieldAlert, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { Decision, Rule } from "../types";
import { Button, Dot } from "./ui";
import { cx, money } from "../lib";

export function DecisionCard({ decision, onError }: { decision: Decision; onError: (m: string) => void }) {
  const [outcome, setOutcome] = useState<Rule["outcome"] | null>(null);
  const [scope, setScope] = useState<"always" | "once">("always");
  const [tenure, setTenure] = useState(decision.suggested_scope.min_tenure_years);
  const [days, setDays] = useState(decision.suggested_scope.max_days_over);
  const [showEvidence, setShowEvidence] = useState(false);
  const [sending, setSending] = useState(false);
  const busy = decision.status === "checking" || decision.status === "answering" || sending;
  const lastAttempt = decision.attempts[decision.attempts.length - 1];
  const f = decision.facts;

  useEffect(() => {
    if (decision.status !== "open" && decision.status !== "held") setSending(false);
  }, [decision.status]);

  async function submit() {
    if (!outcome) return;
    setSending(true);
    try {
      await api.answer(decision.id, { outcome, scope, min_tenure_years: tenure, max_days_over: days });
    } catch (e) {
      setSending(false);
      onError(e instanceof Error ? e.message : String(e));
    }
  }

  if (decision.status === "answered") {
    return (
      <div className="rounded-xl border border-border bg-muted/20 p-3.5">
        <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-primary">
          <Check className="size-3.5" /> Answered · {decision.ticket_id}
        </div>
        <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">
          {decision.scope === "always" && decision.rule
            ? `Saved as rule v${decision.rule.version}. Once won't ask this again.`
            : "Applied to this ticket only."}
        </p>
      </div>
    );
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className="rounded-2xl border border-warn/35 bg-warn/[0.05] p-4 shadow-[0_0_40px_rgba(240,190,80,0.06)]"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-warn">
          <Hand className="size-3.5" /> Your call · {decision.ticket_id}
        </span>
        <span className="font-mono text-[10px] text-muted-foreground">asked once</span>
      </div>

      <p className="mt-3 text-[15px] font-medium leading-snug">{decision.question}</p>

      <dl className="mt-3 grid grid-cols-3 gap-2">
        {[
          ["Customer for", `${f.tenure_years} yrs`],
          ["Past window", `${f.days_over} day${f.days_over === 1 ? "" : "s"}`],
          ["Order", money(f.amount)],
        ].map(([k, v]) => (
          <div key={k} className="rounded-lg border border-border bg-black/20 px-2.5 py-2">
            <dt className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">{k}</dt>
            <dd className="mt-0.5 text-sm font-semibold">{v}</dd>
          </div>
        ))}
      </dl>

      <button
        onClick={() => setShowEvidence((s) => !s)}
        className="mt-3 inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground hover:text-foreground"
      >
        <ChevronDown className={cx("size-3 transition-transform", showEvidence && "rotate-180")} />
        What the agent found ({decision.evidence.length} steps)
      </button>
      {showEvidence && (
        <div className="mt-2 space-y-1.5">
          <p className="text-[13px] leading-relaxed text-muted-foreground">{decision.why}</p>
          {decision.evidence.map((s) => (
            <pre
              key={s.id}
              className="scrollbar-thin max-h-28 overflow-auto rounded-lg border border-border bg-[#09090b] p-2 font-mono text-[10.5px] leading-relaxed text-muted-foreground"
            >
              {s.name}({JSON.stringify(s.args)}) → {JSON.stringify(s.result)}
            </pre>
          ))}
        </div>
      )}

      {decision.status === "held" && lastAttempt && (
        <div className="mt-3 rounded-xl border border-danger/35 bg-danger/[0.07] p-3">
          <p className="inline-flex items-center gap-1.5 text-sm font-medium text-danger">
            <ShieldAlert className="size-4" /> Rule held: it would break {lastAttempt.drift.total - lastAttempt.drift.passed} of
            ACME's distinctive cases
          </p>
          <ul className="mt-2 space-y-1">
            {lastAttempt.drift.results
              .filter((r) => !r.passed)
              .map((r) => (
                <li key={r.id} className="flex gap-2 text-[12.5px] leading-snug text-muted-foreground">
                  <X className="mt-0.5 size-3.5 shrink-0 text-danger" />
                  <span>
                    <span className="text-foreground">{r.title}.</span> {r.detail}
                  </span>
                </li>
              ))}
          </ul>
          <p className="mt-2 text-[12.5px] text-muted-foreground">Narrow the rule and try again.</p>
        </div>
      )}

      {busy ? (
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-primary/30 bg-primary/[0.06] px-3.5 py-3 font-mono text-[11px] uppercase tracking-[0.14em] text-primary">
          {decision.status === "checking" ? (
            <>
              <Dot className="bg-primary" pulse /> Replaying distinctive cases before saving the rule
            </>
          ) : (
            <>
              <Loader2 className="size-3.5 animate-spin" /> Applying your answer
            </>
          )}
        </div>
      ) : (
        <>
          <div className="mt-4 grid gap-1.5">
            {decision.options.map((o) => (
              <button
                key={o.value}
                onClick={() => setOutcome(o.value)}
                className={cx(
                  "flex items-center justify-between rounded-xl border px-3.5 py-2.5 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
                  outcome === o.value
                    ? "border-primary/50 bg-primary/[0.1] text-foreground"
                    : "border-border hover:bg-muted/50",
                )}
              >
                {o.label}
                {outcome === o.value && <Check className="size-4 text-primary" />}
              </button>
            ))}
          </div>

          <div className="mt-3 inline-flex rounded-full border border-border p-0.5">
            {(["always", "once"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setScope(s)}
                className={cx(
                  "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                  scope === s ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {s === "always" ? "Make it a rule" : "Just this ticket"}
              </button>
            ))}
          </div>

          {scope === "always" && (
            <div className="mt-3 rounded-xl border border-border bg-black/20 p-3 text-[13px] leading-relaxed text-muted-foreground">
              Apply to customers of{" "}
              <input
                type="number"
                min={0}
                step={0.5}
                value={tenure}
                onChange={(e) => setTenure(Number(e.target.value))}
                aria-label="Minimum years as a customer"
                className="w-14 rounded-md border border-border bg-muted/50 px-1.5 py-0.5 text-center font-mono text-foreground focus:border-primary/60 focus:outline-none"
              />{" "}
              + years, up to{" "}
              <input
                type="number"
                min={1}
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                aria-label="Maximum days past the window"
                className="w-14 rounded-md border border-border bg-muted/50 px-1.5 py-0.5 text-center font-mono text-foreground focus:border-primary/60 focus:outline-none"
              />{" "}
              days past the window. Once replays ACME's distinctive cases before saving it.
            </div>
          )}

          <Button variant="primary" className="mt-4 w-full" disabled={!outcome} onClick={submit}>
            {scope === "always" ? "Decide and remember" : "Decide for this ticket"}
          </Button>
        </>
      )}
    </motion.div>
  );
}
