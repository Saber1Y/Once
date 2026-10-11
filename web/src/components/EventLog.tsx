import { useEffect, useRef } from "react";
import type { DeskEvent, Finding, Fix } from "../types";

const COLORS: Record<string, string> = {
  system: "text-blue-fg",
  success: "text-green-fg",
  agent: "text-gray-fg",
  decision: "text-yellow-fg",
  failure: "text-red-fg",
};

function describe(e: DeskEvent): { tag: string; tone: keyof typeof COLORS; text: string } | null {
  const t = e.ticket_id ? `${e.ticket_id} ` : "";
  switch (e.type) {
    case "ticket.started":
      return { tag: "START", tone: "system", text: `${t}trace ${String(e.trace_id ?? "local").slice(0, 8)}` };
    case "attempt.started":
      return { tag: "AGENT", tone: "agent", text: `${t}attempt ${e.attempt}` };
    case "attempt.checked": {
      const a = e.attempt as { number: number; findings: Finding[] };
      return a.findings.length
        ? { tag: "CHECK", tone: "failure", text: `${t}blocked: ${a.findings.map((f) => f.title.toLowerCase()).join("; ")}` }
        : { tag: "CHECK", tone: "success", text: `${t}attempt ${a.number} passed every check` };
    }
    case "attempt.post_checked": {
      const f = e.findings as Finding[];
      return { tag: "VERIFY", tone: "failure", text: `${t}${f.map((x) => x.title.toLowerCase()).join("; ")}` };
    }
    case "fix.applied":
      return { tag: "FIX", tone: "success", text: `${t}${(e.fix as Fix).action}` };
    case "fix.verified":
      return { tag: "VERIFIED", tone: "success", text: `${t}${e.how}` };
    case "ticket.waiting":
      return { tag: "ASK", tone: "decision", text: `${t}business decision sent to the support lead` };
    case "ticket.resolved":
      return {
        tag: "SENT",
        tone: "success",
        text: `${t}resolved in ${e.attempts} attempt${e.attempts === 1 ? "" : "s"}${e.applied_rule ? " using your rule" : ""}`,
      };
    case "ticket.failed":
      return { tag: "FAILED", tone: "failure", text: `${t}${e.error}` };
    case "decision.checking":
      return { tag: "RULE", tone: "decision", text: `candidate: ${(e.rule as { describe: string }).describe}` };
    case "decision.answered":
      return { tag: "RULE", tone: "success", text: `saved; ${(e.decision as { ticket_id: string }).ticket_id} resumes` };
    case "decision.held":
      return { tag: "HELD", tone: "failure", text: `rule held: breaks ${(e.failed as unknown[]).length} distinctive case(s)` };
    case "drift.started":
      return { tag: "DRIFT", tone: "system", text: `replaying ${e.total} distinctive cases` };
    case "drift.case": {
      const r = e.result as { id: string; passed: boolean; title: string };
      return { tag: "DRIFT", tone: r.passed ? "success" : "failure", text: `${r.id} ${r.passed ? "holds" : "BROKEN"}: ${r.title}` };
    }
    case "drift.finished":
      return { tag: "DRIFT", tone: e.passed === e.total ? "success" : "failure", text: `${e.passed}/${e.total} hold` };
    case "desk.error":
      return { tag: "ERROR", tone: "failure", text: String(e.error) };
    default:
      return null;
  }
}

export function EventLog({ events }: { events: DeskEvent[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [events.length]);
  const rows = events.map((e) => ({ e, d: describe(e) })).filter((r) => r.d);
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface">
      <div className="flex items-center gap-2 border-b border-line bg-surface px-4 py-2.5">
        <span className="size-2.5 rounded-full bg-[#e3e2de]" />
        <span className="size-2.5 rounded-full bg-[#e3e2de]" />
        <span className="size-2.5 rounded-full bg-[#e3e2de]" />
        <span className="ml-2 font-mono text-[11px] text-muted">once_loop.log</span>
      </div>
      <div ref={ref} className="scrollbar-thin h-44 overflow-y-auto bg-subtle px-4 py-3 font-mono text-[12px] leading-relaxed">
        {rows.length === 0 && <div className="text-muted">Waiting for the first run…</div>}
        {rows.map(({ e, d }) => (
          <div key={e.id} className="flex gap-3 text-ink">
            <span className="shrink-0 text-faint">
              {new Date(e.ts * 1000).toLocaleTimeString([], { hour12: false })}
            </span>
            <span className={`w-16 shrink-0 font-medium ${COLORS[d!.tone]}`}>{d!.tag}</span>
            <span className="min-w-0 break-words">{d!.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
