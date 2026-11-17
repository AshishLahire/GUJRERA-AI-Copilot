import React, { useState } from "react";
import evalSummary from "../data/eval_summary.json";

export const EvaluationPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<
    "summary" | "forensics" | "retrieval" | "testset" | "limitations"
  >("summary");

  const kpis = evalSummary.kpis;
  const datasets = evalSummary.datasets;
  const details = evalSummary.detailed_metrics;

  return (
    <div className="max-w-[1440px] mx-auto px-4 sm:px-6 py-8 space-y-8">
      {/* Page Header */}
      <div className="border-b border-warm-border pb-6">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-accent-surface border border-accent-border text-amber-900 dark:text-amber-200 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
          YellowSense Evaluation Report
        </div>
        <h1 className="font-heading text-2xl sm:text-3xl font-bold tracking-tight text-body">
          Benchmark Evaluation &amp; Verified System Metrics
        </h1>
        <p className="text-sm text-muted mt-1 max-w-3xl leading-relaxed">
          Offline evaluation of Pramaan across four benchmark datasets and the held-out test set.
          All numbers are parsed directly from saved evaluation outputs with zero live API calls to guarantee reproducible verification numbers.
        </p>
      </div>

      {/* Top 4 KPI Metric Cards (Generated from eval_summary.json) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((kpi, idx) => (
          <div key={idx} className="warm-card p-5 border border-warm-border flex flex-col justify-between">
            <div>
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted block mb-1">
                {kpi.label}
              </span>
              <div className="flex items-baseline gap-2">
                <span className="font-heading text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                  {kpi.metric}
                </span>
                <span className="text-xs text-muted font-medium">{kpi.percentage}</span>
              </div>
              <p className="text-xs text-body font-medium mt-2 leading-snug">
                Sample: {kpi.sample_size}
              </p>
              <p className="text-[11px] text-muted mt-1.5 leading-snug">
                <strong className="text-amber-700 dark:text-amber-400">Limitation:</strong> {kpi.limitation}
              </p>
            </div>
            <div className="mt-3 pt-2.5 border-t border-warm-border/60">
              <span className="text-[10px] font-mono text-muted block truncate" title={kpi.source}>
                Source: {kpi.source}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-warm-border pb-2 overflow-x-auto">
        {[
          { key: "summary", label: "Overview & Datasets" },
          { key: "forensics", label: "Forensic Check (Stage 2)" },
          { key: "retrieval", label: "Source Match & RRF (Stage 4)" },
          { key: "testset", label: "Held-out Test Set" },
          { key: "limitations", label: "Known Limitations" },
        ].map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key as any)}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
              activeTab === tab.key
                ? "bg-primary-bg text-primary-text shadow-xs"
                : "text-muted hover:text-body hover:bg-subtle"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab 1: Overview & Datasets */}
      {activeTab === "summary" && (
        <div className="space-y-6">
          <div className="warm-card p-6 border border-warm-border space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-heading text-base font-bold text-body">
                Benchmark Dataset Architecture
              </h2>
              <span className="text-[11px] font-mono text-muted">
                Source of Truth: docs/eval_summary.json
              </span>
            </div>
            <p className="text-xs text-muted leading-relaxed">
              Pramaan is evaluated across 4 primary benchmark sets and a held-out test suite. All metrics below reflect verified saved artifacts:
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              {datasets.map((ds) => (
                <div key={ds.id} className="p-4 rounded-xl bg-subtle/50 border border-warm-border space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-bold text-body">{ds.id}</span>
                    <span className="text-[11px] font-semibold text-accent-amber">
                      {ds.total_generated ? `${ds.count} cached / ${ds.total_generated} generated` : `${ds.count} items`}
                    </span>
                  </div>
                  <p className="text-muted leading-relaxed">{ds.description}</p>
                  <p className="text-[10px] font-mono text-muted pt-1">
                    Verified: {ds.verified_source}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Forensics */}
      {activeTab === "forensics" && (
        <div className="space-y-6">
          <div className="warm-card p-6 border border-warm-border space-y-4">
            <h2 className="font-heading text-base font-bold text-body">
              Stage 2 Forensics Calibration
            </h2>
            <p className="text-xs text-muted leading-relaxed">
              Forensic heuristics evaluate surface indicators without consulting internet archives. Score ranges from 0 (clean) to 100 (high risk). Cues only fire on verified negative indicators.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div className="p-4 rounded-xl bg-subtle/50 border border-warm-border space-y-1">
                <span className="font-semibold text-body block">Genuine Official Corpus ({details.forensics_genuine.metric})</span>
                <p className="text-muted leading-snug">{details.forensics_genuine.sample_size}</p>
                <p className="text-[11px] text-amber-800 dark:text-amber-300">
                  Limitation: {details.forensics_genuine.limitation}
                </p>
                <span className="text-[10px] font-mono text-muted block pt-1">
                  Source: {details.forensics_genuine.source}
                </span>
              </div>
              <div className="p-4 rounded-xl bg-subtle/50 border border-warm-border space-y-1">
                <span className="font-semibold text-body block">Synthetic Forgeries ({details.forensics_synthetic.metric})</span>
                <p className="text-muted leading-snug">{details.forensics_synthetic.sample_size}</p>
                <p className="text-[11px] text-amber-800 dark:text-amber-300">
                  Limitation: {details.forensics_synthetic.limitation}
                </p>
                <span className="text-[10px] font-mono text-muted block pt-1">
                  Source: {details.forensics_synthetic.source}
                </span>
              </div>
            </div>

            <div className="overflow-x-auto pt-2">
              <table className="w-full text-xs text-left">
                <thead className="bg-subtle text-muted uppercase text-[10px] tracking-wider border-b border-warm-border">
                  <tr>
                    <th className="p-2.5">Cue ID</th>
                    <th className="p-2.5">Risk Weight</th>
                    <th className="p-2.5">Targeted Pattern</th>
                    <th className="p-2.5">Validation Rule</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-warm-border">
                  <tr>
                    <td className="p-2.5 font-mono font-semibold text-body">fee_demand</td>
                    <td className="p-2.5 text-red-600 font-bold">+35</td>
                    <td className="p-2.5 text-muted">Upfront registration, file, or approval fee demanded</td>
                    <td className="p-2.5 text-muted">Requires upfront fee phrase + rupee amount</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-mono font-semibold text-body">payment_to_account</td>
                    <td className="p-2.5 text-red-600 font-bold">+35</td>
                    <td className="p-2.5 text-muted">Direct transfer to a savings bank account</td>
                    <td className="p-2.5 text-muted">Govt schemes never instruct wire to savings accounts</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-mono font-semibold text-body">lookalike_domain</td>
                    <td className="p-2.5 text-red-600 font-bold">+35</td>
                    <td className="p-2.5 text-muted">Phishing URL impersonating .gov.in (e.g. mina.gov.is)</td>
                    <td className="p-2.5 text-muted">Matches top lookalike patterns vs official registry</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-mono font-semibold text-body">urgency_threat</td>
                    <td className="p-2.5 text-amber-600 font-bold">+15</td>
                    <td className="p-2.5 text-muted">24-hour arrest or deadline intimidation</td>
                    <td className="p-2.5 text-muted">Common in digital-arrest &amp; recruitment scams</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-mono font-semibold text-body">wrong_signatory_title</td>
                    <td className="p-2.5 text-amber-600 font-bold">+15</td>
                    <td className="p-2.5 text-muted">Impossible title (e.g. Branch Head on Ministry order)</td>
                    <td className="p-2.5 text-muted">Checked against canonical issuer title registry</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Retrieval */}
      {activeTab === "retrieval" && (
        <div className="space-y-6">
          <div className="warm-card p-6 border border-warm-border space-y-4">
            <h2 className="font-heading text-base font-bold text-body">
              Hybrid Retrieval Architecture (Stage 4)
            </h2>
            <p className="text-xs text-muted leading-relaxed">
              Retrieval searches both the official circular registry and the PIB debunk archive using Reciprocal Rank Fusion (RRF, k=60) combining BM25 Okapi lexical matching with BGE-m3 multilingual embeddings.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
              <div className="p-4 rounded-xl bg-subtle/50 border border-warm-border space-y-1">
                <span className="font-semibold text-body block mb-1">Leave-One-Out (LOO) Recall</span>
                <p className="font-mono text-emerald-600 dark:text-emerald-400 font-bold text-sm">
                  {details.retrieval_loo.metric} ({details.retrieval_loo.percentage})
                </p>
                <p className="text-muted leading-relaxed text-[11px]">{details.retrieval_loo.sample_size}</p>
                <p className="text-[11px] text-amber-800 dark:text-amber-300">
                  Limitation: {details.retrieval_loo.limitation}
                </p>
                <span className="text-[10px] font-mono text-muted block pt-1">
                  Source: {details.retrieval_loo.source}
                </span>
              </div>
              <div className="p-4 rounded-xl bg-subtle/50 border border-warm-border space-y-1">
                <span className="font-semibold text-body block mb-1">True Control Precision</span>
                <p className="font-mono text-emerald-600 dark:text-emerald-400 font-bold text-sm">
                  {details.retrieval_controls.metric} ({details.retrieval_controls.percentage})
                </p>
                <p className="text-muted leading-relaxed text-[11px]">{details.retrieval_controls.sample_size}</p>
                <p className="text-[11px] text-amber-800 dark:text-amber-300">
                  Limitation: {details.retrieval_controls.limitation}
                </p>
                <span className="text-[10px] font-mono text-muted block pt-1">
                  Source: {details.retrieval_controls.source}
                </span>
              </div>
              <div className="p-4 rounded-xl bg-subtle/50 border border-warm-border space-y-1">
                <span className="font-semibold text-body block mb-1">Calibrated Thresholds</span>
                <p className="text-muted leading-relaxed">
                  Official Strong Match: <span className="font-mono font-bold text-body">0.88</span>.<br />
                  Debunk Strong Match: <span className="font-mono font-bold text-body">0.78</span>.<br />
                  Prevents cross-matching distinct circulars sharing boilerplate letterheads.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Held-out Test Set */}
      {activeTab === "testset" && (
        <div className="space-y-6">
          <div className="warm-card p-6 border border-warm-border space-y-4">
            <h2 className="font-heading text-base font-bold text-body">
              Held-out Test Set Evaluation (data/testset/manifest.json)
            </h2>
            <p className="text-xs text-muted leading-relaxed">
              The held-out evaluation suite contains 35 total documents (12 real, 11 fake, 12 synthetic). The metrics below document the exact evaluated sample run from{" "}
              <code className="px-1.5 py-0.5 rounded bg-subtle font-mono text-body font-semibold">docs/testset_eval.md</code>:
            </p>
            <div className="p-4 rounded-xl bg-subtle/50 border border-warm-border space-y-3 text-xs">
              <div className="flex items-center justify-between font-semibold text-body">
                <span>Evaluated Genuine Circulars (TR-02 through TR-11)</span>
                <span className="text-emerald-600 dark:text-emerald-400 font-bold">10 / 10 Safe (0 Dangerous False Alarms)</span>
              </div>
              <p className="text-muted leading-relaxed">
                Run Details: Produced by <code className="font-mono font-semibold">scripts/eval_testset.py</code> (commit <code className="font-mono font-semibold">bebf20f</code>, Mon Oct 26 2026). All 10 evaluated real circulars in the official index were correctly verified as <code className="font-mono text-body">matches_official</code> with 0 risk score.
              </p>
              <div className="p-3 rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50/70 dark:bg-amber-950/50 text-[11px] text-amber-900 dark:text-amber-200">
                <strong>Explicit Boundary &amp; Coverage Limitation:</strong> Of the 35 documents in the held-out manifest, exactly 10 genuine circulars have cached OCR text. The 11 held-out fakes (TF-01 through TF-11) and 2 fresh scans (TR-01, TR-12) have not yet been OCR&apos;d without live API calls and were skipped.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 5: Limitations */}
      {activeTab === "limitations" && (
        <div className="warm-card p-6 border border-warm-border space-y-4">
          <h2 className="font-heading text-base font-bold text-body">
            System Limitations &amp; Boundary Conditions
          </h2>
          <div className="space-y-3 text-xs text-muted leading-relaxed">
            <div className="p-3.5 rounded-lg border border-warm-border bg-subtle/40">
              <strong className="text-body block mb-1">1. Decision Support, Not Content Removal</strong>
              Pramaan produces audit trails and risk scores to inform human investigators, newsroom editors, and fraud compliance officers. An &apos;unverified&apos; result does not certify authenticity.
            </div>
            <div className="p-3.5 rounded-lg border border-warm-border bg-subtle/40">
              <strong className="text-body block mb-1">2. Synthetic Sample Size Limitation</strong>
              Only 4 of the 60 generated synthetic circulars (SYN-0001, SYN-0002 clean; SYN-0031, SYN-0033 forged) are in the OCR cache; the remaining 56 synthetic images have not been OCR&apos;d.
            </div>
            <div className="p-3.5 rounded-lg border border-warm-border bg-subtle/40">
              <strong className="text-body block mb-1">3. In-Sample Heuristic Calibration</strong>
              Forensic heuristics were tuned on the genuine corpus (79 documents) and the 12 cached fake notices. Novel fake templates with valid formatting and no fee demands or threats require Stage 3/4 source matching.
            </div>
            <div className="p-3.5 rounded-lg border border-warm-border bg-subtle/40">
              <strong className="text-body block mb-1">4. Visual Heuristics Are Observational Only</strong>
              OpenCV seal, stamp, emblem, and signature detections carry 0 automated risk points to prevent false positives caused by forwarded phone photography and WhatsApp compression.
            </div>
            <div className="p-3.5 rounded-lg border border-warm-border bg-subtle/40">
              <strong className="text-body block mb-1">5. Language Coverage &amp; Speech Noise</strong>
              Offline heuristics operate with high fidelity in Hindi, English, and Hinglish. Vernacular Indic languages route through multilingual embeddings; noisy voice forwards require cloud ASR fallback.
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
export default EvaluationPage;
