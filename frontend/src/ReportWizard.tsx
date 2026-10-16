import { useCallback, useEffect, useRef, useState } from "react";
import {
  reportStart, reportExtract, reportConfirmExtract, reportPrepare,
  reportGetIntake, reportSubmitIntake, reportGenerate, reportStatus,
  reportDownload, reportSession,
  reportInspectFacts, reportLoadFacts, reportDownloadFacts,
  REPORT_CATEGORIES,
  type ReportSession, type IntakeData, type JobStatus, type IntakeQuestion,
  type FactsInspect,
} from "./api";
import { IcUpload, IcCheck, IcPlay, IcDownload, IcFile, IcAlert, IcChevron } from "./components/icons";

/* ------------------------------------------------------------------ */
/* Filename heuristics for auto-suggesting categories                  */
/* ------------------------------------------------------------------ */

function suggestCategory(name: string): string {
  const n = name.toLowerCase();
  if (n.endsWith(".xlsm") || n.endsWith(".xlsx")) return "excel";
  if (n.endsWith(".zip") || n.includes("figure")) return "figures_zip";
  if (n.includes("abadata")) return "abadata";
  if (n.includes("phaseview")) return "phaseview";
  if (n.includes("phase 1") || n.includes("phase1") || n.includes("esa")) return "phase1_esa";
  if (n.includes("borehole") || n.includes("_bh") || n.includes("bh log")) return "borehole_logs";
  if (n.includes("sst")) return "sst_report";
  return "other_assessment";
}

const CATEGORY_LABELS: Record<string, string> = {
  excel: "Excel analytical file",
  figures_zip: "Figures zip",
  abadata: "ABAData",
  phaseview: "Phaseview",
  phase1_esa: "Phase 1 ESA",
  borehole_logs: "Borehole logs",
  other_assessment: "Other assessment",
  sst_report: "SST report",
};

