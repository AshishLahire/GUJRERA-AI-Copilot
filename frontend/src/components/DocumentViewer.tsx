import React, { useState } from "react";
import { resolveApiUrl } from "../api/client";
import { VisualRegion } from "../types";

export const REGION_STYLES: Record<VisualRegion["kind"], { label: string; border: string; chip: string }> = {
  seal: { label: "Seal / stamp", border: "border-blue-500", chip: "bg-blue-600" },
  signature: { label: "Signature", border: "border-emerald-500", chip: "bg-emerald-600" },
  emblem: { label: "Emblem", border: "border-violet-500", chip: "bg-violet-600" },
  edit_trace: { label: "Edit trace", border: "border-orange-500", chip: "bg-orange-600" },
};

interface DocumentViewerProps {
  imageUrl?: string | null;
  audioUrl?: string | null;
  isAudio?: boolean;
  messageText?: string | null;
  regions?: VisualRegion[];
  filename: string | null;
  width?: number;
  height?: number;
}

export const DocumentViewer: React.FC<DocumentViewerProps> = ({
  imageUrl,
  audioUrl,
  isAudio,
  messageText,
  regions,
  filename,
  width,
  height,
}) => {
  const [zoom, setZoom] = useState<number>(100);
  const [fitToWidth, setFitToWidth] = useState<boolean>(true);
  const [showRegions, setShowRegions] = useState<boolean>(true);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number }>({
    w: width || 0,
    h: height || 0,
  });

  const displayW = width || naturalSize.w;
  const displayH = height || naturalSize.h;

  const handleZoomIn = () => {
    setFitToWidth(false);
    setZoom((z) => Math.min(250, z + 25));
  };

  const handleZoomOut = () => {
    setFitToWidth(false);
    setZoom((z) => Math.max(50, z - 25));
  };

  const handleFitToggle = () => {
    setFitToWidth((prev) => !prev);
    setZoom(100);
  };

  return (
    <div className="warm-card flex flex-col overflow-hidden">
      {/* Viewer Header */}
      <div className="px-4 py-3 border-b border-warm-border flex items-center justify-between gap-2 flex-wrap bg-subtle/50">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-heading text-xs font-semibold uppercase tracking-wider text-muted">
              Document Viewer
            </h3>
            {filename && (
              <span className="font-mono text-xs font-medium text-body truncate max-w-[200px]">
                {filename}
              </span>
            )}
          </div>
          {displayW > 0 && displayH > 0 && (
            <p className="text-[11px] font-mono text-muted mt-0.5">
              {displayW} × {displayH} px
            </p>
          )}
        </div>

        {/* Zoom & Fit Controls */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={handleZoomOut}
            disabled={!imageUrl}
            aria-label="Zoom out"
            className="px-2 py-1 rounded-md border border-warm-border bg-card text-xs font-mono text-body hover:bg-subtle disabled:opacity-40 focus-amber transition-colors duration-150"
          >
            −
          </button>
          <span className="text-xs font-mono w-12 text-center text-muted">
            {fitToWidth ? "Fit" : `${zoom}%`}
          </span>
          <button
            type="button"
            onClick={handleZoomIn}
            disabled={!imageUrl}
            aria-label="Zoom in"
            className="px-2 py-1 rounded-md border border-warm-border bg-card text-xs font-mono text-body hover:bg-subtle disabled:opacity-40 focus-amber transition-colors duration-150"
          >
            +
          </button>
          {regions && regions.length > 0 && (
            <button
              type="button"
              onClick={() => setShowRegions((s) => !s)}
              aria-pressed={showRegions}
              className={`px-2.5 py-1 rounded-md border text-xs font-medium transition-colors duration-150 focus-amber ${
                showRegions
                  ? "border-primary-bg bg-primary-bg text-primary-text"
                  : "border-warm-border bg-card text-body hover:bg-subtle"
              }`}
            >
              Regions
            </button>
          )}
          <button
            type="button"
            onClick={handleFitToggle}
            disabled={!imageUrl}
            className={`px-2.5 py-1 rounded-md border text-xs font-medium transition-colors duration-150 focus-amber ${
              fitToWidth
                ? "border-primary-bg bg-primary-bg text-primary-text"
                : "border-warm-border bg-card text-body hover:bg-subtle"
            }`}
          >
            Fit to width
          </button>
        </div>
      </div>

      {/* Image or Audio Canvas */}
      <div className="p-4 bg-subtle/80 overflow-auto max-h-[calc(100vh-11rem)] min-h-[520px] flex items-start justify-center">
        {messageText ? (
          <div className="w-full max-w-md my-auto flex flex-col gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">
              Forwarded message
            </span>
            <div className="self-start rounded-2xl rounded-tl-sm bg-card border border-warm-border shadow-sm px-4 py-3">
              <p className="text-[11px] italic text-muted mb-1">↪ Forwarded many times</p>
              <p className="text-sm text-body whitespace-pre-wrap break-words leading-relaxed">
                {messageText}
              </p>
            </div>
          </div>
        ) : isAudio || audioUrl ? (
          <div className="w-full my-auto flex flex-col items-center justify-center text-center p-8 bg-card rounded-xl border border-warm-border shadow-sm max-w-lg">
            <div className="w-16 h-16 rounded-full bg-accent-surface border border-accent-border flex items-center justify-center text-accent-strong mb-4">
              <svg
                className="w-8 h-8"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.75}
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M19.114 5.636a9 9 0 0 1 0 12.728M16.463 8.288a5.25 5.25 0 0 1 0 7.424M6.75 8.25l4.72-4.72a.75.75 0 0 1 1.28.53v15.88a.75.75 0 0 1-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 0 1 2.25 12c0-.83.097-1.638.282-2.417.234-.847 1.058-1.354 1.938-1.354h2.24Z"
                />
              </svg>
            </div>
            <h4 className="font-heading font-bold text-body text-sm mb-1">
              Voice Note Clip
            </h4>
            <p className="font-mono text-xs text-muted mb-4 truncate max-w-xs">
              {filename || "audio_recording"}
            </p>
            {audioUrl ? (
              <audio
                controls
                src={resolveApiUrl(audioUrl)}
                className="w-full mt-2"
              />
            ) : (
              <p className="text-xs text-muted italic">Audio stream unavailable</p>
            )}
          </div>
        ) : imageUrl ? (
          <div
            className="relative"
            style={fitToWidth ? { width: "100%" } : { width: `${zoom}%`, maxWidth: "none" }}
          >
          <img
            src={resolveApiUrl(imageUrl)}
            alt={filename || "Document preview"}
            onLoad={(e) => {
              const target = e.currentTarget;
              setNaturalSize({
                w: target.naturalWidth,
                h: target.naturalHeight,
              });
            }}
            style={{ width: "100%", height: "auto" }}
            className="rounded-lg shadow-sm border border-warm-border bg-white"
          />
          {showRegions &&
            (regions || []).map((r, i) => (
              <div
                key={`${r.kind}-${i}`}
                data-testid="visual-region"
                title={r.note}
                className={`absolute border-2 rounded-sm pointer-events-auto ${REGION_STYLES[r.kind].border}`}
                style={{
                  left: `${r.box[0] * 100}%`,
                  top: `${r.box[1] * 100}%`,
                  width: `${r.box[2] * 100}%`,
                  height: `${r.box[3] * 100}%`,
                }}
              >
                <span
                  className={`absolute ${
                    r.box[1] < 0.05 ? "top-[100%] mt-0.5" : "bottom-[100%] mb-0.5"
                  } left-0 text-[9px] font-semibold text-white px-1.5 py-0.5 rounded-sm shadow-xs whitespace-nowrap z-10 ${
                    REGION_STYLES[r.kind].chip
                  }`}
                >
                  {REGION_STYLES[r.kind].label}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="my-auto text-center py-16 text-muted text-xs">
            No document loaded
          </div>
        )}
      </div>
    </div>
  );
};
