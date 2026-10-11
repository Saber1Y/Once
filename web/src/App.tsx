import { AnimatePresence, motion } from "motion/react";
import { ArrowCounterClockwise, Key, PaperPlaneRight, Play, WarningCircle, X } from "@phosphor-icons/react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api, useDesk } from "./api";
import { EventLog } from "./components/EventLog";
import { Queue } from "./components/Queue";
import { Decisions, DriftBoard, Memory } from "./components/SidePanels";
import { IntegrationView } from "./components/IntegrationView";
import { TicketDetail } from "./components/TicketDetail";
import { Button, Tag } from "./components/ui";
import { cx } from "./lib";

const reveal = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
};

function Metric({ label, value, hint, tone }: { label: string; value: string | number; hint?: string; tone?: string }) {
  return (
    <div className="sm:px-5 sm:first:pl-0" title={hint}>
      <p className="text-[12px] text-muted">{label}</p>
      <p className={cx("tabular mt-1.5 font-mono text-[28px] font-medium leading-none tracking-[-0.03em] text-ink-strong", tone)}>{value}</p>
    </div>
  );
}

export default function App() {
  const { state, events, connected, error } = useDesk();
  const [selected, setSelected] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [composer, setComposer] = useState("");
  const [view, setView] = useState<"desk" | "integration">("desk");

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
    <main className="relative min-h-[100dvh] overflow-x-hidden pb-28">
      <div aria-hidden className="ambient" />

      <header className="sticky top-0 z-50 border-b border-line bg-canvas/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-3 px-4 py-3 md:px-8">
          <div className="flex items-center gap-5">
            <span className="flex items-center gap-2 text-[17px] font-semibold tracking-[-0.02em] text-ink-strong"><span className="size-2.5 rounded-[3px] bg-ink-strong" />Once</span>
            <nav className="flex items-center gap-1 text-[13px]" aria-label="Views">
              {(
                [
                  ["desk", `${state?.company ?? ""} desk`],
                  ["integration", "Integration"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setView(key)}
                  aria-current={view === key ? "page" : undefined}
                  className={cx(
                    "rounded-md px-2.5 py-1 font-medium transition-colors",
                    view === key ? "bg-gray-bg text-ink-strong" : "text-muted hover:text-ink-strong",
                  )}
                >
                  {label}
                </button>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <span
              className="hidden sm:inline-flex"
              title={state?.tracing.exporting ? "Traces export to neatlogs" : "Set NEATLOGS_API_KEY to export traces"}
            >
              <Tag tone={state?.tracing.exporting ? "green" : "gray"} live={state?.tracing.exporting && busy}>
                {state?.tracing.exporting ? "neatlogs live" : "traces local only"}
              </Tag>
            </span>
            <Button variant="ghost" onClick={call(api.reset)} title="Reset the demo" disabled={busy}>
              <ArrowCounterClockwise weight="bold" className="size-3.5" /> <span className="hidden sm:inline">Reset</span>
            </Button>
            <Button variant="primary" onClick={call(api.runQueue)} disabled={!ready || busy || !queued}>
              <Play weight="fill" className="size-3.5" /> {busy ? "Working" : "Run queue"}
            </Button>
          </div>
        </div>
      </header>

      <div className="relative mx-auto max-w-[1400px] px-4 md:px-8">
        <motion.section
          {...reveal}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="flex flex-col gap-8 py-12 md:py-16 xl:flex-row xl:items-end xl:justify-between"
        >
          <div className="max-w-3xl">
            <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-muted">
              {view === "desk" ? `Guarding ${state?.company ?? ""}'s support agent` : `${state?.company ?? ""} is connected`}
            </p>
            {view === "desk" ? (
              <h1 className="mt-3 text-[38px] font-semibold leading-[1.08] tracking-[-0.035em] text-ink-strong md:text-[56px]">
                Fixes what's mechanical.
                <br />
                <span className="text-faint">Asks what's a choice. Only needs you once.</span>
              </h1>
            ) : (
              <>
                <h1 className="mt-3 text-[38px] font-semibold leading-[1.08] tracking-[-0.035em] text-ink-strong md:text-[56px]">
                  {state?.company}'s agent,
                  <br />
                  <span className="text-faint">now behind Once.</span>
                </h1>
                <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-muted">
                  Five steps in one file: point Once at the help center, hand it the agent, register each write with a
                  read-back, add business checks, and list the trade-offs worth protecting.
                </p>
              </>
            )}
          </div>
          <div className="grid grid-cols-3 gap-x-4 gap-y-5 sm:flex sm:shrink-0 sm:gap-0 sm:divide-x sm:divide-line">
            <Metric label="Resolved" value={stats?.resolved ?? 0} />
            <Metric
              label="Fixed alone"
              value={stats ? `${stats.fixed_verified}/${stats.fixed_alone}` : "0"}
              hint="Verified / applied"
              tone="text-green-fg"
            />
            <Metric label="Asked you" value={stats?.asked ?? 0} />
            <Metric label="Rules" value={stats?.rules ?? 0} />
            <Metric
              label="Reused"
              value={stats?.rule_reuses ?? 0}
              hint="Later tickets resolved with a remembered rule"
              tone="text-yellow-fg"
            />
          </div>
        </motion.section>

        {state && !ready && (
          <div className="mb-6 flex items-start gap-3 rounded-lg bg-yellow-bg px-4 py-3 text-[13.5px] text-yellow-fg">
            <Key weight="bold" className="mt-0.5 size-4 shrink-0" />
            <p className="leading-relaxed">
              <span className="font-medium">No model configured.</span> Add <code className="font-mono">LLM_API_KEY</code>,{" "}
              <code className="font-mono">LLM_BASE_URL</code> and <code className="font-mono">ONCE_MODEL</code> to{" "}
              <code className="font-mono">.env</code>, then restart the server. Nothing here is simulated, so nothing runs
              without a model.
            </p>
          </div>
        )}
        {error && (
          <div className="mb-6 flex items-center gap-3 rounded-lg bg-red-bg px-4 py-3 text-[13.5px] text-red-fg">
            <WarningCircle weight="bold" className="size-4" /> Can't reach the Once API: {error}
          </div>
        )}

        {view === "integration" ? (
          <IntegrationView />
        ) : (
        <>
        <motion.div
          {...reveal}
          transition={{ duration: 0.6, delay: 0.08, ease: [0.16, 1, 0.3, 1] }}
          className="grid gap-4 md:grid-cols-[260px_minmax(0,1fr)] md:[&>*:nth-child(-n+2)]:h-[680px] xl:h-[calc(100dvh-140px)] xl:min-h-[600px] xl:grid-cols-[280px_minmax(0,1fr)_380px] xl:[&>*:nth-child(-n+2)]:h-auto"
        >
          <Queue tickets={tickets} selected={selected} onSelect={setSelected} />
          <TicketDetail
            ticket={ticket}
            events={events}
            canRun={ready && !busy}
            onRun={(id) => call(() => api.runTicket(id))()}
            onJumpToDecision={() => document.getElementById("decisions")?.scrollIntoView({ behavior: "smooth" })}
          />
          <div className="scrollbar-thin grid gap-4 md:col-span-2 md:grid-cols-2 md:items-start xl:col-span-1 xl:block xl:min-h-0 xl:space-y-4 xl:overflow-y-auto xl:pb-20">
            <Decisions decisions={state?.decisions ?? []} onError={setToast} />
            <DriftBoard drift={state?.drift ?? null} events={events} canRun={ready && !busy} onRun={call(api.drift)} />
            <Memory rules={state?.policies ?? []} index={state?.index ?? []} />
          </div>
        </motion.div>

        <motion.div {...reveal} transition={{ duration: 0.6, delay: 0.16, ease: [0.16, 1, 0.3, 1] }} className="mt-4">
          <EventLog events={events} />
        </motion.div>
        </>
        )}
      </div>

      <form
        onSubmit={submitTicket}
        className="fixed bottom-5 left-1/2 z-40 flex w-[min(720px,calc(100vw-2rem))] -translate-x-1/2 items-center gap-3 rounded-lg border border-line bg-surface py-1.5 pl-4 pr-1.5 shadow-[0_2px_12px_rgba(0,0,0,0.04)] focus-within:border-ink-strong/40"
      >
        <span className="hidden whitespace-nowrap font-mono text-[11px] text-faint sm:inline">as priya@</span>
        <input
          value={composer}
          onChange={(e) => setComposer(e.target.value)}
          placeholder="Write your own ticket and watch Once handle it"
          aria-label="New ticket"
          maxLength={4000}
          className="min-w-0 flex-1 bg-transparent py-2 text-[14px] text-ink-strong placeholder:text-faint focus:outline-none"
        />
        <Button type="submit" variant="primary" className="px-3" disabled={!ready || !composer.trim()} title="Send ticket">
          <PaperPlaneRight weight="fill" className="size-4" />
        </Button>
      </form>

      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            className="fixed bottom-24 left-1/2 z-50 flex w-[min(520px,calc(100vw-2rem))] -translate-x-1/2 items-start gap-3 rounded-lg border border-line bg-surface px-4 py-3 text-[13.5px] shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
          >
            <WarningCircle weight="bold" className="mt-0.5 size-4 shrink-0 text-red-fg" />
            <span className="flex-1 leading-relaxed text-ink">{toast}</span>
            <button onClick={() => setToast(null)} aria-label="Dismiss" className="text-muted hover:text-ink-strong">
              <X weight="bold" className="size-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
      {!connected && state && (
        <div className="fixed right-4 top-16 z-40">
          <Tag tone="gray">reconnecting</Tag>
        </div>
      )}
    </main>
  );
}
