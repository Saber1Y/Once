export type Category = "context" | "decision" | "execution" | "trajectory";

export interface Step {
  id: string;
  kind: "tool" | "commit" | "verify" | "llm";
  name: string;
  args: Record<string, unknown>;
  result: unknown;
  ok: boolean;
  duration_ms: number;
}

export interface Finding {
  code: string;
  category: Category;
  route: "mechanical" | "choice";
  title: string;
  detail: string;
  evidence: string[];
  data: Record<string, unknown>;
  tier: "deterministic" | "judge";
}

export interface AttemptRecord {
  number: number;
  steps: Step[];
  staged: Record<string, unknown>[];
  draft: string;
  decision_request: { question: string; options: string[] } | null;
  findings: Finding[];
  post_commit?: Finding[];
  judge?: Finding[];
}

export interface Fix {
  attempt: number;
  code: string;
  category: Category;
  title: string;
  action: string;
  verified: boolean;
  verified_by?: string;
}

export interface Run {
  ticket_id: string;
  status: TicketStatus;
  trace_id: string | null;
  trace_url: string | null;
  attempts: AttemptRecord[];
  fixes: Fix[];
  commits: { action: Record<string, unknown>; result: Record<string, unknown>; ok: boolean; step_id: string }[];
  reply: string;
  applied_rule: string | null;
  error: string | null;
}

export type TicketStatus = "queued" | "pending" | "running" | "resolved" | "waiting_on_you" | "failed";

export interface Ticket {
  id: string;
  from: string;
  subject: string;
  body: string;
  status: TicketStatus;
  source: "seed" | "custom";
  latest: Run | null;
  runs: number;
}

export interface DriftResult {
  id: string;
  title: string;
  why: string;
  passed: boolean;
  detail: string;
  status: string;
  trace_url: string | null;
  fixes: number;
}

export interface Drift {
  passed: number;
  total: number;
  results: DriftResult[];
  at?: string;
  rule?: string | null;
}

export interface Rule {
  id: string;
  version: number;
  min_tenure_years: number;
  max_days_over: number;
  outcome: "refund" | "store_credit" | "decline";
  question: string;
  source_ticket: string;
  decided_by: string;
  status: "active" | "held" | "candidate";
  created_at: string;
  held_reason: string | null;
  describe: string;
}

export interface Decision {
  id: string;
  ticket_id: string;
  status: "open" | "checking" | "answering" | "answered" | "held";
  question: string;
  why: string;
  facts: {
    customer: string;
    plan: string;
    tenure_years: number;
    product: string;
    amount: number;
    days_since_purchase: number;
    window_days: number;
    days_over: number;
  };
  evidence: Step[];
  options: { value: Rule["outcome"]; label: string }[];
  suggested_scope: { min_tenure_years: number; max_days_over: number };
  trace_url: string | null;
  attempts: { rule: Rule; drift: Drift; at: string }[];
  scope?: "once" | "always";
  rule?: Rule;
}

export interface Stats {
  resolved: number;
  waiting: number;
  fixed_alone: number;
  fixed_verified: number;
  asked: number;
  rules: number;
  rule_reuses: number;
}

export interface DeskState {
  tickets: Ticket[];
  decisions: Decision[];
  policies: Rule[];
  index: string[];
  drift: Drift | null;
  stats: Stats;
  tracing: { exporting: boolean; dashboard: string; readback: boolean };
  busy: boolean;
  llm_ready: boolean;
  today: string;
}

export interface DeskEvent {
  id: number;
  type: string;
  ts: number;
  ticket_id?: string;
  [key: string]: unknown;
}