// "site_lsd" -> "Site Lsd", "client_name" -> "Client Name", etc.
function humanizeKey(k: string): string {
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const STEPS = [
  { id: 1, title: "Files" },
  { id: 2, title: "Extract & Review" },
  { id: 3, title: "Intake" },
  { id: 4, title: "Generate" },
  { id: 5, title: "Done" },
];

// Intake dashboard sections — add new sections here as the questionnaire grows.
const INTAKE_SECTIONS: {
  id: string;
  title: string;
  questionIds: string[];
  autoIds: string[];
  info?: { label: string; value: string }[];
}[] = [
  {
    id: "report",
    title: "Report info",
    questionIds: ["q21", "q22c"],
    autoIds: ["q0", "q1"],
  },
  {
    id: "apec",
    title: "APEC assignments",
    questionIds: ["q22a", "q22b"],
    autoIds: ["q22d"],
  },
  {
    id: "impact",
    title: "Impact",
    questionIds: ["q6"],
    autoIds: [],
  },
];

// The reconciled top-level fields the user may override (everything else is
// read-only — see the Option A decision).
const IDENTITY_FIELDS = [
  { key: "site_lsd", label: "Legal land description (LSD)" },
  { key: "uwi", label: "UWI" },
  { key: "client_name", label: "Client name" },
  { key: "site_type", label: "Site type" },
];

/* ------------------------------------------------------------------ */
/* Small building blocks                                               */
/* ------------------------------------------------------------------ */

function StepHeader({ step, onNavigate }: { step: number; onNavigate: (s: number) => void }) {
  return (
    <div className="subtabs" style={{ marginBottom: 16 }}>
      {STEPS.map((s) => (
        <button
          key={s.id}
          className={`subtab ${step === s.id ? "active" : ""}`}
          onClick={() => onNavigate(s.id)}
        >
          {s.id}. {s.title}
        </button>
      ))}
    </div>
  );
}

function Spinner({ label }: { label: string }) {
  return (
    <div style={{ padding: "24px 0", color: "var(--muted)", fontSize: 13.5 }}>
      <span className="spinner" style={{ display: "inline-block", marginRight: 8 }}>⏳</span>
      {label}
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div style={{ padding: 12, margin: "12px 0", background: "#fde8e8", border: "1px solid #f3b6b6", borderRadius: 8, color: "var(--danger, #c0492f)", fontSize: 13 }}>
      {message}
    </div>
  );
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/* ------------------------------------------------------------------ */
/* Main wizard                                                         */
/* ------------------------------------------------------------------ */

export default function ReportWizard() {
  const [step, setStep] = useState(1);
  const [files, setFiles] = useState<{ file: File; category: string }[]>([]);
  const [session, setSession] = useState<ReportSession | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [intake, setIntake] = useState<IntakeData | null>(null);
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [siteFacts, setSiteFacts] = useState<Record<string, unknown>>({});
  const [flags, setFlags] = useState<{ message?: string; field?: string; ambiguous?: boolean }[]>([]);
  const [pendingFacts, setPendingFacts] = useState<FactsInspect | null>(null);
  const [factsLoaded, setFactsLoaded] = useState(false);
  const [activeSection, setActiveSection] = useState("report");
  const [reviewSection, setReviewSection] = useState("identity");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [factsDrag, setFactsDrag] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const factsFileInput = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((list: FileList | File[]) => {
    const next = Array.from(list).map((file) => ({
      file,
      category: suggestCategory(file.name),
    }));
    setFiles((prev) => [...prev, ...next]);
  }, []);

  const setCategory = (index: number, category: string) => {
    setFiles((prev) => prev.map((f, i) => (i === index ? { ...f, category } : f)));
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  // Poll a background job until it finishes. Retries transient network/5xx
  // errors (e.g. a brief backend restart) instead of giving up immediately.
  const pollJob = useCallback(async (id: string) => {
    let failures = 0;
    for (;;) {
      try {
        const st = await reportStatus(id);
        setJob(st);
        failures = 0;
        if (st.status === "done" || st.status === "error") return st;
      } catch {
        failures += 1;
        if (failures >= 5) {
          throw new Error("Lost connection to the backend while waiting for the job.");
        }
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
  }, []);

  // Persist wizard state so a page reload resumes instead of resetting to step 1.
  const STORAGE_KEY = "ebm_report_wizard";

  useEffect(() => {
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (!saved) return;
    let cancelled = false;
    try {
      const { step: savedStep, sessionId, jobId: savedJobId } = JSON.parse(saved);
      if (savedStep) setStep(savedStep);
      if (savedJobId) setJobId(savedJobId);
      if (!sessionId) return;
      reportSession(sessionId).then((s) => {
        if (cancelled) return;
        setSession(s);
        setSiteFacts(s.site_facts ?? {});
        setFlags(s.extraction_flags ?? []);
        if (s.state === "intake") {
          setStep(3);
          reportGetIntake(sessionId).then((data) => {
            if (!cancelled) { setIntake(data); setAnswers(data.answers ?? {}); }
          }).catch(() => {});
        } else if (s.state === "extracting" || s.state === "preparing" || s.state === "generating") {
          setStep(s.state === "extracting" ? 2 : s.state === "preparing" ? 3 : 4);
          if (savedJobId) {
            pollJob(savedJobId).then((st) => {
              if (cancelled) return;
              if (st.status === "error") setError(st.error ?? "Job failed");
              else if (st.status === "done") {
                if (s.state === "extracting") {
                  reportSession(sessionId).then((s2) => {
                    if (!cancelled) { setSession(s2); setSiteFacts(s2.site_facts ?? {}); setFlags(s2.extraction_flags ?? []); }
                  }).catch(() => {});
                } else if (s.state === "preparing") {
                  reportGetIntake(sessionId).then((data) => {
                    if (!cancelled) { setIntake(data); setAnswers(data.answers ?? {}); }
                  }).catch(() => {});
                } else {
                  setStep(5);
                }
              }
            }).catch(() => {
              // Job is gone (backend restarted) — let the user retry.
              if (!cancelled) setJobId(null);
            });
          }
        } else if (s.state === "done") {
          setStep(5);
        } else if (s.state === "facts_review") {
          setStep(2);
          setFactsLoaded(true);
        }
      }).catch(() => {
        // Session gone (backend restarted) — clear stale state.
        if (!cancelled) {
          sessionStorage.removeItem(STORAGE_KEY);
          setJobId(null);
          setJob(null);
        }
      });
    } catch {
      sessionStorage.removeItem(STORAGE_KEY);
    }
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Save the wizard position whenever it changes.
  useEffect(() => {
    if (!session) return;
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ step, sessionId: session.id, jobId }));
  }, [step, session, jobId]);

  /* -- Step 1: start session ---------------------------------------- */
  async function doStart() {
    setError(null);
    if (files.length === 0) {
      setError("Add at least one file (an Excel analytical file is required).");
      return;
    }
    if (!files.some((f) => f.category === "excel")) {
      setError("An Excel analytical file is required.");
      return;
    }
    setBusy(true);
    // Clear any stale job/facts state from a previous session so Step 2
    // shows the extract/load options instead of an empty card.
    setJobId(null);
    setJob(null);
    setFactsLoaded(false);
    setPendingFacts(null);
    try {
      const s = await reportStart(
        files.map((f) => f.file),
        files.map((f) => f.category)
      );
      setSession(s);
      setStep(2);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start session");
    } finally {
      setBusy(false);
    }
  }

  /* -- Step 2: extract & review ------------------------------------- */
  async function doExtract() {
    if (!session) return;
    setError(null);
    setBusy(true);
    try {
      const { job_id } = await reportExtract(session.id);
      setJobId(job_id);
      const st = await pollJob(job_id);
      if (st.status === "error") {
        setError(st.error ?? "Extraction failed");
        return;
      }
      const s = await reportSession(session.id);
      setSession(s);
      setSiteFacts(s.site_facts ?? {});
      setFlags(s.extraction_flags ?? []);
      setFactsLoaded(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Extraction failed");
    } finally {
      setBusy(false);
    }
  }

  async function doConfirmExtract() {
    if (!session) return;
    setError(null);
    setBusy(true);
    try {
      const s = await reportConfirmExtract(session.id, siteFacts, flags);
      setSession(s);
      setStep(3);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Confirm failed");
    } finally {
      setBusy(false);
    }
  }

  /* -- Cached site facts: inspect -> confirm -> load ----------------- */
  async function doInspectFacts(file: File) {
    if (!session) return;
    setError(null);
    setBusy(true);
    try {
      const inspected = await reportInspectFacts(session.id, file);
      setPendingFacts(inspected);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to read cached site facts");
    } finally {
      setBusy(false);
    }
  }

  async function doConfirmFacts(accept: boolean) {
    if (!session || !pendingFacts) return;
    setError(null);
    if (!accept) {
      setPendingFacts(null);
      return;
    }
    setBusy(true);
    try {
      const s = await reportLoadFacts(session.id, pendingFacts.site_facts, pendingFacts.extraction_flags);
      setSession(s);
      setSiteFacts(s.site_facts ?? {});
      setFlags(s.extraction_flags ?? []);
      setFactsLoaded(true);
      setPendingFacts(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load cached site facts");
    } finally {
      setBusy(false);
    }
  }

  async function doDownloadFacts() {
    if (!session) return;
    try {
      const blob = await reportDownloadFacts(session.id);
      const lsd = String(siteFacts.site_lsd ?? session.id);
      downloadBlob(blob, `site_facts_${lsd}.json`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Facts download failed");
    }
  }

  /* -- Step 3: intake ------------------------------------------------ */
  async function doPrepare() {
    if (!session) return;
    setError(null);
    setBusy(true);
    try {
      const { job_id } = await reportPrepare(session.id);
      setJobId(job_id);
      const st = await pollJob(job_id);
      if (st.status === "error") {
        setError(st.error ?? "Prepare failed");
        return;
      }
      const data = await reportGetIntake(session.id);
      setIntake(data);
      setAnswers(data.answers ?? {});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Prepare failed");
    } finally {
      setBusy(false);
    }
  }

  async function doSubmitIntake() {
    if (!session) return;
    setError(null);
    setBusy(true);
    try {
      const s = await reportSubmitIntake(session.id, answers);
      setSession(s);
      // Clear stale job state from the prepare step before entering Generate.
      setJobId(null);
      setJob(null);
      setStep(4);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Intake submit failed");
    } finally {
      setBusy(false);
    }
  }

  /* -- Step 4: generate ---------------------------------------------- */
  async function doGenerate() {
    if (!session) return;
    setError(null);
    setBusy(true);
    // Clear any stale job state from the prepare step so the Generate
    // button/stages render correctly.
    setJobId(null);
    setJob(null);
    try {
      const { job_id } = await reportGenerate(session.id);
      setJobId(job_id);
      const st = await pollJob(job_id);
      if (st.status === "error") {
        setError(st.error ?? "Generation failed");
        return;
      }
      setStep(5);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setBusy(false);
    }
  }

  /* -- Step 5: download ---------------------------------------------- */
  async function doDownload(kind: "report" | "practitioner") {
    if (!session) return;
    try {
      const blob = await reportDownload(session.id, kind);
      downloadBlob(blob, kind === "practitioner" ? "Practitioner_Information.docx" : "EBM_Report.docx");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    }
  }

  /* -- Non-linear step navigation (back is free; forward needs the
        prerequisite for that step, matching the wizard flow) ---------- */
  const goToStep = (s: number) => {
    if (s === step) return;
    if (s < step) {
      // Warn before leaving a step with a background job still running.
      if (job && job.status !== "done" && job.status !== "error") {
        if (!window.confirm("A background job is still running. You can return to this step to check its progress. Continue?")) return;
      }
      setStep(s);
      return;
    }
    if (s === 2 && session) setStep(2);
    else if (s === 3 && factsLoaded) setStep(3);
    else if (s === 4 && intake) setStep(4);
    else if (s === 5 && job?.status === "done") setStep(5);
  };

  /* -- Start a fresh report (clears the persisted wizard state) ------ */
  function resetWizard() {
    sessionStorage.removeItem(STORAGE_KEY);
    setStep(1);
    setSession(null);
    setJobId(null);
    setJob(null);
    setIntake(null);
    setAnswers({});
    setSiteFacts({});
    setFlags([]);
    setPendingFacts(null);
    setFactsLoaded(false);
    setError(null);
    setFiles([]);
  }

  // Intake dashboard: group applicable questions into sections.
  const intakeSections = intake
    ? INTAKE_SECTIONS
        .map((sec) => ({
          ...sec,
          questions: intake.questions.filter((q) => sec.questionIds.includes(q.id)),
          auto: intake.auto_derived.filter((a) => sec.autoIds.includes(a.id)),
        }))
        .filter((sec) => sec.questions.length > 0 || sec.auto.length > 0 || (sec.info && sec.info.length > 0))
    : [];
  const activeSec = intakeSections.find((s) => s.id === activeSection) ?? intakeSections[0];

  // Step 2 review nav: Identity + one entry per uploaded source file, plus
  // one per source type that has extracted data (e.g. facts loaded from a
  // cached JSON without re-uploading the source documents).
  const sourceNav: { id: string; title: string; dataKey: string | null }[] = [
    { id: "identity", title: "Identity", dataKey: null },
  ];
  const catToFactsKey: Record<string, string> = {
    abadata: "abadata",
    phaseview: "phaseview",
    phase1_esa: "phase1_esa",
    borehole_logs: "borehole_logs",
    other_assessment: "other_previous_assessments",
    sst_report: "sst_report",
  };
  const factsKeyToLabel: Record<string, string> = {
    abadata: "ABAData",
    phaseview: "Phaseview",
    phase1_esa: "Phase 1 ESA",
    borehole_logs: "Borehole logs",
    other_previous_assessments: "Other assessments",
    sst_report: "SST report",
  };
  const hasFactsData = (v: unknown): boolean => {
    if (v === undefined || v === null) return false;
    if (Array.isArray(v)) return v.length > 0;
    if (typeof v === "object") return Object.keys(v as object).length > 0;
    return true;
  };
  for (const [cat, files] of Object.entries(session?.files ?? {})) {
    const dataKey = catToFactsKey[cat];
    if (!dataKey) continue; // skip excel / figures_zip
    for (const f of files) {
      sourceNav.push({ id: `file-${cat}-${f.name}`, title: f.name, dataKey });
    }
  }
  for (const [dataKey, label] of Object.entries(factsKeyToLabel)) {
    if (hasFactsData(siteFacts[dataKey]) && !sourceNav.some((s) => s.dataKey === dataKey)) {
      sourceNav.push({ id: `type-${dataKey}`, title: label, dataKey });
    }
  }

  /* ------------------------------------------------------------------ */
  /* Render                                                              */
  /* ------------------------------------------------------------------ */

  return (
    <div style={{ padding: 24 }}>
      <StepHeader step={step} onNavigate={goToStep} />
      {error && <ErrorBox message={error} />}

      {/* ===== Step 1: Files ===== */}
      {step === 1 && (
        <div className="card">
          <div className="card-head"><div className="card-title">Upload files</div></div>
          <div style={{ padding: 24 }}>
            <div
              className="dropzone"
              style={{
                border: `2px dashed ${drag ? "var(--accent, #0e8f8a)" : "var(--line, #e4ebef)"}`,
                borderRadius: 10, padding: 28, textAlign: "center", cursor: "pointer",
                color: "var(--muted, #6b8090)", fontSize: 13.5,
              }}
              onClick={() => fileInput.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
            >
              <IcUpload className="nav-ico" />
              <div>Drop files here or click to browse</div>
              <div style={{ fontSize: 12, marginTop: 6 }}>
                Excel analytical file (required), plus ABAData, Phaseview, Phase 1 ESA, borehole
                logs, and the figures zip (BG_CHLORIDE/ + CL_DELINEATION/ PNGs)
              </div>
              <input
                ref={fileInput} type="file" multiple style={{ display: "none" }}
                onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }}
              />
            </div>

            {files.length > 0 && (
              <div style={{ marginTop: 16 }}>
                {files.map((f, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
                    <IcFile className="nav-ico" />
                    <span style={{ flex: 1, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.file.name}</span>
                    <select
                      value={f.category}
                      onChange={(e) => setCategory(i, e.target.value)}
                      style={{ background: "var(--card, #ffffff)", color: "var(--ink, #0f1c24)", border: "1px solid var(--line, #e4ebef)", borderRadius: 6, padding: "4px 8px", fontSize: 12.5 }}
                    >
                      {REPORT_CATEGORIES.map((c) => (
                        <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>
                      ))}
                    </select>
                    <button onClick={() => removeFile(i)} style={{ background: "none", border: "none", color: "var(--danger, #c0492f)", cursor: "pointer" }}>✕</button>
                  </div>
                ))}
              </div>
            )}

            <div style={{ marginTop: 20 }}>
              <button className="btn primary" onClick={doStart} disabled={busy}>
                {busy ? "Starting…" : "Start session"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== Step 2: Extract & Review ===== */}
      {step === 2 && (
        <div className="card">
          <div className="card-head"><div className="card-title">Extract site facts</div></div>
          <div style={{ padding: 24 }}>
            {!factsLoaded && (!jobId || !job) && (
              <div className="sf-options">
                <div className="sf-option-card">
                  <div className="sf-option-title">Extract with the LLM</div>
                  <p className="sf-option-desc">
                    Reads the uploaded source documents (ABAData, Phaseview, Phase 1 ESA,
                    borehole logs) once and extracts the site facts. Typically takes 2–5 minutes.
                  </p>
                  <button className="btn primary" onClick={doExtract} disabled={busy}>
                    {busy ? "Extracting…" : "Extract site facts"}
                  </button>
                </div>
                <div className="sf-or-v">OR</div>
                <div className="sf-option-card">
                  <div className="sf-option-title">Load cached site facts</div>
                  <p className="sf-option-desc">
                    Upload a previously-downloaded site_facts.json to skip the LLM extraction.
                  </p>
                  <div
                    className="sf-dropzone"
                    onClick={() => factsFileInput.current?.click()}
                    onDragOver={(e) => { e.preventDefault(); setFactsDrag(true); }}
                    onDragLeave={() => setFactsDrag(false)}
                    onDrop={(e) => { e.preventDefault(); setFactsDrag(false); if (e.dataTransfer.files?.[0]) doInspectFacts(e.dataTransfer.files[0]); }}
                  >
                    <IcUpload className="nav-ico" />
                    <div>Drop your site_facts.json here or click to browse</div>
                    <input
                      ref={factsFileInput} type="file" accept=".json" style={{ display: "none" }}
                      onChange={(e) => { if (e.target.files?.[0]) doInspectFacts(e.target.files[0]); e.target.value = ""; }}
                    />
                  </div>
                </div>
              </div>
            )}

            {jobId && job && job.status !== "done" && job.status !== "error" && (
              <div>
                {job.stages.map((s, i) => (
                  <div key={i} style={{ fontSize: 13, color: s.status === "done" ? "var(--success, #1a7f37)" : "var(--muted, #6b8090)", marginBottom: 6 }}>
                    {s.status === "done" ? "✓" : "⏳"} {s.message}
                  </div>
                ))}
              </div>
            )}

            {pendingFacts && (
              <div style={{ marginBottom: 16 }}>
                <div className="subhead" style={{ marginBottom: 8 }}>Confirm cached site facts</div>
                <div style={{ fontSize: 13, marginBottom: 8 }}>
                  This cached file was extracted from these source documents:
                </div>
                <div style={{ fontSize: 13, marginBottom: 8 }}>
                  <b>Client:</b> {pendingFacts.client_name || "—"} &nbsp;·&nbsp; <b>LSD:</b> {pendingFacts.site_lsd || "—"}
                </div>
                {pendingFacts.source_files.length > 0 ? (
                  <ul style={{ margin: "0 0 12px", paddingLeft: 20, fontSize: 13 }}>
                    {pendingFacts.source_files.map((f, i) => (
                      <li key={i}>{CATEGORY_LABELS[f.category] ?? f.category}: {f.name}</li>
                    ))}
                  </ul>
                ) : (
                  <div style={{ fontSize: 13, color: "var(--muted, #6b8090)", marginBottom: 12 }}>
                    No source file metadata in this file.
                  </div>
                )}
                <div style={{ display: "flex", gap: 12 }}>
                  <button className="btn primary" onClick={() => doConfirmFacts(true)} disabled={busy}>
                    {busy ? "Loading…" : "Yes, continue"}
                  </button>
                  <button className="btn" onClick={() => doConfirmFacts(false)} disabled={busy}>
                    No, cancel
                  </button>
                </div>
              </div>
            )}

            {factsLoaded && (
              <div>
                <div className="sf-dashboard">
                  <div className="sf-sidebar">
                    {sourceNav.map((sec) => (
                      <button
                        key={sec.id}
                        className={`sf-section ${reviewSection === sec.id ? "active" : ""}`}
                        onClick={() => setReviewSection(sec.id)}
                        title={sec.title}
                      >
                        {sec.title}
                      </button>
                    ))}
                  </div>
                  <div className="sf-pane">
                    {reviewSection === "identity" ? (
                      <div>
                        <div className="sf-card">
                          <div className="sf-card-title">Identity (editable)</div>
                          <div style={{ marginTop: 12 }}>
                            {IDENTITY_FIELDS.map((f) => (
                              <div key={f.key} className="sf-field">
                                <label className="sf-label">{f.label}</label>
                                <input
                                  type="text"
                                  className="iq-input"
                                  value={String(siteFacts[f.key] ?? "")}
                                  onChange={(e) => setSiteFacts((sf) => ({ ...sf, [f.key]: e.target.value }))}
                                />
                              </div>
                            ))}
                          </div>
                        </div>

                        {flags.length > 0 && (
                          <div className="sf-card">
                            <div className="sf-card-title">Extraction flags — resolve each</div>
                            <div style={{ marginTop: 10 }}>
                              {flags.map((f, i) => (
                                <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 6, fontSize: 13 }}>
                                  <IcAlert className="nav-ico" />
                                  <span style={{ flex: 1 }}>{f.message}{f.field ? ` (field: ${f.field})` : ""}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        <div style={{ display: "flex", gap: 12, marginTop: 4, flexWrap: "wrap" }}>
                          <label className="btn" style={{ cursor: "pointer", margin: 0 }}>
                            Load cached site facts
                            <input
                              type="file" accept=".json" style={{ display: "none" }}
                              onChange={(e) => { if (e.target.files?.[0]) doInspectFacts(e.target.files[0]); e.target.value = ""; }}
                            />
                          </label>
                          <button className="btn" onClick={doDownloadFacts}>
                            <IcDownload className="nav-ico" /> Download site facts
                          </button>
                          <button className="btn primary" onClick={doConfirmExtract} disabled={busy}>
                            {busy ? "Saving…" : "Confirm & continue"}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <SourceFactsView
                        title={sourceNav.find((s) => s.id === reviewSection)?.title ?? ""}
                        data={reviewSection === "identity" ? null : siteFacts[sourceNav.find((s) => s.id === reviewSection)?.dataKey ?? ""]}
                      />
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ===== Step 3: Intake ===== */}
      {step === 3 && (
        <div className="card">
          <div className="card-head"><div className="card-title">Intake questions</div></div>
          <div style={{ padding: 24 }}>
            {!intake && (
              <div>
                <p style={{ fontSize: 13.5, color: "var(--muted, #6b8090)", marginBottom: 16 }}>
                  Analyze the data to determine which intake questions apply.
                </p>
                <button className="btn primary" onClick={doPrepare} disabled={busy}>
                  {busy ? "Analyzing…" : "Analyze data"}
                </button>
              </div>
            )}

            {intake && (
              <div>
                <div className="iq-dashboard">
                  <div className="iq-sidebar">
                    {intakeSections.map((sec) => (
                      <button
                        key={sec.id}
                        className={`iq-section ${activeSec?.id === sec.id ? "active" : ""}`}
                        onClick={() => setActiveSection(sec.id)}
                      >
                        {sec.title}
                      </button>
                    ))}
                  </div>
                  <div className="iq-pane">
                    {activeSec && (
                      <>
                        {(activeSec.auto.length > 0 || (activeSec.info && activeSec.info.length > 0)) && (
                          <div className="iq-auto">
                            {activeSec.auto.map((a) => (
                              <div key={a.id}>
                                {typeof a.value === "object" && a.value !== null ? (
                                  <>
                                    <div className="iq-auto-row">
                                      <span className="iq-auto-label">{a.title}</span>
                                      <span className="iq-auto-value" />
                                    </div>
                                    {Object.entries(a.value as Record<string, unknown>).map(([k, v]) => (
                                      <div key={k} className="iq-auto-row iq-auto-nested">
                                        <span className="iq-auto-label">{humanizeKey(k)}</span>
                                        <span className="iq-auto-value">{typeof v === "object" ? JSON.stringify(v) : String(v ?? "—")}</span>
                                      </div>
                                    ))}
                                  </>
                                ) : (
                                  <div className="iq-auto-row">
                                    <span className="iq-auto-label">{a.title}</span>
                                    <span className="iq-auto-value">{String(a.value ?? "—")}</span>
                                  </div>
                                )}
                              </div>
                            ))}
                            {activeSec.info && activeSec.info.map((i) => (
                              <div key={i.label} className="iq-auto-row">
                                <span className="iq-auto-label">{i.label}</span>
                                <span className="iq-auto-value">{i.value}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {activeSec.questions.map((q) => (
                          <QuestionField key={q.id} q={q} value={answers[q.id]} onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))} />
                        ))}
                      </>
                    )}
                  </div>
                </div>
                <div style={{ marginTop: 20 }}>
                  <button className="btn primary" onClick={doSubmitIntake} disabled={busy}>
                    {busy ? "Submitting…" : "Submit & continue"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ===== Step 4: Generate ===== */}
      {step === 4 && (
        <div className="card">
          <div className="card-head"><div className="card-title">Generate report</div></div>
          <div style={{ padding: 24 }}>
            {!jobId && (
              <div>
                <p style={{ fontSize: 13.5, color: "var(--muted, #6b8090)", marginBottom: 16 }}>
                  One action runs the full hands-off pipeline: regenerate with your intake answers,
                  author every section, apply the operations, and build the practitioner hand-off.
                </p>
                <button className="btn primary" onClick={doGenerate} disabled={busy}>
                  <IcPlay className="nav-ico" /> {busy ? "Starting…" : "Generate Report"}
                </button>
              </div>
            )}

            {jobId && job && job.status !== "done" && job.status !== "error" && (
              <div>
                {job.stages.map((s, i) => (
                  <div key={i} style={{ fontSize: 13, color: s.status === "done" ? "var(--success, #1a7f37)" : "var(--muted, #6b8090)", marginBottom: 6 }}>
                    {s.status === "done" ? "✓" : "⏳"} {s.message}
                  </div>
                ))}
              </div>
            )}

            {jobId && job?.status === "error" && (
              <ErrorBox message={job.error ?? "Generation failed"} />
            )}
          </div>
        </div>
      )}

      {/* ===== Step 5: Done ===== */}
      {step === 5 && (
        <div className="card">
          <div className="card-head"><div className="card-title">Report ready</div></div>
          <div style={{ padding: 24 }}>
            <div style={{ fontSize: 13.5, marginBottom: 16 }}>
              <IcCheck className="nav-ico" /> The report and practitioner hand-off are ready to download.
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              <button className="btn primary" onClick={() => doDownload("report")}>
                <IcDownload className="nav-ico" /> Download report
              </button>
              <button className="btn" onClick={() => doDownload("practitioner")}>
                <IcDownload className="nav-ico" /> Practitioner info
              </button>
            </div>
            <div style={{ marginTop: 20 }}>
              <button className="btn" onClick={resetWizard}>Start a new report</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Question field                                                      */
/* ------------------------------------------------------------------ */

function QuestionField({ q, value, onChange }: {
  q: IntakeQuestion;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  return (
    <div className="iq-question">
      <div className="iq-question-title">{q.title}</div>
      <div className="iq-question-prompt">{q.prompt}</div>
      {q.type === "radio" && q.options && (
        <div className="iq-options">
          {q.options.map((opt) => (
            <label key={opt} className={`iq-option ${value === opt ? "selected" : ""}`}>
              <input
                type="radio"
                name={q.id}
                checked={value === opt}
                onChange={() => onChange(opt)}
              />
              {opt}
            </label>
          ))}
        </div>
      )}
      {q.type === "textarea" && (
        <textarea
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          rows={4}
          className="iq-input"
        />
      )}
      {q.type === "text" && (
        <input
          type="text"
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          className="iq-input"
        />
      )}
      {q.type === "table" && q.columns && (
        <BoreholeTable
          columns={q.columns}
          value={Array.isArray(value) ? (value as Record<string, string>[]) : []}
          onChange={onChange}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Interactive borehole table (Q22a: exploratory boreholes + APECs)    */
/* ------------------------------------------------------------------ */

function BoreholeTable({ columns, value, onChange }: {
  columns: { key: string; label: string }[];
  value: Record<string, string>[];
  onChange: (v: unknown) => void;
}) {
  // Always show at least one editable row.
  const rows = value.length > 0 ? value : [{}];

  const setRow = (i: number, key: string, v: string) => {
    const next = rows.map((r, j) => (j === i ? { ...r, [key]: v } : r));
    onChange(next);
  };
  const addRow = () => onChange([...rows, {}]);
  const removeRow = (i: number) => {
    const next = rows.filter((_, j) => j !== i);
    onChange(next.length ? next : [{}]);
  };

  return (
    <div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{ textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--line, #e4ebef)", color: "var(--muted, #6b8090)", fontWeight: 600 }}>
                {c.label}
              </th>
            ))}
            <th style={{ width: 40 }} />
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.key} style={{ padding: "4px 8px", borderBottom: "1px solid var(--line, #e4ebef)" }}>
                  <input
                    type="text"
                    value={String(r[c.key] ?? "")}
                    onChange={(e) => setRow(i, c.key, e.target.value)}
                    className="iq-input"
                    style={{ padding: "6px 8px", fontSize: 13 }}
                  />
                </td>
              ))}
              <td style={{ padding: "4px 8px", borderBottom: "1px solid var(--line, #e4ebef)" }}>
                <button onClick={() => removeRow(i)} style={{ background: "none", border: "none", color: "var(--danger, #c0492f)", cursor: "pointer" }}>✕</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button className="btn" onClick={addRow} style={{ marginTop: 8 }}>+ Add borehole</button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Read-only source facts view (Step 2 review, non-Identity sections)  */
/* ------------------------------------------------------------------ */

function SourceFactsView({ title, data }: { title: string; data: unknown }) {
  // Open by default so the extracted fields are immediately visible.
  const [open, setOpen] = useState(true);
  return (
    <div className="sf-card">
      <div className="sf-card-head" onClick={() => setOpen(!open)}>
        <span className="sf-card-title">{title}</span>
        <IcChevron className={`sf-chev ${open ? "open" : ""}`} />
      </div>
      {open && (
        <div style={{ marginTop: 10 }}>
          <FieldRows data={data} />
        </div>
      )}
    </div>
  );
}

function FieldRows({ data, depth = 0 }: { data: unknown; depth?: number }) {
  const pad = { paddingLeft: depth * 18 };
  if (data === null || data === undefined) {
    return <div className="sf-row" style={pad}><span className="sf-value">—</span></div>;
  }
  if (Array.isArray(data)) {
    if (data.length === 0) {
      return <div className="sf-row" style={pad}><span className="sf-value">[]</span></div>;
    }
    return (
      <>
        {data.map((item, i) => (
          <div key={i}>
            <div className="sf-row" style={pad}><span className="sf-label">[{i}]</span></div>
            <FieldRows data={item} depth={depth + 1} />
          </div>
        ))}
      </>
    );
  }
  if (typeof data === "object") {
    return (
      <>
        {Object.entries(data as Record<string, unknown>).map(([k, v]) => (
          <div key={k}>
            {v !== null && typeof v === "object" ? (
              <>
                <div className="sf-row" style={pad}><span className="sf-label">{k}</span></div>
                <FieldRows data={v} depth={depth + 1} />
              </>
            ) : (
              <div className="sf-row" style={pad}>
                <span className="sf-label">{k}</span>
                <span className="sf-value">{formatValue(v)}</span>
              </div>
            )}
          </div>
        ))}
      </>
    );
  }
  return <div className="sf-row" style={pad}><span className="sf-value">{formatValue(data)}</span></div>;
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}