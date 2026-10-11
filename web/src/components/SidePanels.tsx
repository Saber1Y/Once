import { AnimatePresence, motion } from "motion/react";
import { Books, Brain, Check, Database, HandPalm, Play, ShieldCheck, X } from "@phosphor-icons/react";
import type { DeskEvent, Decision, Drift, DriftResult, Rule } from "../types";
import { DecisionCard } from "./DecisionCard";
import { Button, Card, CardHeader, Empty, Tag } from "./ui";
import { cx } from "../lib";

export function Decisions({ decisions, onError }: { decisions: Decision[]; onError: (m: string) => void }) {
  const open = decisions.filter((d) => d.status !== "answered");
  const answered = decisions.filter((d) => d.status === "answered");
  return (
    <Card id="decisions">
      <CardHeader
        title="Needs you"
        icon={<HandPalm weight="bold" />}
        meta={open.length > 0 ? <Tag tone="yellow" live>{open.length} waiting</Tag> : null}
      />
      <div className="space-y-3.5 p-4">
        <AnimatePresence initial={false}>
          {open.map((d) => (
            <DecisionCard key={d.id} decision={d} onError={onError} />
          ))}
        </AnimatePresence>
        {answered.slice(-2).map((d) => (
          <DecisionCard key={d.id} decision={d} onError={onError} />
        ))}
        {decisions.length === 0 && (
          <p className="text-[13.5px] leading-relaxed text-muted">
            Nothing to decide. Once only asks when a case is a business choice that no policy covers.
          </p>
        )}
      </div>
    </Card>
  );
}

export function Memory({ rules, index }: { rules: Rule[]; index: string[] }) {
  const repaired = index.includes("refund-policy-v3.0");
  return (
    <Card>
      <CardHeader
        title="Policy memory"
        icon={<Brain weight="bold" />}
        meta={<code className="font-mono text-[11px] text-muted">policies.yaml</code>}
      />
      <div className="p-4">
        <ul>
          {rules.map((r) => (
            <motion.li
              key={r.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              className="border-b border-line py-3 first:pt-0 last:border-b-0 last:pb-0"
            >
              <div className="flex items-center justify-between gap-2">
                <Tag tone={r.status === "active" ? "green" : "red"}>
                  v{r.version} {r.status}
                </Tag>
                <span className="text-[11.5px] text-muted">
                  {r.decided_by} on {r.source_ticket}
                </span>
              </div>
              <p className="mt-2 text-[13.5px] leading-relaxed text-ink">{r.describe}</p>
              {r.held_reason && <p className="mt-1 text-[12px] leading-snug text-red-fg/90">{r.held_reason}</p>}
            </motion.li>
          ))}
          {rules.length === 0 && (
            <li className="text-[13.5px] leading-relaxed text-muted">
              No remembered decisions yet. Your answers land here as versioned rules.
            </li>
          )}
        </ul>
        <div className="mt-5 border-t border-line pt-4">
          <div className="flex items-center gap-2 text-[12.5px] font-medium text-ink-strong">
            <Database weight="bold" className="size-4 text-muted" /> Search index
          </div>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {index.map((a) => (
              <code
                key={a}
                className={cx(
                  "rounded-md px-1.5 py-0.5 font-mono text-[11px]",
                  a === "refund-policy-v2.1"
                    ? "bg-red-bg text-red-fg"
                    : a === "refund-policy-v3.0"
                      ? "bg-green-bg text-green-fg"
                      : "bg-gray-bg text-gray-fg",
                )}
              >
                {a}
              </code>
            ))}
          </div>
          <p className="mt-2.5 text-[12.5px] leading-relaxed text-muted">
            {repaired
              ? "Repaired by Once: the outdated refund policy was replaced with the current one."
              : "Seeded like neatlogs' own demo: the outdated refund policy is in, the current one is out."}
          </p>
        </div>
      </div>
    </Card>
  );
}

function DriftRow({ r }: { r: DriftResult }) {
  return (
    <li className="flex items-start gap-3 border-b border-line py-2.5 last:border-b-0">
      <span
        className={cx(
          "mt-0.5 flex size-[18px] shrink-0 items-center justify-center rounded-full",
          r.passed ? "bg-green-bg text-green-fg" : "bg-red-bg text-red-fg",
        )}
      >
        {r.passed ? <Check weight="bold" className="size-3" /> : <X weight="bold" className="size-3" />}
      </span>
      <div className="min-w-0">
        <p className="text-[13.5px] leading-snug text-ink-strong">
          <span className="mr-1 font-mono text-[11px] text-faint">{r.id}</span>
          {r.title}
        </p>
        <p className="mt-0.5 text-[12.5px] leading-snug text-muted">{r.detail}</p>
      </div>
    </li>
  );
}

export function DriftBoard({
  drift,
  events,
  canRun,
  onRun,
}: {
  drift: Drift | null;
  events: DeskEvent[];
  canRun: boolean;
  onRun: () => void;
}) {
  const types = events.map((e) => e.type);
  const startIdx = types.lastIndexOf("drift.started");
  const running = startIdx > types.lastIndexOf("drift.finished");
  const liveResults = running
    ? events.slice(startIdx).filter((e) => e.type === "drift.case").map((e) => e.result as DriftResult)
    : [];
  const total = running ? Number(events[startIdx].total) : (drift?.total ?? 0);
  const results = running ? liveResults : (drift?.results ?? []);
  const passed = results.filter((r) => r.passed).length;
  return (
    <Card>
      <CardHeader
        title="Drift check"
        icon={<ShieldCheck weight="bold" />}
        meta={
          !running && (
            <Button variant="ghost" className="-my-1 px-2 py-1 text-[12px]" onClick={onRun} disabled={!canRun}>
              <Play weight="fill" className="size-3" /> Replay
            </Button>
          )
        }
      />
      <div className="p-4">
        {total > 0 ? (
          <>
            <div className="flex items-baseline gap-2.5">
              <span
                className={cx(
                  "font-serif text-[44px] leading-none tracking-[-0.02em]",
                  !running && passed === total ? "text-green-fg" : !running ? "text-red-fg" : "text-ink-strong",
                )}
              >
                {passed}/{total}
              </span>
              <span className="text-[13px] text-muted">{running ? "replaying…" : "still behave the way ACME chose"}</span>
            </div>
            <div className="mt-3 flex gap-1">
              {Array.from({ length: total }).map((_, i) => (
                <span
                  key={i}
                  className={cx(
                    "h-1 flex-1 rounded-full transition-colors duration-500",
                    i < results.length ? (results[i].passed ? "bg-green-fg/70" : "bg-red-fg/70") : "breathe bg-line",
                  )}
                />
              ))}
            </div>
            <ul className="mt-3">
              {results.map((r) => (
                <DriftRow key={r.id} r={r} />
              ))}
            </ul>
            {drift?.rule && !running && (
              <p className="mt-2 text-[12px] text-muted">Checked with candidate rule: {drift.rule}</p>
            )}
          </>
        ) : (
          <Empty icon={<Books weight="bold" />} title="No replay yet">
            Six distinctive cases encode ACME's chosen trade-offs. They replay before any new rule is saved.
          </Empty>
        )}
      </div>
    </Card>
  );
}
