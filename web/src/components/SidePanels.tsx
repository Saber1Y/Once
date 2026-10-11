import { AnimatePresence, motion } from "motion/react";
import { BookCheck, Brain, Check, Database, Hand, Play, ShieldCheck, X } from "lucide-react";
import type { DeskEvent, Decision, Drift, DriftResult, Rule } from "../types";
import { DecisionCard } from "./DecisionCard";
import { Button, Dot, Empty, HudLabel, Panel } from "./ui";
import { cx } from "../lib";

export function Decisions({ decisions, onError }: { decisions: Decision[]; onError: (m: string) => void }) {
  const open = decisions.filter((d) => d.status !== "answered");
  const answered = decisions.filter((d) => d.status === "answered");
  return (
    <Panel className="p-4" >
      <div id="decisions" />
      <HudLabel
        icon={<Hand />}
        right={
          open.length > 0 ? (
            <span className="inline-flex items-center gap-1.5 font-mono text-[10px] text-warn">
              <Dot className="bg-warn" pulse /> {open.length} waiting
            </span>
          ) : null
        }
      >
        Needs you
      </HudLabel>
      <div className="mt-3 space-y-2.5">
        <AnimatePresence initial={false}>
          {open.map((d) => (
            <DecisionCard key={d.id} decision={d} onError={onError} />
          ))}
        </AnimatePresence>
        {answered.slice(-2).map((d) => (
          <DecisionCard key={d.id} decision={d} onError={onError} />
        ))}
        {decisions.length === 0 && (
          <p className="py-3 text-[13px] leading-relaxed text-muted-foreground">
            Nothing to decide. Once only asks when a case is a business choice no policy covers.
          </p>
        )}
      </div>
    </Panel>
  );
}

export function Memory({ rules, index }: { rules: Rule[]; index: string[] }) {
  const repaired = index.includes("refund-policy-v3.0");
  return (
    <Panel className="p-4">
      <HudLabel icon={<Brain />} right={<span className="font-mono text-[10px] text-muted-foreground">policies.yaml</span>}>
        Policy memory
      </HudLabel>
      <ul className="mt-3 space-y-2">
        {rules.map((r) => (
          <motion.li
            layout
            key={r.id}
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            className={cx(
              "rounded-xl border p-3",
              r.status === "active" ? "border-primary/25 bg-primary/[0.04]" : "border-danger/25 bg-danger/[0.04]",
            )}
          >
            <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.14em]">
              <span className={r.status === "active" ? "text-primary" : "text-danger"}>
                v{r.version} · {r.status}
              </span>
              <span className="text-muted-foreground">
                {r.decided_by} · {r.source_ticket}
              </span>
            </div>
            <p className="mt-1.5 text-[13px] leading-relaxed">{r.describe}</p>
            {r.held_reason && <p className="mt-1 text-[12px] leading-snug text-muted-foreground">{r.held_reason}</p>}
          </motion.li>
        ))}
        {rules.length === 0 && (
          <li className="text-[13px] leading-relaxed text-muted-foreground">
            No remembered decisions yet. Your answers land here as versioned rules.
          </li>
        )}
      </ul>
      <div className="mt-4 border-t border-border pt-3">
        <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          <Database className="size-3.5 text-primary" /> Search index
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {index.map((a) => (
            <span
              key={a}
              className={cx(
                "rounded-md border px-1.5 py-0.5 font-mono text-[10px]",
                a === "refund-policy-v2.1"
                  ? "border-danger/30 text-danger"
                  : a === "refund-policy-v3.0"
                    ? "border-primary/30 text-primary"
                    : "border-border text-muted-foreground",
              )}
            >
              {a}
            </span>
          ))}
        </div>
        <p className="mt-2 text-[12px] leading-snug text-muted-foreground">
          {repaired
            ? "Repaired by Once: the outdated refund policy was replaced with the current one."
            : "Seeded like neatlogs' own demo: the outdated refund policy is in, the current one is out."}
        </p>
      </div>
    </Panel>
  );
}

function DriftRow({ r }: { r: DriftResult }) {
  return (
    <li className="flex items-start gap-2.5 py-1.5">
      <span
        className={cx(
          "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full",
          r.passed ? "bg-primary/15 text-primary" : "bg-danger/15 text-danger",
        )}
      >
        {r.passed ? <Check className="size-3" /> : <X className="size-3" />}
      </span>
      <div className="min-w-0">
        <p className="text-[13px] leading-snug">
          <span className="font-mono text-[10px] text-muted-foreground">{r.id}</span> {r.title}
        </p>
        <p className="text-[12px] leading-snug text-muted-foreground">{r.detail}</p>
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
  const startIdx = events.map((e) => e.type).lastIndexOf("drift.started");
  const finishIdx = events.map((e) => e.type).lastIndexOf("drift.finished");
  const running = startIdx > finishIdx;
  const liveResults = running
    ? events.slice(startIdx).filter((e) => e.type === "drift.case").map((e) => e.result as DriftResult)
    : [];
  const total = running ? Number(events[startIdx].total) : drift?.total ?? 0;
  const results = running ? liveResults : drift?.results ?? [];
  const passed = results.filter((r) => r.passed).length;
  return (
    <Panel className="p-4">
      <HudLabel
        icon={<ShieldCheck />}
        right={
          !running && (
            <Button variant="ghost" className="-my-1 px-2.5 py-1 text-xs" onClick={onRun} disabled={!canRun}>
              <Play className="size-3" /> Replay
            </Button>
          )
        }
      >
        Drift check
      </HudLabel>
      {total > 0 ? (
        <>
          <div className="mt-3 flex items-baseline gap-2">
            <span className={cx("text-3xl font-semibold tracking-[-0.04em]", passed === total && !running ? "text-primary" : "")}>
              {passed}/{total}
            </span>
            <span className="text-[13px] text-muted-foreground">
              {running ? "replaying…" : "still behave the way ACME chose"}
            </span>
          </div>
          <div className="mt-2 flex gap-1">
            {Array.from({ length: total }).map((_, i) => (
              <span
                key={i}
                className={cx(
                  "h-1 flex-1 rounded-full transition-colors duration-300",
                  i < results.length ? (results[i].passed ? "bg-primary" : "bg-danger") : "animate-pulse bg-muted",
                )}
              />
            ))}
          </div>
          <ul className="mt-3 divide-y divide-border">
            {results.map((r) => (
              <DriftRow key={r.id} r={r} />
            ))}
          </ul>
          {drift?.rule && !running && (
            <p className="mt-2 font-mono text-[10px] text-muted-foreground">checked with candidate: {drift.rule}</p>
          )}
        </>
      ) : (
        <Empty icon={<BookCheck />} title="No replay yet">
          Six distinctive cases encode ACME's chosen trade-offs. They replay before any new rule is saved.
        </Empty>
      )}
    </Panel>
  );
}
