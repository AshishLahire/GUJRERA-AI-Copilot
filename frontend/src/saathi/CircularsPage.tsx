import React, { useCallback, useEffect, useState } from "react";
import {
  AuthExpiredError,
  CircularRec,
  circularPdfLink,
  deleteCircular,
  fetchAdminCirculars,
  navigateTo,
  updateCircular,
  uploadCircular,
} from "../api/gujrera";
import { Icon } from "./Brand";
import { useSaathi } from "./context";

const LANG_LABEL: Record<string, string> = { gu: "Gujarati", en: "English", hi: "Hindi", mixed: "Mixed" };

/** One circular: its details, editable before (and after) publishing. */
const Row: React.FC<{ c: CircularRec; token: string; onChange: () => void; onError: (e: unknown) => void }> = ({ c, token, onChange, onError }) => {
  const [number, setNumber] = useState(c.number ?? "");
  const [subject, setSubject] = useState(c.subject ?? "");
  const [date, setDate] = useState(c.issued_on ?? "");
  const [busy, setBusy] = useState(false);
  const dirty = number !== (c.number ?? "") || subject !== (c.subject ?? "") || date !== (c.issued_on ?? "");
  const save = async (status?: "draft" | "published") => {
    setBusy(true);
    try {
      await updateCircular(token, c.id, {
        number, subject, ...(date ? { issued_on: date } : { clear_date: !!c.issued_on }), ...(status ? { status } : {}),
      });
      onChange();
    } catch (e) { onError(e); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!window.confirm(`Delete ${c.number || c.filename}? It is removed from search and the PDF is deleted.`)) return;
    try { await deleteCircular(token, c.id); onChange(); } catch (e) { onError(e); }
  };
  const published = c.status === "published";
  return (
    <li className={`warm-card p-4 flex flex-col gap-3 border-l-4 ${published ? "border-l-emerald-600" : "border-l-brand"}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className={`px-2 py-0.5 rounded-full border font-semibold ${published ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-900" : "border-accent-border bg-accent-surface text-accent-amber-strong"}`}>
          {published ? "Published: citizens and officers can ask about it" : "Draft: check the details, then publish"}
        </span>
        <span className="text-muted">{c.filename} · {c.pages} page{c.pages === 1 ? "" : "s"}{c.ocr_pages ? ` · ${c.ocr_pages} read with OCR` : ""} · {LANG_LABEL[c.language] ?? c.language}</span>
        <a href={circularPdfLink(c, token)} target="_blank" rel="noopener noreferrer" className="ml-auto font-semibold text-brand-strong">Open PDF</a>
      </div>
      <div className="grid gap-2 md:grid-cols-[220px_150px_1fr]">
        <label className="text-[11px] text-muted flex flex-col gap-1">Circular number
          <input value={number} onChange={(e) => setNumber(e.target.value)} placeholder="as printed"
            className="rounded-lg border border-warm-border bg-card text-body text-sm px-2.5 py-1.5" />
        </label>
        <label className="text-[11px] text-muted flex flex-col gap-1">Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
            className="rounded-lg border border-warm-border bg-card text-body text-sm px-2.5 py-1.5" />
        </label>
        <label className="text-[11px] text-muted flex flex-col gap-1">Subject
          <input value={subject} onChange={(e) => setSubject(e.target.value)}
            className="rounded-lg border border-warm-border bg-card text-body text-sm px-2.5 py-1.5" />
        </label>
      </div>
      {c.preview && c.preview[0] && (
        <details className="text-xs text-muted">
          <summary className="cursor-pointer">Text read from page 1</summary>
          <pre className="mt-1 p-2 rounded bg-subtle border border-warm-border whitespace-pre-wrap font-sans text-[11px] text-body max-h-40 overflow-auto">{c.preview[0]}</pre>
        </details>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {!published && (
          <button type="button" disabled={busy || (!number.trim() && !subject.trim())} onClick={() => void save("published")}
            className="px-4 py-1.5 rounded-lg bg-brand text-on-brand text-xs font-bold disabled:opacity-50">Publish</button>
        )}
        {dirty && (
          <button type="button" disabled={busy} onClick={() => void save()}
            className="px-4 py-1.5 rounded-lg bg-primary-bg text-primary-text text-xs font-semibold disabled:opacity-50">Save details</button>
        )}
        {published && (
          <>
            <button type="button" disabled={busy} onClick={() => void save("draft")}
              className="px-3 py-1.5 rounded-lg border border-warm-border text-body text-xs hover:border-brand">Unpublish</button>
            <button type="button" onClick={() => navigateTo("ask")}
              className="px-3 py-1.5 rounded-lg border border-warm-border text-body text-xs hover:border-brand">Ask Saathi about it</button>
          </>
        )}
        <button type="button" onClick={() => void remove()} className="ml-auto text-xs text-red-700 dark:text-red-300">Delete</button>
        <span className="w-full text-[10px] text-muted">Uploaded by {c.uploaded_by ?? "—"} on {c.uploaded_at.replace("T", " ")}{c.published_at ? ` · published ${c.published_at.replace("T", " ")}` : ""}</span>
      </div>
    </li>
  );
};

export const CircularsPage: React.FC = () => {
  const { user, token, logout } = useSaathi();
  const allowed = user?.role === "officer" && !user.district_scope;
  const [list, setList] = useState<CircularRec[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [queue, setQueue] = useState<string[]>([]);
  const [fresh, setFresh] = useState<Record<number, CircularRec>>({});
  const fail = useCallback((e: unknown) => {
    if (e instanceof AuthExpiredError) logout();
    setError((e as Error).message);
  }, [logout]);
  const load = useCallback(() => {
    if (token && allowed) fetchAdminCirculars(token).then((r) => setList(r.circulars)).catch(fail);
  }, [token, allowed, fail]);
  useEffect(load, [load]);

  if (!allowed) return <div className="max-w-3xl mx-auto px-4 py-8 text-sm text-muted">Managing circulars is for state-level GUJRERA officers.</div>;

  const onFiles = async (files: FileList | null) => {
    if (!files || !token) return;
    setError(null);
    for (const f of Array.from(files)) {
      setQueue((q) => [...q, f.name]);
      try {
        const r = await uploadCircular(token, f);
        setFresh((x) => ({ ...x, [r.circular.id]: r.circular }));
      } catch (e) { fail(e); } finally { setQueue((q) => q.filter((n) => n !== f.name)); }
    }
    load();
  };
  const drafts = list.filter((c) => c.status === "draft");
  const published = list.filter((c) => c.status === "published");

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
      <section className="hero-band p-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-accent-amber-strong">Administration</p>
        <h2 className="mt-1 font-heading text-2xl font-bold text-body">Circulars</h2>
        <p className="mt-1 text-sm text-muted max-w-3xl">
          Upload the department's circular PDFs, in Gujarati or English, typed or scanned. The text is read (scanned pages with OCR),
          the number, date and subject are filled in for you to check, and once published, Ask Saathi answers questions from it,
          quoting the circular with its number, date and page.
        </p>
      </section>

      <div className="grid grid-cols-3 gap-3">
        {[["Published", published.length], ["Drafts to check", drafts.length], ["Pages read with OCR", list.reduce((a, c) => a + c.ocr_pages, 0)]].map(([l, v]) => (
          <div key={l as string} className="warm-card p-3"><div className="font-heading text-2xl font-bold text-body">{v}</div><div className="text-xs text-muted">{l}</div></div>
        ))}
      </div>

      {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-900 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900 p-3 text-sm">{error}</div>}

      <label className="warm-card flex flex-col items-center justify-center gap-2 px-4 py-8 text-center cursor-pointer border-2 border-dashed hover:border-brand"
        onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); void onFiles(e.dataTransfer.files); }}>
        <span className="w-10 h-10 rounded-lg bg-brand-soft text-brand-strong flex items-center justify-center"><Icon name="doc" /></span>
        <span className="text-sm font-semibold text-body">{queue.length ? `Reading ${queue.join(", ")}…` : "Drop circular PDFs here, or click to choose"}</span>
        <span className="text-xs text-muted">PDF, up to 30 MB and 60 pages each. Scanned pages take a few seconds each to read.</span>
        <input type="file" accept="application/pdf,.pdf" multiple className="sr-only" onChange={(e) => void onFiles(e.target.files)} />
      </label>

      {drafts.length > 0 && (
        <section className="flex flex-col gap-3">
          <h3 className="font-heading text-sm font-bold text-body">Drafts: check the details, then publish</h3>
          <ul className="flex flex-col gap-3">{drafts.map((c) => <Row key={c.id} c={fresh[c.id] ? { ...c, preview: fresh[c.id].preview } : c} token={token!} onChange={load} onError={fail} />)}</ul>
        </section>
      )}
      <section className="flex flex-col gap-3">
        <h3 className="font-heading text-sm font-bold text-body">Published ({published.length})</h3>
        {published.length === 0
          ? <p className="text-sm text-muted">None yet. Published circulars are searchable in Ask Saathi straight away.</p>
          : <ul className="flex flex-col gap-3">{published.map((c) => <Row key={c.id} c={c} token={token!} onChange={load} onError={fail} />)}</ul>}
      </section>
    </div>
  );
};
