import React, { useCallback, useEffect, useState } from "react";
import {
  checkText,
  fetchHealth,
  fetchSamples,
  fetchTestset,
  runTestItem,
  retranscribeAudio,
  runSampleOcr,
  runUploadOcr,
  uploadAudio,
} from "./api/client";
import { DocumentViewer } from "./components/DocumentViewer";
import { Footer } from "./components/Footer";
import { NarrativesPage } from "./components/NarrativesPage";
import { EvaluationPage } from "./components/EvaluationPage";
import { ReraCheckPage } from "./components/ReraCheckPage";
import { AskPage } from "./components/AskPage";
import type { NavTab } from "./components/TopBar";
import { ResultPanel } from "./components/ResultPanel";
import { SampleDrawer } from "./components/SampleDrawer";
import { StartHub } from "./components/StartHub";
import { TopBar } from "./components/TopBar";
import {
  HealthResponse,
  OCRResult,
  SampleItem,
  TestItem,
} from "./types";

export const App: React.FC = () => {
  const [darkMode, setDarkMode] = useState<boolean>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("theme") === "dark";
  });
  const [activeNavTab, setActiveNavTab] = useState<NavTab>(() => {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get("tab");
    if (tab === "ask") return "ask";
    if (tab === "verification") return "verification";
    if (tab === "narratives") return "narratives";
    if (tab === "evaluation") return "evaluation";
    return "rera";
  });
  const [presenterMode, setPresenterMode] = useState<boolean>(false);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<boolean>(false);
  const [samples, setSamples] = useState<SampleItem[]>([]);
  const [testItems, setTestItems] = useState<TestItem[]>([]);
  const [selectedTestId, setSelectedTestId] = useState<string | null>(null);
  const [allowFallback, setAllowFallback] = useState<boolean>(false);
  const [fallbackInitialized, setFallbackInitialized] = useState<boolean>(false);
  const [simulateUnseen, setSimulateUnseen] = useState<boolean>(false);

  const [selectedSampleId, setSelectedSampleId] = useState<string | null>(null);
  const [activeImageUrl, setActiveImageUrl] = useState<string | null>(null);
  const [activeFilename, setActiveFilename] = useState<string | null>(null);
  const [activeDimensions, setActiveDimensions] = useState<{
    w: number;
    h: number;
  }>({ w: 0, h: 0 });

  const [result, setResult] = useState<OCRResult | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [loadingMessage, setLoadingMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const root = document.documentElement;
    if (darkMode) {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
  }, [darkMode]);

  const refreshHealth = useCallback(async () => {
    try {
      const h = await fetchHealth();
      setHealth(h);
      setHealthError(false);
      if (!fallbackInitialized) {
        setAllowFallback(!h.ollama_enabled);
        setFallbackInitialized(true);
      }
    } catch {
      setHealthError(true);
    }
  }, [fallbackInitialized]);

  useEffect(() => {
    void refreshHealth();
    fetchTestset()
      .then((res) => setTestItems(res.items || []))
      .catch(() => {});
    fetchSamples()
      .then((res) => {
        const list = res.items || [];
        setSamples(list);
        const params = new URLSearchParams(window.location.search);
        const initialSampleId = params.get("sample");
        const initialText = params.get("text");
        const initialAudioJob = params.get("audio_job");
        if (initialSampleId) {
          const found = list.find((s) => s.id === initialSampleId) || {
            id: initialSampleId,
            group: "fake",
            label: "fake",
            language: "en",
            narrative: null,
            note: null,
            expected_issuer: null,
            expected_issuer_id: null,
            expected_reference_no: null,
            thumbnail_url: `/api/samples/${encodeURIComponent(initialSampleId)}/image`,
            filename: `${initialSampleId}.jpg`,
            width: 0,
            height: 0,
          };
          void handleSelectSample(found);
        } else if (initialText) {
          void handleCheckText(initialText);
        } else if (initialAudioJob) {
          void handleRetranscribeAudio(initialAudioJob, "hi");
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleResetVerification = () => {
    setResult(null);
    setSelectedSampleId(null);
    setSelectedTestId(null);
    setActiveImageUrl(null);
    setActiveFilename(null);
    setActiveDimensions({ w: 0, h: 0 });
    setErrorMessage(null);
  };

  const handleSelectSample = async (sample: SampleItem, unseenOverride?: boolean) => {
    setSelectedTestId(null);
    setSelectedSampleId(sample.id);
    setActiveImageUrl(sample.thumbnail_url);
    setActiveFilename(sample.filename);
    setActiveDimensions({ w: sample.width || 0, h: sample.height || 0 });
    setErrorMessage(null);
    setLoading(true);

    try {
      const activeUnseen =
        unseenOverride !== undefined
          ? unseenOverride
          : sample.group === "fake"
          ? simulateUnseen
          : false;
      const ocrRes = await runSampleOcr(sample.id, allowFallback, activeUnseen);
      setResult(ocrRes);
      if (ocrRes.image_url) {
        setActiveImageUrl(ocrRes.image_url);
      }
      if (ocrRes.filename) {
        setActiveFilename(ocrRes.filename);
      }
      if (ocrRes.width && ocrRes.height) {
        setActiveDimensions({ w: ocrRes.width, h: ocrRes.height });
      }
      if (!ocrRes.valid && ocrRes.error) {
        setErrorMessage(ocrRes.error);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to run OCR.";
      setErrorMessage(msg);
      setResult(null);
    } finally {
      setLoading(false);
      void refreshHealth();
    }
  };

  const handleToggleSimulateUnseen = (val: boolean) => {
    setSimulateUnseen(val);
    if (selectedSampleId) {
      const s = samples.find((x) => x.id === selectedSampleId);
      if (s) {
        void handleSelectSample(s, val);
      }
    }
  };

  const handleUploadFile = async (file: File) => {
    setSelectedTestId(null);
    setSelectedSampleId(null);
    setActiveFilename(file.name);
    setActiveImageUrl(null);
    setActiveDimensions({ w: 0, h: 0 });
    setErrorMessage(null);

    const ext = file.name.toLowerCase().split(".").pop() || "";
    if (!["png", "jpg", "jpeg", "webp", "pdf"].includes(ext)) {
      setErrorMessage(
        "Unsupported file type. Allowed formats: PNG, JPG, JPEG, WEBP, PDF."
      );
      setResult(null);
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setErrorMessage("File exceeds the 10 MB size limit.");
      setResult(null);
      return;
    }

    setLoading(true);
    try {
      const ocrRes = await runUploadOcr(file, allowFallback);
      setResult(ocrRes);
      if (ocrRes.image_url) {
        setActiveImageUrl(ocrRes.image_url);
      }
      if (ocrRes.filename) {
        setActiveFilename(ocrRes.filename);
      }
      if (ocrRes.width && ocrRes.height) {
        setActiveDimensions({ w: ocrRes.width, h: ocrRes.height });
      }
      if (!ocrRes.valid && ocrRes.error) {
        setErrorMessage(ocrRes.error);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Upload OCR failed.";
      setErrorMessage(msg);
      setResult(null);
    } finally {
      setLoading(false);
      void refreshHealth();
    }
  };

  const handleUploadAudio = async (file: File, language?: string) => {
    setSelectedTestId(null);
    setSelectedSampleId(null);
    setActiveFilename(file.name);
    setActiveImageUrl(null);
    setActiveDimensions({ w: 0, h: 0 });
    setErrorMessage(null);

    const ext = file.name.toLowerCase().split(".").pop() || "";
    if (!["mp3", "ogg", "opus", "wav", "m4a"].includes(ext)) {
      setErrorMessage(
        "Unsupported audio type. Allowed formats: MP3, OGG, OPUS, WAV, M4A."
      );
      setResult(null);
      return;
    }
    if (file.size > 25 * 1024 * 1024) {
      setErrorMessage("Audio file exceeds the 25 MB size limit.");
      setResult(null);
      return;
    }

    if (!health?.speech_model_loaded) {
      setLoadingMessage("Loading speech model...");
    } else {
      setLoadingMessage(null);
    }
    setLoading(true);
    try {
      const audioRes = await uploadAudio(file, language, allowFallback);
      setResult(audioRes);
      if (audioRes.filename) {
        setActiveFilename(audioRes.filename);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Audio upload failed.";
      setErrorMessage(msg);
      setResult(null);
    } finally {
      setLoading(false);
      setLoadingMessage(null);
      void refreshHealth();
    }
  };

  const handleRunTestItem = async (item: TestItem, unseen: boolean) => {
    setSelectedSampleId(null);
    setSelectedTestId(item.id);
    setActiveImageUrl(item.thumbnail_url);
    setActiveFilename(item.id);
    setActiveDimensions({ w: 0, h: 0 });
    setErrorMessage(null);
    setLoading(true);
    try {
      const res = await runTestItem(item.id, allowFallback, unseen);
      setResult(res);
      if (res.width && res.height) setActiveDimensions({ w: res.width, h: res.height });
      if (!res.valid && res.error) setErrorMessage(res.error);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Test item failed.");
      setResult(null);
    } finally {
      setLoading(false);
      void refreshHealth();
    }
  };

  const handleCheckText = async (text: string) => {
    setSelectedTestId(null);
    setSelectedSampleId(null);
    setActiveFilename("Pasted message");
    setActiveImageUrl(null);
    setActiveDimensions({ w: 0, h: 0 });
    setErrorMessage(null);

    setLoading(true);
    try {
      const textRes = await checkText(text, allowFallback);
      setResult(textRes);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Text check failed.";
      setErrorMessage(msg);
      setResult(null);
    } finally {
      setLoading(false);
      void refreshHealth();
    }
  };

  const handleRetranscribeAudio = async (jobId: string, language: string) => {
    setSelectedTestId(null);
    setSelectedSampleId(null);
    setActiveFilename(jobId);
    setActiveImageUrl(null);
    setActiveDimensions({ w: 0, h: 0 });
    setErrorMessage(null);
    if (!health?.speech_model_loaded) {
      setLoadingMessage("Loading speech model...");
    } else {
      setLoadingMessage(null);
    }
    setLoading(true);
    try {
      const retrans = await retranscribeAudio(jobId, language, allowFallback);
      setResult(retrans);
      if (retrans.filename) {
        setActiveFilename(retrans.filename);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Retranscription failed.";
      setErrorMessage(msg);
    } finally {
      setLoading(false);
      setLoadingMessage(null);
      void refreshHealth();
    }
  };

  const currentSample = samples.find((s) => s.id === selectedSampleId);

  return (
    <div className="min-h-screen flex flex-col bg-page text-body transition-colors duration-150">
      {/* 1. Header */}
      <TopBar
        health={health}
        healthError={healthError}
        darkMode={darkMode}
        onToggleDarkMode={() => setDarkMode((d) => !d)}
        activeNavTab={activeNavTab}
        onSelectNavTab={setActiveNavTab}
        presenterMode={presenterMode}
        onTogglePresenterMode={() => setPresenterMode((p) => !p)}
      />

      {/* Backend Alert Banner */}
      {healthError && (
        <div
          role="alert"
          className="bg-red-700 text-white px-6 py-2.5 text-xs font-semibold text-center"
        >
          Backend not running: start it with scripts/run_demo.ps1
        </div>
      )}

      {/* Main Body */}
      <main className="flex-1 w-full flex flex-col">
        {activeNavTab === "ask" ? (
          <div className="w-full flex-1">
            <AskPage />
          </div>
        ) : activeNavTab === "rera" ? (
          <div className="w-full flex-1">
            <ReraCheckPage />
          </div>
        ) : activeNavTab === "narratives" ? (
          <div className="max-w-[1440px] w-full mx-auto px-4 sm:px-6 py-6 flex-1">
            <NarrativesPage onBackToVerification={() => setActiveNavTab("verification")} />
          </div>
        ) : activeNavTab === "evaluation" ? (
          <div className="w-full flex-1">
            <EvaluationPage />
          </div>
        ) : (
          /* VERIFICATION TAB */
          <div className="w-full flex-1">
            {/* Inline Error Message */}
            {errorMessage && (
              <div className="max-w-[1440px] mx-auto px-4 sm:px-6 pt-4">
                <div
                  role="alert"
                  className="rounded-xl border border-red-300 dark:border-red-800 bg-red-50/90 dark:bg-red-950/50 p-4 flex items-start gap-3"
                >
                  <div className="w-5 h-5 rounded-full bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 flex items-center justify-center shrink-0 mt-0.5 font-bold text-xs">
                    !
                  </div>
                  <div className="text-xs">
                    <h4 className="font-heading font-semibold text-red-900 dark:text-red-200">
                      Verification Issue
                    </h4>
                    <p className="text-red-800 dark:text-red-300 mt-0.5">
                      {errorMessage}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* A. Loading State */}
            {loading ? (
              <div className="max-w-[1440px] mx-auto px-4 sm:px-6 py-8">
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
                  <div className="lg:col-span-5 warm-card p-5 space-y-4">
                    <div className="h-4 w-36 bg-skeleton rounded animate-pulse" />
                    <div className="h-[420px] w-full bg-skeleton/70 rounded-xl animate-pulse" />
                  </div>
                  <div className="lg:col-span-7 flex flex-col gap-4">
                    <div className="rounded-xl border border-accent-border bg-accent-surface/70 p-4 flex items-center gap-3">
                      <div className="w-4 h-4 border-2 border-accent-amber border-t-transparent rounded-full animate-spin shrink-0" />
                      <p className="text-xs font-semibold text-body">
                        {loadingMessage || "Running Pramaan document verification pipeline..."}
                      </p>
                    </div>
                    <div className="warm-card p-5 space-y-4">
                      <div className="h-6 w-48 bg-skeleton rounded animate-pulse" />
                      <div className="h-4 w-full bg-skeleton/60 rounded animate-pulse" />
                      <div className="h-20 w-full bg-skeleton/40 rounded-xl animate-pulse" />
                    </div>
                  </div>
                </div>
              </div>
            ) : result || activeImageUrl ? (
              /* B. RESULT STATE (2-Pane View: Left ~45% sticky, Right ~55% report) */
              <div className="max-w-[1440px] mx-auto px-4 sm:px-6 py-6">
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
                  {/* Left Pane (45%, sticky) */}
                  <div className="lg:col-span-5 lg:sticky lg:top-20 lg:self-start space-y-3">
                    {/* Top action bar: New verification + Switch sample */}
                    <div className="flex items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={handleResetVerification}
                        className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-warm-border bg-card text-body hover:bg-subtle transition-colors focus-amber shadow-xs"
                      >
                        <span aria-hidden="true">←</span>
                        <span>New Verification</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setDrawerOpen(true)}
                        className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-warm-strong bg-card text-body hover:bg-subtle transition-colors focus-amber shadow-xs"
                      >
                        <svg className="w-4 h-4 text-accent-amber" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16m-7 6h7" />
                        </svg>
                        <span>Browse Samples</span>
                      </button>
                    </div>

                    {/* Document Viewer / Audio Player / Pasted Text */}
                    <DocumentViewer
                      imageUrl={activeImageUrl}
                      audioUrl={result?.is_audio ? result.audio_url : null}
                      isAudio={Boolean(result?.is_audio)}
                      messageText={result?.is_text ? result.final_text : null}
                      regions={result?.visual?.regions}
                      filename={activeFilename}
                      width={activeDimensions.w}
                      height={activeDimensions.h}
                    />
                  </div>

                  {/* Right Pane (55%, The Report) */}
                  <div className="lg:col-span-7">
                    {result && (
                      <ResultPanel
                        result={result}
                        onRetranscribe={handleRetranscribeAudio}
                        loading={loading}
                        presenterMode={presenterMode}
                        talkingPoint={currentSample?.talking_point}
                        simulateUnseen={simulateUnseen}
                      />
                    )}
                  </div>
                </div>
              </div>
            ) : (
              /* C. START STATE (Centred input hub + 6 curated examples) */
              <StartHub
                samples={samples}
                onSelectSample={handleSelectSample}
                onUploadFile={handleUploadFile}
                onUploadAudio={handleUploadAudio}
                onCheckText={handleCheckText}
                onOpenDrawer={() => setDrawerOpen(true)}
                loading={loading}
              />
            )}
          </div>
        )}
      </main>

      {/* Flyout Slide-over Drawer for All Samples & Held-out Test Set */}
      <SampleDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        samples={samples}
        selectedSampleId={selectedSampleId}
        onSelectSample={handleSelectSample}
        testItems={testItems}
        selectedTestId={selectedTestId}
        onRunTestItem={handleRunTestItem}
        simulateUnseen={simulateUnseen}
        onToggleSimulateUnseen={handleToggleSimulateUnseen}
        allowFallback={allowFallback}
        onToggleFallback={setAllowFallback}
        offlineMode={Boolean(health?.offline_mode)}
        loading={loading}
      />

      {/* Global Footer */}
      <Footer />
    </div>
  );
};

export default App;
