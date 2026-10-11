import { motion } from "motion/react";
import {
  BookOpen,
  Buildings,
  CheckCircle,
  Code,
  FlowArrow,
  HandPalm,
  Lightning,
  ListChecks,
  Plugs,
  ShieldCheck,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../api";
import { cx } from "../lib";
import type { Integration } from "../types";
import { Card, CardHeader, Empty, Tag } from "./ui";

const BUILT_IN = [
  ["outdated_source", "The answer rests on a help-center article marked outdated; Once repairs the index."],
  ["side_effect_missing", "A write was accepted but reading it back shows it never landed; Once retries and verifies."],
  ["unsupported_amount", "The reply states an amount no tool returned."],
  ["needless_escalation", "The agent asked a person about something no check calls a choice."],
  ["no_reply", "The agent crashed or never finished."],
  ["tier-2 judge", "A cheap model checks specifics only when nothing deterministic fired."],
];

const reveal = (i: number) => ({
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.6, delay: i * 0.08, ease: [0.16, 1, 0.3, 1] as const },
});

function CodeFile({ source }: { source: string }) {
  const ref = useRef<HTMLPreElement>(null);
  const lines = source.replace(/\n$/, "").split("\n");
  let inDoc = false;
  const kinds = lines.map((line) => {
    const quotes = (line.match(/"""/g) ?? []).length;
    const doc = inDoc || quotes > 0;
    if (quotes % 2 === 1) inDoc = !inDoc;
    if (/^\s*# \d\./.test(line)) return "step";
    return doc || /^\s*#/.test(line) ? "comment" : "code";
  });

  useEffect(() => {
    const first = ref.current?.querySelector<HTMLElement>("[data-step]");
    if (ref.current) ref.current.scrollTop = first ? first.offsetTop - 120 : 0;
  }, [source]);

  return (
    <pre ref={ref} className="scrollbar-thin relative min-h-0 flex-1 overflow-auto bg-subtle py-4 font-mono text-[12.5px] leading-[1.7]">
      {lines.map((line, i) => (
        <div key={i} data-step={kinds[i] === "step" ? "" : undefined} className={cx("flex pr-6", kinds[i] === "step" && "bg-yellow-bg/70")}>
          <span className="w-12 shrink-0 select-none pr-4 text-right text-faint">{i + 1}</span>
          <code
            className={cx(
              "whitespace-pre",
              kinds[i] === "step" ? "font-medium text-yellow-fg" : kinds[i] === "comment" ? "text-muted" : "text-ink-strong",
            )}
          >
            {line || " "}
          </code>
        </div>
      ))}
    </pre>
  );
}

function Section({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="border-t border-line px-5 py-4 first:border-t-0">
      <p className="flex items-center gap-2 text-[12.5px] font-medium text-ink-strong">
        <span className="text-muted [&>svg]:size-4">{icon}</span>
        {title}
      </p>
      <div className="mt-2.5">{children}</div>
    </div>
  );
}

export function IntegrationView() {
  const [data, setData] = useState<Integration | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState("integration.py");

  useEffect(() => {
    api
      .integration()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  if (error) {
    return (
      <Card>
        <Empty icon={<Plugs weight="bold" />} title="Couldn't load the integration">
          {error}
        </Empty>
      </Card>
    );
  }
  if (!data) return null;

  const cfg = data.config;
  const files = Object.keys(data.files);
  const boundary = Object.entries(cfg.choice_boundary ?? {});

  return (
    <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)_340px]">
      <motion.div {...reveal(0)} className="space-y-4">
        <Card>
          <div className="px-5 pb-5 pt-5">
            <div className="flex items-center justify-between">
              <span className="flex size-10 items-center justify-center rounded-lg border border-line bg-subtle text-ink-strong">
                <Buildings weight="bold" className="size-5" />
              </span>
              <Tag tone="green">Connected</Tag>
            </div>
            <h2 className="mt-4 text-[28px] font-semibold leading-none tracking-[-0.03em] text-ink-strong">{data.company}</h2>
            <p className="mt-2 text-[13.5px] leading-relaxed text-muted">{cfg.about}</p>
            <p className="mt-3 font-mono text-[11px] text-faint">module {data.module}</p>
          </div>
          <Section icon={<Plugs weight="bold" />} title="Systems Once reads">
            <ul className="space-y-2.5">
              {(cfg.systems ?? []).map((s) => (
                <li key={s.name} className="flex gap-2.5 text-[13px]">
                  <CheckCircle weight="fill" className="mt-0.5 size-4 shrink-0 text-green-fg" />
                  <span>
                    <span className="font-medium text-ink-strong">{s.name}</span>
                    <span className="block leading-snug text-muted">{s.role}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Section>
          <Section icon={<HandPalm weight="bold" />} title="Where policy ends and a person decides">
            {boundary.map(([domain, limits]) => (
              <div key={domain} className="text-[13px] leading-relaxed text-muted">
                <code className="rounded bg-gray-bg px-1.5 py-0.5 font-mono text-[11px] text-gray-fg">{domain}</code>
                <ul className="mt-1.5 space-y-0.5">
                  {Object.entries(limits).map(([k, v]) => (
                    <li key={k}>
                      {k.split("_").join(" ")}: <span className="font-mono text-ink-strong">{v}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            <p className="mt-2 text-[12.5px] text-muted">
              Decided by {cfg.decisions?.decided_by ?? "the support lead"} in the {cfg.decisions?.channel ?? "console"}.
            </p>
          </Section>
        </Card>
      </motion.div>

      <motion.div {...reveal(1)} className="min-w-0">
        <Card className="flex h-[720px] flex-col overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
            <div className="flex items-center gap-2 text-[13px] font-medium text-ink-strong">
              <Code weight="bold" className="size-4 text-muted" /> How {data.company} plugs its agent into Once
            </div>
            <span className="hidden font-mono text-[11px] text-faint md:inline">examples/acme/</span>
          </div>
          <div className="scrollbar-thin flex gap-1 overflow-x-auto border-b border-line px-3 py-2">
            {files.map((name) => (
              <button
                key={name}
                onClick={() => setFile(name)}
                className={cx(
                  "whitespace-nowrap rounded-md px-2.5 py-1 font-mono text-[12px] transition-colors",
                  file === name ? "bg-ink-strong text-white" : "text-muted hover:bg-gray-bg hover:text-ink-strong",
                )}
              >
                {name}
              </button>
            ))}
          </div>
          <CodeFile source={data.files[file] ?? ""} />
        </Card>
      </motion.div>

      <motion.div {...reveal(2)} className="space-y-4">
        <Card>
          <CardHeader title="What Once now guards" icon={<ShieldCheck weight="bold" />} />
          <Section icon={<Lightning weight="bold" />} title="Writes, each read back after commit">
            <ul className="space-y-1.5">
              {data.actions.map((a) => (
                <li key={a.name} className="flex items-start justify-between gap-3 text-[13px]">
                  <span>
                    <code className="font-mono text-[12px] text-ink-strong">{a.name}</code>
                    <span className="block leading-snug text-muted">{a.description}</span>
                  </span>
                  {a.verify && <Tag tone="green">read-back</Tag>}
                </li>
              ))}
            </ul>
          </Section>
          <Section icon={<ListChecks weight="bold" />} title={`${data.company}'s own checks`}>
            <ul className="space-y-1.5">
              {data.checks.map((c) => (
                <li key={c.name} className="text-[13px]">
                  <code className="font-mono text-[12px] text-ink-strong">{c.name}</code>
                  <span className="block leading-snug text-muted">{c.description}</span>
                </li>
              ))}
            </ul>
          </Section>
          <Section icon={<BookOpen weight="bold" />} title="Built into Once, for every company">
            <ul className="space-y-1.5">
              {BUILT_IN.map(([name, desc]) => (
                <li key={name} className="text-[13px]">
                  <code className="font-mono text-[12px] text-ink-strong">{name}</code>
                  <span className="block leading-snug text-muted">{desc}</span>
                </li>
              ))}
            </ul>
          </Section>
        </Card>
        <Card>
          <CardHeader title="Distinctive cases" icon={<FlowArrow weight="bold" />} meta={<Tag tone="gray">{data.cases.length}</Tag>} />
          <ul className="px-5 py-2">
            {data.cases.map((c) => (
              <li key={c.id} className="border-b border-line py-2.5 last:border-b-0">
                <p className="text-[13px] text-ink-strong">
                  <span className="mr-1.5 font-mono text-[11px] text-faint">{c.id}</span>
                  {c.title}
                </p>
                <p className="text-[12px] leading-snug text-muted">{c.why}</p>
              </li>
            ))}
          </ul>
        </Card>
      </motion.div>
    </div>
  );
}
