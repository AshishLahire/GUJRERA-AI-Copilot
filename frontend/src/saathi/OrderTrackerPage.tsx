import React, { useState } from "react";
import { CalcProject, OrderStatus, trackOrders } from "../api/gujrera";
import { Icon } from "./Brand";
import { ProjectPicker } from "./CalculatorPage";
import { Said, say, useSaathi } from "./context";
import { En } from "./En";
import { tr } from "./strings";

export const STATE_STYLE: Record<string, { label: Said; cls: string }> = {
  complied: { label: { en: "Complied", gu: "પાલન થયું", hi: "पालन हुआ" }, cls: "bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-900" },
  partly_complied: { label: { en: "Partly done", gu: "અંશતઃ પાલન", hi: "आंशिक पालन" }, cls: "bg-accent-surface text-accent-amber-strong border-accent-border" },
  pending: { label: { en: "Not due yet", gu: "હજી મુદત બાકી", hi: "अभी देय नहीं" }, cls: "bg-subtle text-muted border-warm-border" },
  overdue: { label: { en: "Overdue", gu: "મુદત વીતી", hi: "समय सीमा पार" }, cls: "bg-red-50 text-red-800 border-red-200 dark:bg-red-950/50 dark:text-red-200 dark:border-red-900" },
  not_complied: { label: { en: "Not complied", gu: "પાલન નથી", hi: "पालन नहीं" }, cls: "bg-red-50 text-red-800 border-red-200 dark:bg-red-950/50 dark:text-red-200 dark:border-red-900" },
  recovery: { label: { en: "Recovery started", gu: "વસૂલાત શરૂ", hi: "वसूली शुरू" }, cls: "bg-red-50 text-red-800 border-red-200 dark:bg-red-950/50 dark:text-red-200 dark:border-red-900" },
  dismissed: { label: { en: "Complaint dismissed", gu: "ફરિયાદ નામંજૂર", hi: "शिकायत खारिज" }, cls: "bg-subtle text-muted border-warm-border" },
};

export const StateChip: React.FC<{ state: string | null }> = ({ state }) => {
  const { lang } = useSaathi();
  return state ? (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap ${STATE_STYLE[state]?.cls ?? ""}`}>
      {STATE_STYLE[state] ? say(STATE_STYLE[state].label, lang) : state}
    </span>
  ) : null;
};

export const OrderCard: React.FC<{ o: OrderStatus }> = ({ o }) => {
  const { lang } = useSaathi();
  return (
  <li className="rounded-xl border border-warm-border bg-card p-4">
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div>
        <div className="font-mono text-sm font-semibold text-body">{o.order_no}</div>
        <div className="text-[11px] text-muted">
          {o.complaint_ref ? say({ en: `Complaint ${o.complaint_ref} · `, gu: `ફરિયાદ ${o.complaint_ref} · `, hi: `शिकायत ${o.complaint_ref} · ` }, lang) : ""}{o.project ?? ""}{o.district ? `, ${o.district}` : ""}
        </div>
      </div>
      <StateChip state={o.state} />
    </div>
    <div className="mt-2 flex flex-col gap-1.5 text-sm text-body leading-relaxed">
      {o.sentences.map((s, i) => (
        <p key={i} className={i > 1 ? "text-xs text-muted" : ""}>
          {s.text}
          {s.citations.some((c) => c.type.startsWith("legal")) && (
            <span className="ml-1 text-[10px] text-brand-strong font-semibold">
              {s.citations.filter((c) => c.type.startsWith("legal")).map((c) => c.id.replace("RERA Act, 2016, ", "")).join(", ")}
            </span>
          )}
        </p>
      ))}
    </div>
  </li>
  );
};

export const OrderTrackerPage: React.FC = () => {
  const { lang } = useSaathi();
  const [q, setQ] = useState("");
  const [project, setProject] = useState<CalcProject | null>(null);
  const [items, setItems] = useState<OrderStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const find = async (by: { order_no?: string; complaint_ref?: string; project_id?: number }) => {
    setError(null);
    try {
      setItems((await trackOrders(by, lang)).items);
    } catch (e) {
      setItems(null);
      setError((e as Error).message);
    }
  };
  const submit = () => {
    const v = q.trim().toUpperCase();
    if (!v) return;
    void find(/-ORD-/.test(v) ? { order_no: v } : { complaint_ref: v });
  };

  return (
    <div className="max-w-5xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <div className="max-w-3xl">
        <p className="text-sm text-muted leading-relaxed">{tr("ordIntro", lang)}</p>
        {lang !== "en" && <p lang="en" className="text-xs text-muted opacity-80 mt-0.5">{tr("ordIntro", "en")}</p>}
      </div>
      <section className="rounded-xl border border-warm-border bg-card p-5 grid gap-4 md:grid-cols-2">
        <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <label htmlFor="order-q" className="block text-xs font-semibold text-body mb-1.5">{tr("ordSearch", lang)}<En k="ordSearch" className="font-normal text-muted" /></label>
          <div className="flex gap-2">
            <input id="order-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder={say({ en: "e.g. DEMO-ORD-2024-00006 or DEMO-CMP-2023-00005", gu: "દા.ત. DEMO-ORD-2024-00006 અથવા DEMO-CMP-2023-00005", hi: "जैसे DEMO-ORD-2024-00006 या DEMO-CMP-2023-00005" }, lang)}
              className="flex-1 min-w-0 rounded-lg border border-warm-border bg-card text-body px-3 py-2 text-sm font-mono focus:outline-none focus:border-brand focus:ring-2 focus:ring-brand/30" />
            <button type="submit" className="px-4 rounded-lg bg-primary-bg text-primary-text text-sm font-semibold leading-tight">
              {tr("ordFind", lang)}<En k="ordFind" className="font-normal" />
            </button>
          </div>
        </form>
        <div>
          <label htmlFor="order-project" className="block text-xs font-semibold text-body mb-1.5">{tr("ordOrProject", lang)}<En k="ordOrProject" className="font-normal text-muted" /></label>
          <ProjectPicker inputId="order-project" value={project} onChange={(p) => { setProject(p); if (p) void find({ project_id: p.id }); }} />
        </div>
      </section>
      {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
      {items && items.length === 0 && (
        <div className="rounded-xl border border-dashed border-warm-strong p-6 text-center text-sm text-muted">{say({ en: "No complaint orders found.", gu: "ફરિયાદ પર કોઈ આદેશ મળ્યો નથી.", hi: "शिकायत पर कोई आदेश नहीं मिला।" }, lang)}</div>
      )}
      {items && items.length > 0 && <ul className="grid gap-3">{items.map((o) => <OrderCard key={o.order_id} o={o} />)}</ul>}
      {!items && !error && (
        <div className="rounded-xl border border-dashed border-warm-strong p-8 text-center text-sm text-muted">
          <span className="inline-flex w-10 h-10 rounded-lg bg-brand-soft text-brand-strong items-center justify-center mb-3"><Icon name="law" /></span>
          <p>{say({ en: "Enter an order number or complaint reference, or choose a project.", gu: "આદેશ નંબર અથવા ફરિયાદ સંદર્ભ નંબર લખો, અથવા પ્રોજેક્ટ પસંદ કરો.", hi: "आदेश संख्या या शिकायत संदर्भ संख्या लिखें, या प्रोजेक्ट चुनें।" }, lang)}</p>
        </div>
      )}
    </div>
  );
};
