import { motion } from "motion/react";
import { Inbox, Repeat2, Sparkles, Wrench } from "lucide-react";
import type { Ticket } from "../types";
import { HudLabel, Panel, StatusTag } from "./ui";
import { cx } from "../lib";

export function Queue({
  tickets,
  selected,
  onSelect,
}: {
  tickets: Ticket[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <Panel className="flex min-h-0 flex-col">
      <div className="border-b border-border px-4 py-3.5">
        <HudLabel icon={<Inbox />} right={<span className="font-mono text-[10px] text-muted-foreground">{tickets.length}</span>}>
          Ticket queue
        </HudLabel>
      </div>
      <ul className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-2">
        {tickets.map((t, i) => {
          const fixes = t.latest?.fixes.length ?? 0;
          return (
            <motion.li
              key={t.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <button
                onClick={() => onSelect(t.id)}
                className={cx(
                  "group w-full rounded-xl border px-3 py-2.5 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
                  selected === t.id
                    ? "border-primary/30 bg-primary/[0.06]"
                    : "border-transparent hover:border-border hover:bg-muted/40",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[10px] text-muted-foreground">{t.id}</span>
                  <StatusTag status={t.status} />
                </div>
                <p className="mt-1 truncate text-sm font-medium">{t.subject}</p>
                <p className="truncate text-xs text-muted-foreground">{t.from}</p>
                {(fixes > 0 || t.latest?.applied_rule || t.source === "custom") && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {fixes > 0 && (
                      <span className="inline-flex items-center gap-1 font-mono text-[9px] uppercase tracking-[0.12em] text-primary">
                        <Wrench className="size-3" /> fixed {fixes}
                      </span>
                    )}
                    {t.latest?.applied_rule && (
                      <span className="inline-flex items-center gap-1 font-mono text-[9px] uppercase tracking-[0.12em] text-warn">
                        <Repeat2 className="size-3" /> your rule
                      </span>
                    )}
                    {t.source === "custom" && (
                      <span className="inline-flex items-center gap-1 font-mono text-[9px] uppercase tracking-[0.12em] text-info">
                        <Sparkles className="size-3" /> your ticket
                      </span>
                    )}
                  </div>
                )}
              </button>
            </motion.li>
          );
        })}
      </ul>
    </Panel>
  );
}
