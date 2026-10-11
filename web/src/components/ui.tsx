import type { ReactNode } from "react";
import { cx } from "../lib";
import type { Category, TicketStatus } from "../types";

export function Card({ className, children, id }: { className?: string; children: ReactNode; id?: string }) {
  return (
    <section id={id} className={cx("rounded-xl border border-line bg-surface", className)}>
      {children}
    </section>
  );
}

export function CardHeader({ title, meta, icon }: { title: string; meta?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
      <div className="flex items-center gap-2 text-[13px] font-medium text-ink-strong">
        {icon && <span className="text-muted [&>svg]:size-4">{icon}</span>}
        {title}
      </div>
      {meta}
    </div>
  );
}

export type Tone = "red" | "blue" | "green" | "yellow" | "gray";

const TONE: Record<Tone, string> = {
  red: "bg-red-bg text-red-fg",
  blue: "bg-blue-bg text-blue-fg",
  green: "bg-green-bg text-green-fg",
  yellow: "bg-yellow-bg text-yellow-fg",
  gray: "bg-gray-bg text-gray-fg",
};

export function Tag({ tone, children, live }: { tone: Tone; children: ReactNode; live?: boolean }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-[10.5px] font-medium uppercase leading-5 tracking-[0.05em]",
        TONE[tone],
      )}
    >
      {live && <span className="breathe size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

const STATUS: Record<TicketStatus, { label: string; tone: Tone; live?: boolean }> = {
  queued: { label: "Queued", tone: "gray" },
  pending: { label: "Up next", tone: "gray" },
  running: { label: "Working", tone: "blue", live: true },
  resolved: { label: "Resolved", tone: "green" },
  waiting_on_you: { label: "Needs you", tone: "yellow", live: true },
  failed: { label: "Failed", tone: "red" },
};

export function StatusTag({ status }: { status: TicketStatus }) {
  const s = STATUS[status];
  return (
    <Tag tone={s.tone} live={s.live}>
      {s.label}
    </Tag>
  );
}

const CATEGORY: Record<Category, Tone> = {
  context: "blue",
  decision: "yellow",
  execution: "red",
  trajectory: "gray",
};

export function CategoryTag({ category }: { category: Category }) {
  return <Tag tone={CATEGORY[category]}>{category}</Tag>;
}

export function Button({
  children,
  onClick,
  variant = "secondary",
  disabled,
  className,
  type = "button",
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost";
  disabled?: boolean;
  className?: string;
  type?: "button" | "submit";
  title?: string;
}) {
  const styles = {
    primary: "bg-ink-strong text-white hover:bg-[#333333]",
    secondary: "border border-line bg-surface text-ink-strong hover:bg-subtle",
    ghost: "text-muted hover:bg-gray-bg hover:text-ink-strong",
  }[variant];
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-md px-3.5 py-2 text-[13px] font-medium transition-[background-color,color,transform] duration-200 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink-strong/20 disabled:pointer-events-none disabled:opacity-35",
        styles,
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2.5 px-8 py-14 text-center">
      <span className="flex size-10 items-center justify-center rounded-lg border border-line bg-subtle text-muted [&>svg]:size-5">
        {icon}
      </span>
      <p className="text-[15px] font-semibold tracking-[-0.01em] text-ink-strong">{title}</p>
      {children && <p className="max-w-xs text-[13px] leading-relaxed text-muted">{children}</p>}
    </div>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-muted">{children}</p>;
}
