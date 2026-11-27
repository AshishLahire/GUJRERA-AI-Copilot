import React, { useCallback, useEffect, useState } from "react";
import { AuthExpiredError, WATCH_CHANGED_EVENT, Watch, fetchUnread, fetchWatches, markWatchSeen, navigateTo, unwatchProject, watchProject } from "../api/gujrera";
import { Icon } from "./Brand";
import { say, useSaathi } from "./context";
import { En } from "./En";
import { LoginPrompt } from "./RolePages";
import { tr } from "./strings";

const TONE_DOT: Record<string, string> = { good: "bg-emerald-600", warn: "bg-brand", bad: "bg-red-600", info: "bg-warm-strong" };
const fmt = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
const changed = () => window.dispatchEvent(new Event(WATCH_CHANGED_EVENT));

/** Watch / Watching toggle for one project. Buyers only; others are pointed to log in. */
export const WatchButton: React.FC<{ projectId: number; compact?: boolean }> = ({ projectId, compact }) => {
  const { user, token, lang } = useSaathi();
  const [on, setOn] = useState<boolean | null>(null);
  const buyer = user?.role === "citizen" && !!token;

  useEffect(() => {
    if (!buyer) return;
    fetchWatches(token!, lang).then((d) => setOn(d.watches.some((w) => w.project_id === projectId))).catch(() => setOn(false));
  }, [buyer, token, lang, projectId]);

  const cls = compact ? "px-3 py-1.5 text-xs rounded-md" : "px-4 py-2 text-sm rounded-lg";
  if (!buyer) {
    return (
      <button type="button" onClick={() => navigateTo("watch")} className={`${cls} border border-warm-strong font-semibold text-body inline-flex items-center gap-1.5`}>
        <Icon name="eye" className="w-4 h-4" /> {tr("watchOn", lang)}
      </button>
    );
  }
  const toggle = async () => {
    if (on) await unwatchProject(token!, projectId); else await watchProject(token!, projectId);
    setOn(!on);
    changed();
  };
  return (
    <button type="button" disabled={on === null} onClick={() => void toggle()} aria-pressed={!!on}
      className={`${cls} font-semibold inline-flex items-center gap-1.5 leading-tight ${on ? "bg-brand-soft text-brand-strong border border-accent-border" : "border border-warm-strong text-body"}`}>
      <Icon name="eye" className="w-4 h-4" />
      <span className="text-left">{tr(on ? "watchOff" : "watchOn", lang)}{!compact && <En k={on ? "watchOff" : "watchOn"} className="font-normal" />}</span>
    </button>
  );
};

/** Bell with the unread count, for buyers. */
export const WatchBell: React.FC<{ page: string }> = ({ page }) => {
  const { user, token, lang } = useSaathi();
  const [n, setN] = useState(0);
  const buyer = user?.role === "citizen" && !!token;
  useEffect(() => {
    if (!buyer) { setN(0); return; }
    const load = () => fetchUnread(token!).then((d) => setN(d.unread)).catch(() => setN(0));
    load();
    window.addEventListener(WATCH_CHANGED_EVENT, load);
    return () => window.removeEventListener(WATCH_CHANGED_EVENT, load);
  }, [buyer, token, page]);
  if (!buyer) return null;
  return (
    <button type="button" onClick={() => navigateTo("watch")} aria-label={say({ en: `${n} new alerts`, gu: `${n} નવી ચેતવણીઓ`, hi: `${n} नई सूचनाएँ` }, lang)}
      className="relative w-8 h-8 rounded-lg border border-warm-border flex items-center justify-center text-muted hover:text-body">
      <Icon name="bell" className="w-4 h-4" />
      {n > 0 && (
        <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-brand text-on-brand text-[10px] font-bold flex items-center justify-center">
          {n > 99 ? "99+" : n}
        </span>
      )}
    </button>
  );
};

