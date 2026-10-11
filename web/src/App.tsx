import { AnimatePresence, motion } from "motion/react";
import { CircleDot, KeyRound, Play, RotateCcw, Send, TriangleAlert, X } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api, useDesk } from "./api";
import { EventLog } from "./components/EventLog";
import { Queue } from "./components/Queue";
import { Decisions, DriftBoard, Memory } from "./components/SidePanels";
import { TicketDetail } from "./components/TicketDetail";
import { Button, Dot } from "./components/ui";
import { cx } from "./lib";

function Metric({ label, value, accent, hint }: { label: string; value: string | number; accent?: boolean; hint?: string }) {
  return (
    <div className="border-t border-border pt-3" title={hint}>
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <p className={cx("mt-2 text-2xl font-semibold tracking-[-0.04em]", accent && "text-primary")}>{value}</p>
    </div>
  );
}

export default function App() {
  const { state, events, connected, error } = useDesk();
  const [selected, setSelected] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [composer, setComposer] = useState("");

  const tickets = useMemo(() => state?.tickets ?? [], [state]);
  const active = tickets.find((t) => t.status === "running");

  useEffect(() => {
    if (active) setSelected(active.id);
  }, [active?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!selected && tickets.length) setSelected(tickets[0].id);
  }, [tickets, selected]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 6000);
    return () => window.clearTimeout(t);
  }, [toast]);

  const call = (fn: () => Promise<unknown>) => () => {
    fn().catch((e) => setToast(e instanceof Error ? e.message : String(e)));
  };

  async function submitTicket(e: FormEvent) {
    e.preventDefault();
    const body = composer.trim();
    if (!body) return;
    try {
      const { id } = await api.addTicket("priya@example.com", body.slice(0, 60), body);
      setComposer("");
      setSelected(id);
    } catch (err) {
      setToast(err instanceof Error ? err.message : String(err));
    }
  }

  const ticket = tickets.find((t) => t.id === selected) ?? null;
  const ready = !!state?.llm_ready;
  const stats = state?.stats;
  const busy = !!state?.busy;
  const queued = tickets.some((t) => t.status === "queued" || t.status === "failed");

  return (
    <main className="relative min-h-[100dvh] overflow-x-hidden bg-[#09090b] px-4 pb-28 pt-24 text-foreground md:px-8">
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 opacity-20"
        style={{
          backgroundImage: "radial-gradient(circle at 2px 2px, rgba(255,255,255,0.15) 1px, transparent 0)",
          backgroundSize: "32px 32px",
        }}
      />

      <motion.header
        initial={{ y: -12, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="fixed left-1/2 top-4 z-50 flex w-[min(1100px,calc(100vw-2rem))] -translate-x-1/2 items-center justify-between gap-3 rounded-full border border-border bg-card/70 px-3 py-2.5 shadow-xl shadow-black/10 backdrop-blur-xl md:px-4"
      >
        <div className="flex items-center gap-3">
          <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground shadow-[0_0_15px_rgba(200,245,106,0.3)]">
            <CircleDot className="size-4" />
          </span>
          <span className="font-mono text-sm tracking-[0.16em]">ONCE</span>
          <span className="hidden text-sm text-muted-foreground md:inline">ACME support desk</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="hidden items-center gap-1.5 rounded-full border border-border bg-card/70 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] sm:inline-flex"
            title={state?.tracing.exporting ? "Traces export to neatlogs" : "Set NEATLOGS_API_KEY to export traces"}
          >
            <Dot className={state?.tracing.exporting ? "bg-primary" : "bg-muted-foreground"} pulse={state?.tracing.exporting && busy} />
            {state?.tracing.exporting ? "neatlogs live" : "traces local only"}
          </span>
          <Button variant="ghost" className="px-3" onClick={call(api.reset)} title="Reset the demo" disabled={busy}>
            <RotateCcw className="size-3.5" /> <span className="hidden sm:inline">Reset</span>
          </Button>
          <Button variant="primary" onClick={call(api.runQueue)} disabled={!ready || busy || !queued}>
            <Play className="size-3.5" /> {busy ? "Working" : "Run queue"}
          </Button>
        </div>
      </motion.header>

      <div className="relative z-10 mx-auto max-w-[1400px]">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-primary">neatHack 2026 · live desk</p>
            <h1 className="mt-2 text-3xl font-semibold leading-[1.02] tracking-[-0.05em] md:text-5xl">
              Fixes what's mechanical.
              <br />
              <span className="text-muted-foreground">Asks what's a choice. Only needs you once.</span>
            </h1>
          </div>
          <div className="grid grid-cols-3 gap-x-6 gap-y-3 md:grid-cols-5 md:gap-x-8">
            <Metric label="Resolved" value={stats?.resolved ?? 0} />
            <Metric label="Fixed alone" value={stats ? `${stats.fixed_verified}/${stats.fixed_alone}` : "0"} accent hint="Verified / applied" />
            <Metric label="Asked you" value={stats?.asked ?? 0} />
            <Metric label="Rules" value={stats?.rules ?? 0} />
            <Metric label="Reused" value={stats?.rule_reuses ?? 0} accent hint="Tickets resolved with a remembered rule" />
          </div>
        </div>

        {state && !ready && (
          <div className="mt-6 flex items-start gap-3 rounded-2xl border border-warn/35 bg-warn/[0.06] px-4 py-3 text-sm">
            <KeyRound className="mt-0.5 size-4 shrink-0 text-warn" />
            <p className="leading-relaxed">
              <span className="font-medium text-warn">No model configured.</span>{" "}
              <span className="text-muted-foreground">
                Add <code className="font-mono text-foreground">LLM_API_KEY</code>,{" "}
                <code className="font-mono text-foreground">LLM_BASE_URL</code> and{" "}
                <code className="font-mono text-foreground">ONCE_MODEL</code> to <code className="font-mono">.env</code>, then
                restart the server. Nothing below is simulated, so nothing runs without a model.
              </span>
            </p>
          </div>
        )}
        {error && (
          <div className="mt-6 flex items-center gap-3 rounded-2xl border border-danger/35 bg-danger/[0.06] px-4 py-3 text-sm text-danger">
            <TriangleAlert className="size-4" /> Can't reach the Once API: {error}
          </div>
        )}

        <div className="mt-8 grid gap-4 lg:h-[calc(100dvh-330px)] lg:min-h-[560px] lg:grid-cols-[280px_minmax(0,1fr)_360px]">
          <Queue tickets={tickets} selected={selected} onSelect={setSelected} />
          <TicketDetail
            ticket={ticket}
            events={events}
            canRun={ready && !busy}
            onRun={(id) => call(() => api.runTicket(id))()}
            onJumpToDecision={() => document.getElementById("decisions")?.scrollIntoView({ behavior: "smooth" })}
          />
          <div className="scrollbar-thin space-y-4 lg:min-h-0 lg:overflow-y-auto lg:pr-1">
            <Decisions decisions={state?.decisions ?? []} onError={setToast} />
            <DriftBoard drift={state?.drift ?? null} events={events} canRun={ready && !busy} onRun={call(api.drift)} />
            <Memory rules={state?.policies ?? []} index={state?.index ?? []} />
          </div>
        </div>

        <div className="mt-4">
          <EventLog events={events} />
        </div>
      </div>

      <form
        onSubmit={submitTicket}
        className="fixed bottom-5 left-1/2 z-40 flex w-[min(720px,calc(100vw-2rem))] -translate-x-1/2 items-center gap-2 rounded-full border border-border bg-card/80 py-1.5 pl-5 pr-1.5 shadow-2xl shadow-black/40 backdrop-blur-xl focus-within:border-primary/50"
      >
        <span className="hidden font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground sm:inline">as priya@</span>
        <input
          value={composer}
          onChange={(e) => setComposer(e.target.value)}
          placeholder="Write your own ticket and watch Once handle it…"
          aria-label="New ticket"
          maxLength={4000}
          className="min-w-0 flex-1 bg-transparent py-2 text-sm placeholder:text-muted-foreground/70 focus:outline-none"
        />
        <Button type="submit" variant="primary" className="px-3.5" disabled={!ready || !composer.trim()}>
          <Send className="size-3.5" />
        </Button>
      </form>

      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            className="fixed bottom-24 left-1/2 z-50 flex w-[min(520px,calc(100vw-2rem))] -translate-x-1/2 items-start gap-3 rounded-2xl border border-danger/40 bg-card/95 px-4 py-3 text-sm shadow-2xl backdrop-blur-xl"
          >
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-danger" />
            <span className="flex-1 leading-relaxed">{toast}</span>
            <button onClick={() => setToast(null)} aria-label="Dismiss" className="text-muted-foreground hover:text-foreground">
              <X className="size-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
      {!connected && state && (
        <div className="fixed right-4 top-20 z-40 rounded-full border border-border bg-card/80 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          reconnecting…
        </div>
      )}
    </main>
  );
}
