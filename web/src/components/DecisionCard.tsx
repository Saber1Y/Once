import { motion } from "motion/react";
import { Check, CheckCircle, CircleNotch, HandPalm, Minus, Plus, ShieldWarning, X } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { Decision, Rule } from "../types";
import { Button } from "./ui";
import { cx, money } from "../lib";

const numberInput =
  "w-14 rounded-md border border-line bg-surface px-1.5 py-0.5 text-center font-mono text-[13px] text-ink-strong focus:border-ink-strong focus:outline-none";

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
      <div className="flex items-start gap-2.5 border-t border-line pt-3.5 text-[13px]">
        <CheckCircle weight="fill" className="mt-0.5 size-4 shrink-0 text-green-fg" />
        <p className="leading-relaxed text-muted">
          <span className="font-medium text-ink-strong">{decision.ticket_id} answered.</span>{" "}
          {decision.scope === "always" && decision.rule
            ? `Saved as rule v${decision.rule.version}. Once won't ask this again.`
            : "Applied to this ticket only."}
        </p>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className="rounded-lg border border-line bg-surface"
    >
      <div className="flex items-center justify-between gap-2 rounded-t-lg bg-yellow-bg px-4 py-2.5 text-[12px] text-yellow-fg">
        <span className="inline-flex items-center gap-1.5 font-medium">
          <HandPalm weight="bold" className="size-4" /> Your call on {decision.ticket_id}
        </span>
        <span>asked once</span>
      </div>

      <div className="p-4">
        <p className="font-serif text-[21px] leading-[1.2] tracking-[-0.01em] text-ink-strong">{decision.question}</p>

        <dl className="mt-4 grid grid-cols-3 divide-x divide-line rounded-lg border border-line">
          {[
            ["Customer for", `${f.tenure_years} yrs`],
            ["Past window", `${f.days_over} day${f.days_over === 1 ? "" : "s"}`],
            ["Order", money(f.amount)],
          ].map(([k, v]) => (
            <div key={k} className="px-3 py-2.5">
              <dt className="text-[11px] text-muted">{k}</dt>
              <dd className="mt-0.5 font-mono text-[14px] text-ink-strong">{v}</dd>
            </div>
          ))}
        </dl>

        <button
          onClick={() => setShowEvidence((s) => !s)}
          className="mt-3 inline-flex items-center gap-1.5 text-[12.5px] font-medium text-muted hover:text-ink-strong"
        >
          {showEvidence ? <Minus className="size-3.5" /> : <Plus className="size-3.5" />}
          What the agent found ({decision.evidence.length} steps)
        </button>
        {showEvidence && (
          <div className="mt-2 space-y-2">
            <p className="text-[13px] leading-relaxed text-muted">{decision.why}</p>
            {decision.evidence.map((s) => (
              <pre
                key={s.id}
                className="scrollbar-thin max-h-28 overflow-auto rounded-md bg-subtle p-2.5 font-mono text-[11px] leading-relaxed text-gray-fg"
              >
                {s.name}({JSON.stringify(s.args)}) → {JSON.stringify(s.result)}
              </pre>
            ))}
          </div>
        )}

        {decision.status === "held" && lastAttempt && (
          <div className="mt-4 rounded-lg bg-red-bg p-3.5">
            <p className="inline-flex items-center gap-1.5 text-[13.5px] font-medium text-red-fg">
              <ShieldWarning weight="bold" className="size-4" /> Rule held. It would break{" "}
              {lastAttempt.drift.total - lastAttempt.drift.passed} of ACME's distinctive cases.
            </p>
            <ul className="mt-2 space-y-1.5">
              {lastAttempt.drift.results
                .filter((r) => !r.passed)
                .map((r) => (
                  <li key={r.id} className="flex gap-2 text-[12.5px] leading-snug text-red-fg/90">
                    <X weight="bold" className="mt-0.5 size-3.5 shrink-0" />
                    <span>
                      <span className="font-medium">{r.title}.</span> {r.detail}
                    </span>
                  </li>
                ))}
            </ul>
            <p className="mt-2 text-[12.5px] text-red-fg/80">Narrow the rule and try again.</p>
          </div>
        )}

        {busy ? (
          <div className="mt-4 flex items-center gap-2 rounded-lg bg-blue-bg px-3.5 py-3 text-[13px] text-blue-fg">
            {decision.status === "checking" ? (
              <>
                <span className="breathe size-2 rounded-full bg-blue-fg" /> Replaying distinctive cases before saving
                the rule
              </>
            ) : (
              <>
                <CircleNotch weight="bold" className="size-4 animate-spin" /> Applying your answer
              </>
            )}
          </div>
        ) : (
          <>
            <div className="mt-4 overflow-hidden rounded-lg border border-line">
              {decision.options.map((o) => (
                <button
                  key={o.value}
                  onClick={() => setOutcome(o.value)}
                  className={cx(
                    "flex w-full items-center justify-between border-b border-line px-3.5 py-2.5 text-left text-[13.5px] transition-colors last:border-b-0 focus-visible:outline-none",
                    outcome === o.value ? "bg-canvas font-medium text-ink-strong" : "text-ink hover:bg-subtle",
                  )}
                >
                  {o.label}
                  <span
                    className={cx(
                      "flex size-4 items-center justify-center rounded-full border",
                      outcome === o.value ? "border-ink-strong bg-ink-strong text-white" : "border-line",
                    )}
                  >
                    {outcome === o.value && <Check weight="bold" className="size-2.5" />}
                  </span>
                </button>
              ))}
            </div>

            <div className="mt-3 grid grid-cols-2 rounded-md border border-line p-0.5 text-[12.5px]">
              {(["always", "once"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setScope(s)}
                  className={cx(
                    "rounded px-3 py-1.5 font-medium transition-colors",
                    scope === s ? "bg-ink-strong text-white" : "text-muted hover:text-ink-strong",
                  )}
                >
                  {s === "always" ? "Make it a rule" : "Just this ticket"}
                </button>
              ))}
            </div>

            {scope === "always" && (
              <p className="mt-3 text-[13px] leading-[2] text-muted">
                Apply to customers of{" "}
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  value={tenure}
                  onChange={(e) => setTenure(Number(e.target.value))}
                  aria-label="Minimum years as a customer"
                  className={numberInput}
                />{" "}
                or more years, up to{" "}
                <input
                  type="number"
                  min={1}
                  value={days}
                  onChange={(e) => setDays(Number(e.target.value))}
                  aria-label="Maximum days past the window"
                  className={numberInput}
                />{" "}
                days past the window. Once replays ACME's distinctive cases before saving it.
              </p>
            )}

            <Button variant="primary" className="mt-4 w-full" disabled={!outcome} onClick={submit}>
              {scope === "always" ? "Decide and remember" : "Decide for this ticket"}
            </Button>
          </>
        )}
      </div>
    </motion.div>
  );
}
