import React, { useEffect, useRef, useState } from "react";
import {
  AuthExpiredError,
  AuthUser,
  ChatReply,
  Lang,
  fetchChatStarters,
  fetchMe,
  sendChat,
} from "../api/gujrera";
import { AccountBar } from "./AccountBar";
import { AnalyticsCard, AnalyticsCardData } from "./AnalyticsCard";

const TOKEN_KEY = "gujrera.token";

function readToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage unavailable: the login lasts for this page view only
  }
}

const SUMMARY_PROMPT: Record<Lang, string> = {
  en: "Show my compliance summary",
  gu: "મારો અનુપાલન સારાંશ બતાવો",
  hi: "मेरा अनुपालन सारांश दिखाएँ",
};

const ROLE_SUGGESTIONS: Record<string, string[]> = {
  developer: ["What are my dues?", "Pending notices for my projects", "My QPR filings", "My registration expiry"],
  agent: ["My registration status", "My complaints"],
  citizen: ["My complaints", "File a complaint"],
  officer: [
    "Which promoters have the most delayed projects?",
    "Complaints by category",
    "Oldest open complaints",
    "Lapsed or soon-ending registrations",
  ],
};

type Message = { role: "user"; text: string } | { role: "assistant"; reply: ChatReply };

const LANG_CHOICES: { id: Lang | null; label: string }[] = [
  { id: null, label: "Auto" },
  { id: "gu", label: "ગુજરાતી" },
  { id: "hi", label: "हिन्दी" },
  { id: "en", label: "English" },
];

const SOURCE_LABEL: Record<string, string> = {
  project: "Project registration",
  promoter: "Promoter record",
  promoter_scorecard: "Promoter scorecard",
  progress_report: "Quarterly progress report",
  approval: "Approval",
  complaint_stats: "Complaint statistics",
  order: "Order",
  agent: "Agent registration",
};

const VERDICT_TONE: Record<string, string> = {
  verified: "border-emerald-300 bg-emerald-50 text-emerald-950 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-100",
  registered_with_warnings: "border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100",
};
const RED = "border-red-300 bg-red-50 text-red-950 dark:border-red-800 dark:bg-red-950/40 dark:text-red-100";

function fmt(v: unknown): string {
  return v === null || v === undefined || v === "" ? "—" : String(v);
}

/** Render "text [1] more [2]" with the markers as small citation chips. */
const CitedText: React.FC<{ text: string }> = ({ text }) => {
  const parts = text.split(/(\[\d+\])/g);
  return (
    <p className="text-sm leading-relaxed whitespace-pre-wrap">
      {parts.map((part, i) => {
        const m = part.match(/^\[(\d+)\]$/);
        return m ? (
          <sup key={i} className="mx-0.5 text-[10px] font-bold px-1 rounded bg-accent-surface text-accent-strong border border-accent-border">
            {m[1]}
          </sup>
        ) : (
          <React.Fragment key={i}>{part}</React.Fragment>
        );
      })}
    </p>
  );
};

