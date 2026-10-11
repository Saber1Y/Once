import { motion } from "motion/react";
import { ArrowsClockwise, PencilSimpleLine, Tray, Wrench } from "@phosphor-icons/react";
import type { Ticket } from "../types";
import { Card, CardHeader, StatusTag } from "./ui";
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
    <Card className="flex max-h-[440px] min-h-0 flex-col overflow-hidden md:max-h-none">
      <CardHeader
        title="Inbox"
        icon={<Tray weight="bold" />}
        meta={<span className="font-mono text-[11px] text-muted">{tickets.length} tickets</span>}
      />
      <ul className="scrollbar-thin min-h-0 flex-1 overflow-y-auto pb-20">
        {tickets.map((t, i) => {
          const fixes = t.latest?.fixes.length ?? 0;
          const active = selected === t.id;
          return (
            <motion.li
              key={t.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
              className="border-b border-line last:border-b-0"
            >
              <button
                onClick={() => onSelect(t.id)}
                className={cx(
                  "relative w-full px-5 py-3.5 text-left transition-colors duration-200 focus-visible:bg-subtle focus-visible:outline-none",
                  active ? "bg-canvas" : "hover:bg-subtle",
                )}
              >
                {active && <span className="absolute inset-y-0 left-0 w-[2px] bg-ink-strong" />}
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[11px] text-faint">{t.id}</span>
                  <StatusTag status={t.status} />
                </div>
                <p className="mt-1 truncate text-[14px] font-medium text-ink-strong">{t.subject}</p>
                <p className="truncate text-[12.5px] text-muted">{t.from}</p>
                {(fixes > 0 || t.latest?.applied_rule || t.source === "custom") && (
                  <div className="mt-2 flex flex-wrap gap-3 text-[11.5px] text-muted">
                    {fixes > 0 && (
                      <span className="inline-flex items-center gap-1">
                        <Wrench weight="bold" className="size-3.5 text-green-fg" /> {fixes} fixed
                      </span>
                    )}
                    {t.latest?.applied_rule && (
                      <span className="inline-flex items-center gap-1">
                        <ArrowsClockwise weight="bold" className="size-3.5 text-yellow-fg" /> your rule
                      </span>
                    )}
                    {t.source === "custom" && (
                      <span className="inline-flex items-center gap-1">
                        <PencilSimpleLine weight="bold" className="size-3.5 text-blue-fg" /> your ticket
                      </span>
                    )}
                  </div>
                )}
              </button>
            </motion.li>
          );
        })}
      </ul>
    </Card>
  );
}