export const WatchPage: React.FC = () => {
  const { user, token, lang, logout } = useSaathi();
  const buyer = user?.role === "citizen" && !!token;
  const [data, setData] = useState<{ watches: Watch[]; unread: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!buyer) return;
    fetchWatches(token!, lang).then(setData).catch((e) => { if (e instanceof AuthExpiredError) logout(); setError((e as Error).message); });
  }, [buyer, token, lang, logout]);
  useEffect(load, [load]);

  const readAll = async () => { await markWatchSeen(token!); changed(); load(); };
  const stop = async (pid: number) => { await unwatchProject(token!, pid); changed(); load(); };

  return (
    <div className="max-w-5xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <div className="max-w-3xl">
        <p className="text-sm text-muted leading-relaxed">{tr("watchIntro", lang)}</p>
        {lang !== "en" && <p lang="en" className="text-xs text-muted opacity-80 mt-0.5">{tr("watchIntro", "en")}</p>}
      </div>
      {!buyer && <LoginPrompt k="loginNeededWatch" />}
      {buyer && error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 p-4 text-sm">{error}</div>}
      {buyer && data && (
        <>
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm text-body"><b>{data.unread}</b> {say({ en: "new alert(s)", gu: "નવી ચેતવણી(ઓ)", hi: "नई सूचना(एँ)" }, lang)} · {data.watches.length} {say({ en: "project(s)", gu: "પ્રોજેક્ટ", hi: "प्रोजेक्ट" }, lang)}</span>
            {data.unread > 0 && (
              <button type="button" onClick={() => void readAll()} className="px-3 py-1.5 rounded-lg border border-warm-strong text-xs font-semibold text-body leading-tight">
                {tr("watchMarkRead", lang)}<En k="watchMarkRead" className="font-normal" />
              </button>
            )}
          </div>
          {data.watches.length === 0 && (
            <div className="rounded-xl border border-dashed border-warm-strong p-8 text-center text-sm text-muted">
              <span className="inline-flex w-10 h-10 rounded-lg bg-brand-soft text-brand-strong items-center justify-center mb-3"><Icon name="eye" /></span>
              <p>{say({ en: "Open a project's before-you-buy report or ask about it in the chat, then press \"Watch this project\".", gu: "કોઈ પ્રોજેક્ટનો ખરીદી પહેલાંનો અહેવાલ ખોલો અથવા ચેટમાં તેના વિશે પૂછો, પછી \"આ પ્રોજેક્ટ પર નજર રાખો\" દબાવો.", hi: "किसी प्रोजेक्ट की ख़रीद से पहले की रिपोर्ट खोलें या चैट में उसके बारे में पूछें, फिर \"इस प्रोजेक्ट की निगरानी करें\" दबाएँ।" }, lang)}</p>
            </div>
          )}
          <ul className="flex flex-col gap-4">
            {data.watches.map((w) => (
              <li key={w.project_id} className="rounded-xl border border-warm-border bg-card">
                <div className="px-5 py-3 border-b border-warm-border flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="font-semibold text-body">{lang === "gu" && w.name_gu ? w.name_gu : w.name.replace(" (Demo)", "")}
                      {w.unread > 0 && <span className="ml-2 rounded-full bg-brand text-on-brand text-[10px] font-bold px-1.5 py-0.5">{w.unread} {say({ en: "new", gu: "નવી", hi: "नई" }, lang)}</span>}
                    </div>
                    <div className="text-[11px] text-muted">{w.district} · {w.status} · {say({ en: "watching since", gu: "નજર રાખવાની શરૂઆત", hi: "निगरानी शुरू" }, lang)} {fmt(w.watching_since)}</div>
                  </div>
                  <button type="button" onClick={() => void stop(w.project_id)} className="text-xs text-muted hover:text-body">{say({ en: "Stop watching", gu: "નજર રાખવાનું બંધ કરો", hi: "निगरानी बंद करें" }, lang)}</button>
                </div>
                <ol className="px-5 py-3 flex flex-col gap-2">
                  {w.events.length === 0 && <li className="text-sm text-muted">{say({ en: "Nothing in the last year.", gu: "છેલ્લા એક વર્ષમાં કંઈ નથી.", hi: "पिछले एक साल में कुछ नहीं।" }, lang)}</li>}
                  {w.events.map((e, i) => (
                    <li key={i} className={`flex gap-3 text-sm ${e.unread ? "text-body" : "text-muted"}`}>
                      <span className={`mt-1.5 w-2 h-2 shrink-0 rounded-full ${TONE_DOT[e.tone]}`} />
                      <span className="min-w-0">
                        <span className="text-[11px] tabular-nums mr-2">{fmt(e.date)}</span>
                        {e.unread && <span className="mr-1 text-[10px] font-bold text-brand-strong">{say({ en: "NEW", gu: "નવું", hi: "नया" }, lang)}</span>}
                        {e.text}
                      </span>
                    </li>
                  ))}
                </ol>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
};
