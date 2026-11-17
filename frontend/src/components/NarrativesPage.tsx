import React, { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
} from "recharts";
import { fetchNarrativeDetail, fetchNarratives } from "../api/client";
import {
  NarrativeClusterDetail,
  NarrativeClusterSummary,
  SharedIndicatorItem,
} from "../types";

interface NarrativesPageProps {
  onBackToVerification?: () => void;
}

export const NarrativesPage: React.FC<NarrativesPageProps> = () => {
  const [narratives, setNarratives] = useState<NarrativeClusterSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sortMode, setSortMode] = useState<"size" | "recent">("size");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedIssuer, setSelectedIssuer] = useState<string>("all");

  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(
    null
  );
  const [detail, setDetail] = useState<NarrativeClusterDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetchNarratives(
      sortMode,
      searchQuery || undefined,
      selectedIssuer === "all" ? undefined : selectedIssuer
    )
      .then((res) => {
        setNarratives(res.items || []);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load narratives");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [sortMode, searchQuery, selectedIssuer]);

  useEffect(() => {
    if (!selectedClusterId) {
      setDetail(null);
      return;
    }
    setLoadingDetail(true);
    fetchNarrativeDetail(selectedClusterId)
      .then((res) => setDetail(res))
      .catch(() => setDetail(null))
      .finally(() => setLoadingDetail(false));
  }, [selectedClusterId]);

  // Aggregate all unique issuers across narratives for the filter dropdown
  const allIssuers = Array.from(
    new Set(
      narratives.flatMap((n) =>
        (n.claimed_issuers || []).map((iss) => iss.issuer)
      )
    )
  ).sort();

  return (
    <div className="flex flex-col gap-6 w-full">
      {/* Header & Controls Band */}
      <section className="warm-card p-6 flex flex-col gap-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <span className="inline-block text-[11px] font-semibold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-accent-surface border border-accent-border text-accent-strong mb-2">
              Stage 8 · Intelligence &amp; Analysis
            </span>
            <h2 className="font-heading text-xl font-bold text-body">
              Disinformation &amp; Scam Narratives
            </h2>
            <p className="text-xs text-muted mt-1 leading-relaxed max-w-2xl">
              HDBSCAN density clustering across 1,968 debunked records discovers
              repeating forgery campaigns. Track multi-year timelines and
              cross-agency template reuse (shared signatories, phone numbers,
              and phishing domains).
            </p>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            {/* Sort Toggle */}
            <div className="inline-flex rounded-lg border border-warm-border p-1 bg-subtle text-xs">
              <button
                type="button"
                onClick={() => setSortMode("size")}
                className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                  sortMode === "size"
                    ? "bg-card text-body shadow-sm font-semibold"
                    : "text-muted hover:text-body"
                }`}
              >
                Sort by size
              </button>
              <button
                type="button"
                onClick={() => setSortMode("recent")}
                className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                  sortMode === "recent"
                    ? "bg-card text-body shadow-sm font-semibold"
                    : "text-muted hover:text-body"
                }`}
              >
                Most recent activity
              </button>
            </div>
          </div>
        </div>

        {/* Filter / Search Bar */}
        <div className="flex items-center gap-3 flex-wrap pt-3 border-t border-warm-border">
          <div className="flex-1 min-w-[240px]">
            <input
              type="text"
              placeholder="Search narrative name, keywords, or issuer…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full text-xs px-3.5 py-2 rounded-lg border border-warm-border bg-card text-body placeholder:text-muted focus-amber"
            />
          </div>

          <div className="w-56">
            <select
              value={selectedIssuer}
              onChange={(e) => setSelectedIssuer(e.target.value)}
              aria-label="Filter by agency"
              className="w-full text-xs px-3 py-2 rounded-lg border border-warm-border bg-card text-body focus-amber"
            >
              <option value="all">All agencies ({allIssuers.length})</option>
              {allIssuers.map((iss) => (
                <option key={iss} value={iss}>
                  {iss}
                </option>
              ))}
            </select>
          </div>

          <span className="font-mono text-xs text-muted">
            Showing {narratives.length} narratives
          </span>
        </div>
      </section>

      {/* Main Grid: Narratives Cards */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="warm-card p-5 space-y-4">
              <div className="h-4 w-32 bg-skeleton rounded animate-pulse" />
              <div className="h-6 w-3/4 bg-skeleton rounded animate-pulse" />
              <div className="h-28 w-full bg-skeleton/70 rounded animate-pulse" />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="warm-card p-6 text-center text-xs text-red-700 dark:text-red-300">
          {error}
        </div>
      ) : narratives.length === 0 ? (
        <div className="warm-card p-12 text-center text-xs text-muted">
          No narratives match your query.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 items-start">
          {narratives.map((cluster) => {
            const hasTimeline =
              cluster.monthly_debunks && cluster.monthly_debunks.length > 0;
            const topIssuers = (cluster.claimed_issuers || []).slice(0, 3);

            return (
              <div
                key={cluster.id}
                className="warm-card p-5 flex flex-col justify-between gap-4 transition-all duration-150 hover:border-warm-strong"
              >
                <div>
                  {/* Top Badge & Size */}
                  <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                    <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-accent-surface border border-accent-border font-semibold text-accent-strong">
                      {cluster.id}
                    </span>
                    <span className="font-mono text-xs font-semibold px-2.5 py-0.5 rounded-full bg-subtle border border-warm-border text-body">
                      {cluster.size} debunk{cluster.size === 1 ? "" : "s"}
                    </span>
                  </div>

                  <h3 className="font-heading text-sm font-bold text-body line-clamp-2">
                    {cluster.name}
                  </h3>

                  {/* Issuers */}
                  {topIssuers.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap mt-2">
                      {topIssuers.map((iss) => (
                        <span
                          key={iss.issuer}
                          className="text-[11px] font-medium px-2 py-0.2 rounded bg-card border border-warm-border text-body"
                        >
                          {iss.issuer}{" "}
                          <span className="text-muted font-mono">
                            ({iss.count})
                          </span>
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Date range & timeline */}
                  <div className="text-[11px] text-muted mt-2.5 flex items-center justify-between flex-wrap gap-2">
                    <span>
                      {cluster.first_date
                        ? `${cluster.first_date.slice(0, 7)} to ${
                            cluster.last_date
                              ? cluster.last_date.slice(0, 7)
                              : "N/A"
                          }`
                        : "Date range N/A"}
                    </span>
                    {cluster.shared_indicators_count > 0 && (
                      <span className="font-semibold text-accent-strong">
                        {cluster.shared_indicators_count} shared indicator
                        {cluster.shared_indicators_count === 1 ? "" : "s"}
                      </span>
                    )}
                  </div>

                  {/* Monthly Timeline Chart (Recharts) */}
                  {hasTimeline ? (
                    <div className="mt-3 pt-3 border-t border-warm-border">
                      <div className="flex items-center justify-between text-[10px] text-muted mb-1">
                        <span>Debunks per month</span>
                        <span className="font-mono">
                          {cluster.monthly_debunks.length} active months
                        </span>
                      </div>
                      <div className="h-20 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart
                            data={cluster.monthly_debunks}
                            margin={{ top: 4, right: 2, left: 2, bottom: 2 }}
                          >
                            <XAxis
                              dataKey="month"
                              tick={{ fontSize: 9, fill: "#6B6455" }}
                              interval="preserveStartEnd"
                              tickLine={false}
                              axisLine={false}
                            />
                            <Tooltip
                              contentStyle={{
                                backgroundColor: "#FFFFFF",
                                borderColor: "#F1E9D2",
                                borderRadius: "8px",
                                fontSize: "11px",
                                color: "#1F2937",
                              }}
                              formatter={(value: unknown) => [
                                `${value} debunks`,
                                "Count",
                              ]}
                              labelFormatter={(label) => `Month: ${label}`}
                            />
                            <Bar
                              dataKey="count"
                              fill="#B7791F"
                              radius={[3, 3, 0, 0]}
                            />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  ) : (
                    <p className="text-[11px] text-muted italic mt-3 pt-3 border-t border-warm-border">
                      No monthly timeline data
                    </p>
                  )}
                </div>

                {/* Exemplar Links & Action */}
                <div className="pt-3 border-t border-warm-border space-y-2">
                  <div className="text-[11px] font-semibold text-muted uppercase tracking-wider">
                    Example Debunks
                  </div>
                  {cluster.exemplars && cluster.exemplars.length > 0 ? (
                    <div className="space-y-1.5">
                      {cluster.exemplars.slice(0, 2).map((ex) => (
                        <div
                          key={ex.doc_id}
                          className="text-xs flex items-baseline justify-between gap-2"
                        >
                          <span className="truncate text-body text-[11px]">
                            {ex.title || ex.snippet || ex.doc_id}
                          </span>
                          {ex.url && (
                            <a
                              href={ex.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="font-mono text-[10px] text-accent-strong hover:underline shrink-0"
                            >
                              {ex.doc_id} ↗
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <span className="text-[11px] text-muted italic">
                      No exemplar links available
                    </span>
                  )}

                  <button
                    type="button"
                    onClick={() => setSelectedClusterId(cluster.id)}
                    className="w-full mt-2 py-1.5 rounded-lg border border-accent-border bg-accent-surface hover:bg-accent-border/40 text-xs font-semibold text-body transition-colors focus-amber"
                  >
                    View timeline &amp; template reuse →
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Narrative Detail Modal / Slide-over */}
      {selectedClusterId && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-charcoal/60 backdrop-blur-sm"
        >
          <div className="max-w-3xl w-full max-h-[90vh] overflow-y-auto warm-card p-6 space-y-6 shadow-xl animate-fade-in">
            {loadingDetail ? (
              <div className="p-8 text-center text-xs text-muted">
                Loading narrative details…
              </div>
            ) : detail ? (
              <>
                <div className="flex items-start justify-between gap-4 border-b border-warm-border pb-4">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className="font-mono text-xs px-2.5 py-0.5 rounded bg-accent-surface border border-accent-border font-semibold text-accent-strong">
                        {detail.id}
                      </span>
                      <span className="font-mono text-xs px-2.5 py-0.5 rounded-full bg-subtle border border-warm-border text-body font-semibold">
                        {detail.size} debunks
                      </span>
                      {detail.keyword_narrative_id && (
                        <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-card border border-warm-border text-muted">
                          Rule: {detail.keyword_narrative_id}
                        </span>
                      )}
                    </div>
                    <h3 className="font-heading text-lg font-bold text-body">
                      {detail.name}
                    </h3>
                    <p className="text-xs text-muted mt-1">
                      First recorded: {detail.first_date || "N/A"} · Latest:{" "}
                      {detail.last_date || "N/A"}
                    </p>
                    {detail.skipped_undated_posts > 0 && (
                      <p className="text-[11px] text-muted mt-0.5">
                        ({detail.skipped_undated_posts} post
                        {detail.skipped_undated_posts === 1 ? "" : "s"} without
                        dates were skipped from the monthly timeline)
                      </p>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => setSelectedClusterId(null)}
                    className="p-1.5 rounded-lg border border-warm-border bg-card text-muted hover:text-body text-xs font-semibold focus-amber"
                  >
                    ✕ Close
                  </button>
                </div>

                {/* Full Timeline Chart */}
                <div>
                  <h4 className="font-heading text-xs font-bold uppercase tracking-wider text-muted mb-2">
                    Monthly Debunk Frequency
                  </h4>
                  {detail.monthly_debunks && detail.monthly_debunks.length > 0 ? (
                    <div className="h-44 w-full bg-subtle/50 p-3 rounded-lg border border-warm-border">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={detail.monthly_debunks}
                          margin={{ top: 8, right: 8, left: 0, bottom: 8 }}
                        >
                          <XAxis
                            dataKey="month"
                            tick={{ fontSize: 10, fill: "#6B6455" }}
                            interval="preserveStartEnd"
                            tickLine={false}
                          />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: "#FFFFFF",
                              borderColor: "#F1E9D2",
                              borderRadius: "8px",
                              fontSize: "12px",
                              color: "#1F2937",
                            }}
                            formatter={(value: unknown) => [
                              `${value} debunks`,
                              "Count",
                            ]}
                          />
                          <Bar
                            dataKey="count"
                            fill="#B7791F"
                            radius={[4, 4, 0, 0]}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <p className="text-xs text-muted italic">
                      No monthly dates available for this campaign.
                    </p>
                  )}
                </div>

                {/* Template Reuse Links */}
                <div>
                  <h4 className="font-heading text-xs font-bold uppercase tracking-wider text-muted mb-2">
                    Template Reuse &amp; Shared Indicators
                  </h4>
                  {detail.shared_indicators &&
                  detail.shared_indicators.length > 0 ? (
                    <div className="space-y-2">
                      {detail.shared_indicators.map((ind: SharedIndicatorItem) => (
                        <div
                          key={ind.indicator_id}
                          className="p-3 rounded-lg bg-accent-surface border border-accent-border text-xs space-y-1.5"
                        >
                          <div className="flex items-center justify-between gap-2 flex-wrap">
                            <span className="font-mono font-bold text-accent-strong">
                              [{ind.kind.toUpperCase()}] {ind.value}
                            </span>
                            <span className="font-mono text-[11px] text-muted">
                              {ind.linked_records.length} linked documents
                            </span>
                          </div>
                          <p className="text-body font-medium">{ind.summary}</p>
                          <div className="flex items-center gap-1.5 flex-wrap pt-1 text-[11px] text-muted">
                            <span className="font-semibold">Linked docs:</span>
                            {ind.linked_records.map((docId) => (
                              <span
                                key={docId}
                                className="font-mono px-1.5 py-0.5 rounded bg-card border border-warm-border text-body"
                              >
                                {docId}
                              </span>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-muted italic">
                      No shared indicators found across distinct agencies or
                      years for this narrative.
                    </p>
                  )}
                </div>

                {/* All Exemplar Debunks */}
                <div>
                  <h4 className="font-heading text-xs font-bold uppercase tracking-wider text-muted mb-2">
                    Core Exemplar Debunks (Closest to Campaign Centroid)
                  </h4>
                  <div className="space-y-2">
                    {detail.exemplars.map((ex) => (
                      <div
                        key={ex.doc_id}
                        className="p-3 rounded-lg bg-subtle border border-warm-border text-xs space-y-1"
                      >
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <span className="font-mono font-bold text-body">
                            {ex.doc_id}
                          </span>
                          <span className="font-mono text-[11px] text-muted">
                            {ex.date || "Date N/A"}
                          </span>
                        </div>
                        <p className="font-medium text-body">{ex.title}</p>
                        {ex.snippet && (
                          <p className="text-[11px] text-muted line-clamp-2">
                            {ex.snippet}
                          </p>
                        )}
                        {ex.url && (
                          <div className="pt-1">
                            <a
                              href={ex.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-accent-strong font-semibold hover:underline inline-flex items-center gap-1 text-[11px]"
                            >
                              <span>Official Fact-Check</span>
                              <span aria-hidden="true">↗</span>
                            </a>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="p-8 text-center text-xs text-red-700">
                Failed to load narrative detail.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
