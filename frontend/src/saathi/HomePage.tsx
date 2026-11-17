import React, { useState } from "react";
import { useSaathi } from "./context";
import { Icon } from "./Brand";
import { tr } from "./strings";

export type Page = "home" | "ask" | "check" | "promoter" | "officer";

const EXAMPLES: Record<"en" | "gu" | "hi", string[]> = {
  gu: ["મંગલ સ્ક્વેર નું પઝેશન ક્યારે મળશે?", "પઝેશનમાં વિલંબ થાય તો શું મને વ્યાજ મળે?", "મારે ફરિયાદ નોંધાવવી છે"],
  hi: ["कब्जे में देरी होने पर क्या मुझे ब्याज मिलेगा?", "शिकायत कैसे दर्ज करें?", "मेरी शिकायत की स्थिति"],
  en: ["When will I get possession of Mangal Square?", "Can a builder take 20% before the agreement?", "I want to file a complaint"],
};

export const HomePage: React.FC<{ onAsk: (q: string) => void; onNavigate: (p: Page) => void }> = ({ onAsk, onNavigate }) => {
  const { lang } = useSaathi();
  const [q, setQ] = useState("");

  const tiles: { icon: string; title: string; body: string; page: Page; prompt?: string }[] = [
    { icon: "building", title: tr("tileProjectTitle", lang), body: tr("tileProjectBody", lang), page: "ask" },
    { icon: "shield", title: tr("tileCheckTitle", lang), body: tr("tileCheckBody", lang), page: "check" },
    {
      icon: "complaint", title: tr("tileComplaintTitle", lang), body: tr("tileComplaintBody", lang), page: "ask",
      prompt: { en: "I want to file a complaint", gu: "મારે ફરિયાદ નોંધાવવી છે", hi: "मुझे शिकायत दर्ज करनी है" }[lang],
    },
    { icon: "law", title: tr("tileRightsTitle", lang), body: tr("tileRightsBody", lang), page: "ask" },
  ];
  const roles: { icon: string; title: string; body: string; page: Page }[] = [
    { icon: "user", title: tr("roleBuyer", lang), body: tr("roleBuyerBody", lang), page: "ask" },
    { icon: "briefcase", title: tr("rolePromoter", lang), body: tr("rolePromoterBody", lang), page: "promoter" },
    { icon: "chart", title: tr("roleOfficer", lang), body: tr("roleOfficerBody", lang), page: "officer" },
  ];

  return (
    <div className="flex flex-col">
      {/* Hero */}
      <section className="bg-brand text-white dark:text-[#0B1424]">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-10 sm:py-14 grid gap-6">
          <div className="max-w-3xl">
            <h1 className="font-heading text-3xl sm:text-4xl font-bold leading-tight">{tr("heroTitle", lang)}</h1>
            <p className="mt-3 text-base sm:text-lg opacity-90 leading-relaxed">{tr("heroBody", lang)}</p>
          </div>
          <form
            className="flex gap-2 max-w-3xl"
            onSubmit={(e) => {
              e.preventDefault();
              if (q.trim()) onAsk(q.trim());
            }}
          >
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={tr("heroPlaceholder", lang)}
              aria-label={tr("navAsk", lang)}
              className="flex-1 min-w-0 rounded-xl px-4 py-3 text-base text-[#0F1E3A] bg-white border-0 focus:outline-none focus:ring-4 focus:ring-[#FFA43A]/50"
            />
            <button
              type="submit"
              className="px-5 sm:px-6 rounded-xl bg-[#D96C00] hover:bg-[#B85C00] text-white font-semibold text-base"
            >
              {tr("ask", lang)}
            </button>
          </form>
          <div className="flex flex-wrap gap-2">
            {EXAMPLES[lang].map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => onAsk(ex)}
                className="text-sm px-3 py-1.5 rounded-full border border-white/40 dark:border-[#0B1424]/40 hover:bg-white/10"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* What you can do */}
      <section className="max-w-6xl w-full mx-auto px-4 sm:px-6 -mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {tiles.map((t) => (
          <button
            key={t.title}
            type="button"
            onClick={() => (t.prompt ? onAsk(t.prompt) : onNavigate(t.page))}
            className="text-left rounded-2xl border border-warm-border bg-card p-5 shadow-sm hover:border-brand hover:shadow-md transition"
          >
            <span className="inline-flex w-10 h-10 rounded-xl bg-brand-soft text-brand items-center justify-center">
              <Icon name={t.icon} />
            </span>
            <span className="block mt-3 font-heading font-bold text-body">{t.title}</span>
            <span className="block mt-1 text-sm text-muted leading-relaxed">{t.body}</span>
          </button>
        ))}
      </section>

      {/* Roles */}
      <section className="max-w-6xl w-full mx-auto px-4 sm:px-6 pt-12">
        <h2 className="font-heading text-xl font-bold text-body">{tr("rolesTitle", lang)}</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          {roles.map((r) => (
            <div key={r.title} className="rounded-2xl border border-warm-border bg-card p-5 flex flex-col gap-3">
              <div className="flex items-center gap-3">
                <span className="w-9 h-9 rounded-full bg-accent-surface text-accent-amber flex items-center justify-center">
                  <Icon name={r.icon} />
                </span>
                <span className="font-heading font-bold text-body">{r.title}</span>
              </div>
              <p className="text-sm text-muted leading-relaxed flex-1">{r.body}</p>
              <button
                type="button"
                onClick={() => onNavigate(r.page)}
                className="self-start text-sm font-semibold text-brand hover:underline"
              >
                {r.page === "ask" ? tr("navAsk", lang) : r.page === "promoter" ? tr("navPromoter", lang) : tr("navOfficer", lang)} →
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* Trust */}
      <section className="max-w-6xl w-full mx-auto px-4 sm:px-6 py-12">
        <div className="rounded-2xl border border-warm-border bg-subtle p-6">
          <h2 className="font-heading text-lg font-bold text-body">{tr("trustTitle", lang)}</h2>
          <ul className="mt-4 grid gap-4 md:grid-cols-3">
            {(["trust1", "trust2", "trust3"] as const).map((k, i) => (
              <li key={k} className="flex gap-3 text-sm text-body leading-relaxed">
                <span className="text-brand shrink-0 mt-0.5"><Icon name={["shield", "server", "lock"][i]} /></span>
                {tr(k, lang)}
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
};
