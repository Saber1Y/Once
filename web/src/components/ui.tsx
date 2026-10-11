import type { ReactNode } from "react";
import { cx } from "../lib";
import type { Category, TicketStatus } from "../types";

export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <section
      className={cx(
        "rounded-2xl border border-border bg-card/65 shadow-2xl shadow-black/20 backdrop-blur-xl",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function HudLabel({ icon, children, right }: { icon?: ReactNode; children: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
        {icon && <span className="text-primary [&>svg]:size-3.5">{icon}</span>}
        {children}
      </div>
      {right}
    </div>
  );
}

const STATUS: Record<TicketStatus, { label: string; dot: string; text: string; pulse?: boolean }> = {
  queued: { label: "Queued", dot: "bg-muted-foreground/50", text: "text-muted-foreground" },
  pending: { label: "Up next", dot: "bg-info", text: "text-info" },
  running: { label: "Working", dot: "bg-primary", text: "text-primary", pulse: true },
  resolved: { label: "Resolved", dot: "bg-primary", text: "text-foreground" },
  waiting_on_you: { label: "Needs you", dot: "bg-warn", text: "text-warn", pulse: true },
  failed: { label: "Failed", dot: "bg-danger", text: "text-danger" },
};

export function Dot({ className, pulse }: { className: string; pulse?: boolean }) {
  return (
    <span className="relative flex size-1.5 shrink-0">
      {pulse && <span className={cx("absolute inline-flex size-full animate-ping rounded-full opacity-60", className)} />}
      <span className={cx("relative inline-flex size-1.5 rounded-full", className)} />
    </span>
  );
}

export function StatusTag({ status }: { status: TicketStatus }) {
  const s = STATUS[status];
  return (
    <span className={cx("inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em]", s.text)}>
      <Dot className={s.dot} pulse={s.pulse} />
      {s.label}
    </span>
  );
}

const CATEGORY: Record<Category, string> = {
  context: "text-info border-info/30 bg-info/10",
  decision: "text-warn border-warn/30 bg-warn/10",
  execution: "text-danger border-danger/30 bg-danger/10",
  trajectory: "text-agent border-agent/30 bg-agent/10",
};

export function CategoryTag({ category }: { category: Category }) {
  return (
    <span
      className={cx(
        "rounded-md border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em]",
        CATEGORY[category],
      )}
    >
      {category}
    </span>
  );
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
    primary:
      "bg-primary text-primary-foreground shadow-[0_0_20px_rgba(200,245,106,0.2)] hover:-translate-y-0.5 hover:shadow-[0_0_32px_rgba(200,245,106,0.35)]",
    secondary: "border border-border text-foreground hover:bg-muted/60",
    ghost: "text-muted-foreground hover:text-foreground hover:bg-muted/40",
  }[variant];
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-all duration-200 active:translate-y-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/70 disabled:pointer-events-none disabled:opacity-40",
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
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
      <span className="flex size-10 items-center justify-center rounded-xl border border-border bg-muted/40 text-muted-foreground [&>svg]:size-4">
        {icon}
      </span>
      <p className="text-sm font-medium">{title}</p>
      {children && <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">{children}</p>}
    </div>
  );
}