const Card: React.FC<{ card: ChatReply["cards"][number] }> = ({ card }) => {
  if (card.type === "project") {
    return (
      <div className="mt-3 rounded-lg border border-warm-border bg-subtle p-3 text-xs grid grid-cols-2 gap-2">
        <div className="col-span-2 font-mono break-all text-body">{fmt(card.rera_no)}</div>
        <div><span className="text-muted">Status </span><span className="capitalize">{fmt(card.status)}</span></div>
        <div><span className="text-muted">Valid until </span>{fmt(card.reg_valid_until)}</div>
        <div><span className="text-muted">Promoter </span>{fmt(card.promoter_name)}</div>
        <div><span className="text-muted">Delay </span>{Number(card.delay_days) > 0 ? `${card.delay_days} days` : "None"}</div>
      </div>
    );
  }
  if (card.type === "promoter") {
    const projects = (card.project_list as Array<Record<string, unknown>>) ?? [];
    return (
      <div className="mt-3 rounded-lg border border-warm-border bg-subtle p-3 text-xs">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2">
          {[
            ["Projects", card.projects],
            ["Delayed", card.delayed_projects],
            ["Open complaints", card.complaints_open],
            ["Adverse orders", card.adverse_orders],
          ].map(([k, v]) => (
            <div key={String(k)}>
              <div className="text-muted">{String(k)}</div>
              <div className="font-heading text-base font-bold text-body">{fmt(v)}</div>
            </div>
          ))}
        </div>
        <ul className="divide-y divide-warm-border">
          {projects.map((p) => (
            <li key={String(p.rera_no)} className="py-1 flex flex-wrap gap-x-2">
              <span className="font-semibold text-body">{fmt(p.name)}</span>
              <span className="text-muted capitalize">{fmt(p.status)}</span>
              {Number(p.delay_days) > 0 && <span className="text-amber-700 dark:text-amber-300">{fmt(p.delay_days)} days late</span>}
            </li>
          ))}
        </ul>
      </div>
    );
  }
  if (card.type === "legal") {
    const hits = (card.hits as { label: string; title: string; excerpt: string; page: number | null }[]) ?? [];
    return (
      <div className="mt-3 rounded-lg border border-warm-border bg-subtle p-3 text-xs flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-body">Provisions used</span>
          <span className="px-2 py-0.5 rounded-full border border-warm-border text-[10px] text-muted">
            {card.summary_by === "llm" ? "AI summary, checked against these provisions" : "Quoted from the law"}
          </span>
        </div>
        {hits.map((h) => (
          <details key={h.label} className="rounded-md border border-warm-border bg-card px-2.5 py-1.5">
            <summary className="cursor-pointer">
              <span className="font-semibold text-body">{h.label}</span>
              <span className="text-muted"> · {h.title}{h.page ? ` · p. ${h.page}` : ""}</span>
            </summary>
            <p className="mt-1 text-muted whitespace-pre-wrap">{h.excerpt}</p>
          </details>
        ))}
        <p className="text-muted">Source: RERA Act, 2016 and Gujarat RERA General Rules, 2017 (GUJRERA website). The Act copy is a scan read by OCR; check the official text before relying on it.</p>
      </div>
    );
  }
  if (card.type === "analytics") {
    return <AnalyticsCard card={card as unknown as AnalyticsCardData} />;
  }
  if (card.type === "self_service") {
    const dues = (card.dues as { description: string; amount: number | null; due_date: string; overdue: boolean }[]) ?? [];
    const regs = (card.registrations as { project: string; valid_until: string; days_left: number }[]) ?? [];
    const qpr = (card.qpr_missing as { project: string; quarters: string[] }[]) ?? [];
    if (card.role === "agent") {
      return (
        <div className="mt-3 rounded-lg border border-warm-border bg-subtle p-3 text-xs grid grid-cols-2 gap-2">
          <div className="col-span-2 font-mono break-all">{fmt(card.reg_no)}</div>
          <div><span className="text-muted">Status </span><span className="capitalize">{fmt(card.status)}</span></div>
          <div><span className="text-muted">Valid until </span>{fmt(card.valid_until)}</div>
        </div>
      );
    }
    return (
      <div className="mt-3 rounded-lg border border-warm-border bg-subtle p-3 text-xs flex flex-col gap-3">
        {dues.length > 0 && (
          <div>
            <div className="font-semibold text-body mb-1">Pending dues</div>
            <ul className="divide-y divide-warm-border">
              {dues.map((d, i) => (
                <li key={i} className="py-1 flex flex-wrap gap-x-2 justify-between">
                  <span className="text-body">{d.description}</span>
                  <span className="whitespace-nowrap">
                    {d.amount ? `₹${d.amount.toLocaleString("en-IN")}` : "—"} · due {d.due_date}
                    {d.overdue && <span className="ml-1 px-1.5 rounded bg-red-600 text-white">overdue</span>}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {qpr.length > 0 && (
          <div>
            <div className="font-semibold text-body mb-1">Quarterly reports not filed</div>
            {qpr.map((q) => (
              <div key={q.project} className="text-body">{q.project}: <span className="text-muted">{q.quarters.join(", ")}</span></div>
            ))}
          </div>
        )}
        {regs.length > 0 && (
          <div>
            <div className="font-semibold text-body mb-1">Registrations</div>
            {regs.map((r) => (
              <div key={r.project} className="flex justify-between gap-2">
                <span className="text-body">{r.project}</span>
                <span className={r.days_left < 0 ? "text-red-700 dark:text-red-300" : r.days_left <= 180 ? "text-amber-700 dark:text-amber-300" : "text-muted"}>
                  until {r.valid_until} ({r.days_left < 0 ? "ended" : `${r.days_left} days`})
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }
  if (card.type === "complaint_draft") {
    const fields = (card.fields as { key: string; label: string; value: string }[]) ?? [];
    return (
      <div className="mt-3 rounded-lg border border-warm-border bg-subtle p-3 text-xs">
        <div className="flex items-center justify-between mb-2">
          <span className="font-heading text-sm font-bold text-body">Form {String(card.form)}</span>
          <span className="text-[10px] px-2 py-0.5 rounded-full border border-warm-border text-muted">Draft · not sent</span>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
          {fields.map((f) => (
            <React.Fragment key={f.key}>
              <dt className="text-muted">{f.label}</dt>
              <dd className="text-body break-words whitespace-pre-wrap">{f.value}</dd>
            </React.Fragment>
          ))}
        </dl>
      </div>
    );
  }
  if (card.type === "complaint_submitted") {
    return <SubmittedCard refNo={String(card.ref_no)} code={String(card.tracking_code)} form={String(card.form)} />;
  }
  if (card.type === "complaint_status") {
    const events = (card.events as { at: string; status: string; note: string | null }[]) ?? [];
    return (
      <div className="mt-3 rounded-lg border border-warm-border bg-subtle p-3 text-xs">
        <div className="font-mono text-body mb-2">{String(card.ref_no)}</div>
        <ol className="relative border-l border-warm-border ml-1.5 flex flex-col gap-2">
          {events.map((e, i) => (
            <li key={i} className="ml-3">
              <span className={`absolute -left-[5px] mt-1 w-2.5 h-2.5 rounded-full ${i === events.length - 1 ? "bg-accent-amber" : "bg-muted/50"}`} />
              <div className="font-semibold text-body capitalize">{e.status}</div>
              <div className="text-muted">{e.at}{e.note ? ` · ${e.note}` : ""}</div>
            </li>
          ))}
        </ol>
      </div>
    );
  }
  if (card.type === "trust") {
    const verdict = String(card.verdict);
    const problems = (card.problems as string[]) ?? [];
    return (
      <div className={`mt-3 rounded-lg border p-3 text-xs ${VERDICT_TONE[verdict] ?? RED}`}>
        <div className="font-bold uppercase tracking-wide mb-1">{verdict.replace(/_/g, " ")}</div>
        {problems.length > 0 && (
          <ul className="list-disc pl-4">
            {problems.map((p) => <li key={p}>{p}</li>)}
          </ul>
        )}
        <div className="mt-1 opacity-80">Open the RERA check tab for the full report.</div>
      </div>
    );
  }
  return null;
};

const SubmittedCard: React.FC<{ refNo: string; code: string; form: string }> = ({ refNo, code, form }) => {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard
      ?.writeText(`${refNo} ${code}`)
      .then(() => setCopied(true))
      .catch(() => setCopied(false));
  };
  return (
    <div className="mt-3 rounded-lg border border-emerald-300 bg-emerald-50 text-emerald-950 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-100 p-3 text-xs">
      <div className="font-bold uppercase tracking-wide mb-2">Complaint filed · Form {form}</div>
      <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <span className="opacity-80">Reference</span>
        <span className="font-mono font-bold break-all">{refNo}</span>
        <span className="opacity-80">Tracking code</span>
        <span className="font-mono font-bold text-base tracking-widest">{code}</span>
      </div>
      <button type="button" onClick={copy} className="mt-2 px-2.5 py-1 rounded-md border border-current text-[11px] font-semibold">
        {copied ? "Copied" : "Copy both"}
      </button>
    </div>
  );
};

export const AskPage: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [lang, setLang] = useState<Lang | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [starters, setStarters] = useState<{ lang: Lang; text: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const [token, setToken] = useState<string | null>(() => readToken());
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    if (!token) return;
    fetchMe(token)
      .then((r) => setUser(r.user))
      .catch(() => {
        setToken(null);
        writeToken(null);
      });
  }, [token]);

  useEffect(() => {
    fetchChatStarters().then((r) => setStarters(r.items)).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const send = async (text: string, shown?: string, as: { token: string | null; sessionId: string | null } = { token, sessionId }) => {
    const message = text.trim();
    if (!message || busy) return;
    setInput("");
    setError(null);
    setMessages((m) => [...m, { role: "user", text: shown ?? message }]);
    setBusy(true);
    try {
      const reply = await sendChat(message, as.sessionId, lang, as.token);
      setSessionId(reply.session_id);
      setMessages((m) => [...m, { role: "assistant", reply }]);
    } catch (e) {
      if (e instanceof AuthExpiredError) {
        logout();
      }
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    writeToken(null);
    setMessages([]);
    setSessionId(null);
  };

  const onLogin = (newToken: string, newUser: AuthUser) => {
    setToken(newToken);
    setUser(newUser);
    writeToken(newToken);
    setMessages([]);
    setSessionId(null);
    if (newUser.role === "developer" || newUser.role === "agent") {
      const l = lang ?? newUser.preferred_lang;
      void send(SUMMARY_PROMPT[l], undefined, { token: newToken, sessionId: null });
    }
  };

  const last = [...messages].reverse().find((m) => m.role === "assistant") as
    | { role: "assistant"; reply: ChatReply }
    | undefined;

  return (
    <div className="max-w-3xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-heading text-lg font-bold text-body">Ask GUJRERA</h2>
          <p className="text-sm text-muted">
            Ask about a project, builder or agent in Gujarati, Hindi or English. Every answer cites the registry
            record it comes from, or says it was not found.
          </p>
        </div>
        <div className="w-full">
          <AccountBar user={user} onLogin={onLogin} onLogout={logout} />
        </div>
        <div className="flex gap-1 rounded-lg border border-warm-border p-1 bg-subtle" role="group" aria-label="Answer language">
          {LANG_CHOICES.map((l) => (
            <button
              key={l.label}
              type="button"
              aria-pressed={lang === l.id}
              onClick={() => setLang(l.id)}
              className={`text-xs px-2.5 py-1 rounded-md font-semibold ${lang === l.id ? "bg-card text-body shadow-xs" : "text-muted hover:text-body"}`}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>

      <section className="rounded-card border border-warm-border bg-card p-4 shadow-xs min-h-[420px] flex flex-col gap-3" aria-live="polite">
        {messages.length === 0 && (
          <div className="flex-1 flex flex-col items-center justify-center text-center gap-3 py-10">
            <p className="font-heading text-base font-bold text-body">તમારા ઘરનો દરેક જવાબ, તમારી ભાષામાં</p>
            <p className="text-sm text-muted">Try one of these:</p>
            <div className="flex flex-wrap justify-center gap-2">
              {[...(user ? (ROLE_SUGGESTIONS[user.role] ?? []).map((text) => ({ lang: "en" as Lang, text })) : []), ...starters].map((s) => (
                <button
                  key={s.text}
                  type="button"
                  onClick={() => send(s.text)}
                  className="text-xs px-3 py-1.5 rounded-full border border-warm-border bg-subtle text-body hover:border-accent-amber"
                >
                  {s.text}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="self-end max-w-[85%] rounded-2xl rounded-br-sm bg-primary-bg text-primary-text px-4 py-2 text-sm whitespace-pre-wrap">
              {m.text}
            </div>
          ) : (
            <div
              key={i}
              className={`self-start min-w-0 rounded-2xl rounded-bl-sm border border-warm-border bg-page px-4 py-3 text-body ${
                m.reply.cards.some((c) => c.type === "analytics") ? "w-full" : "max-w-[92%]"
              }`}
            >
              <CitedText text={m.reply.text} />
              {m.reply.cards.map((c, j) => <Card key={j} card={c} />)}
              {m.reply.options.length > 0 && (
                <div className="mt-2 flex flex-col gap-1.5">
                  {m.reply.options.map((o) => (
                    <button
                      key={o.n}
                      type="button"
                      disabled={busy || m !== last}
                      onClick={() => send(String(o.n), o.label)}
                      className="text-left text-xs px-3 py-2 rounded-lg border border-warm-border bg-card hover:border-accent-amber disabled:opacity-50 disabled:hover:border-warm-border disabled:cursor-default"
                    >
                      <span className="font-bold mr-1.5">{o.n}.</span>{o.label}
                    </button>
                  ))}
                </div>
              )}
              {m.reply.sources.length > 0 && (
                <details className="mt-2 text-[11px] text-muted">
                  <summary className="cursor-pointer">
                    Sources ({m.reply.sources.length}){m.reply.is_mock ? " · demo data" : ""}
                  </summary>
                  <ol className="mt-1 flex flex-col gap-0.5">
                    {m.reply.sources.map((s) => (
                      <li key={s.n} className="break-all">
                        <span className="font-bold">[{s.n}]</span> {SOURCE_LABEL[s.type] ?? s.type}: <span className="font-mono">{s.id}</span>
                      </li>
                    ))}
                  </ol>
                </details>
              )}
            </div>
          )
        )}
        {busy && <div className="self-start text-xs text-muted">…</div>}
        <div ref={endRef} />
      </section>

      {error && (
        <div role="alert" className={`rounded-card border p-3 text-sm ${RED}`}>
          {error}
        </div>
      )}

      {last && last.reply.suggestions.length > 0 && !busy && (
        <div className="flex flex-wrap gap-2">
          {last.reply.suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => send(s)}
              className="text-xs px-3 py-1.5 rounded-full border border-warm-border bg-subtle text-body hover:border-accent-amber"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. મંગલ સ્ક્વેર નું પઝેશન ક્યારે મળશે?"
          aria-label="Your question"
          className="flex-1 min-w-0 rounded-lg border border-warm-border bg-page text-body text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent-amber"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="px-4 py-2 rounded-lg bg-primary-bg text-primary-text text-sm font-semibold disabled:opacity-50"
        >
          Send
        </button>
      </form>
      <p className="text-[11px] text-muted">
        Prototype on demo data. Answers are built only from registry records. Complaints go to a mock GUJRERA
        workflow until the real one is connected.
      </p>
    </div>
  );
};
