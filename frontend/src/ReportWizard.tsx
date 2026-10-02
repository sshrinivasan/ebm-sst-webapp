import { useCallback, useRef, useState } from "react";
import {
  reportStart, reportExtract, reportConfirmExtract, reportPrepare,
  reportGetIntake, reportSubmitIntake, reportGenerate, reportStatus,
  reportDownload, reportSession,
  REPORT_CATEGORIES,
  type ReportSession, type IntakeData, type JobStatus, type IntakeQuestion,
} from "./api";
import { IcUpload, IcCheck, IcPlay, IcDownload, IcFile, IcAlert } from "./components/icons";

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

const STEPS = [
  { id: 1, title: "Files" },
  { id: 2, title: "Extract & Review" },
  { id: 3, title: "Intake" },
  { id: 4, title: "Generate" },
  { id: 5, title: "Done" },
];

/* ------------------------------------------------------------------ */
/* Small building blocks                                               */
/* ------------------------------------------------------------------ */

function StepHeader({ step }: { step: number }) {
  return (
    <div className="subtabs" style={{ marginBottom: 16 }}>
      {STEPS.map((s) => (
        <button key={s.id} className={`subtab ${step === s.id ? "active" : ""}`}>
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
    <div style={{ padding: 12, margin: "12px 0", background: "var(--danger-bg, #3a1d1d)", border: "1px solid var(--danger, #c0392b)", borderRadius: 8, color: "var(--danger, #e74c3c)", fontSize: 13 }}>
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
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

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

  // Poll a background job until it finishes.
  const pollJob = useCallback(async (id: string) => {
    for (;;) {
      const st = await reportStatus(id);
      setJob(st);
      if (st.status === "done" || st.status === "error") return st;
      await new Promise((r) => setTimeout(r, 2000));
    }
  }, []);

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

  /* ------------------------------------------------------------------ */
  /* Render                                                              */
  /* ------------------------------------------------------------------ */

  return (
    <div style={{ padding: 24 }}>
      <StepHeader step={step} />
      {error && <ErrorBox message={error} />}

      {/* ===== Step 1: Files ===== */}
      {step === 1 && (
        <div className="card">
          <div className="card-head"><div className="card-title">Upload files</div></div>
          <div style={{ padding: 24 }}>
            <div
              className="dropzone"
              style={{
                border: `2px dashed ${drag ? "var(--accent, #4a9eff)" : "var(--line-2, #333)"}`,
                borderRadius: 10, padding: 28, textAlign: "center", cursor: "pointer",
                color: "var(--muted, #888)", fontSize: 13.5,
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
                      style={{ background: "var(--bg-2, #1a1a1a)", color: "var(--fg, #eee)", border: "1px solid var(--line-2, #333)", borderRadius: 6, padding: "4px 8px", fontSize: 12.5 }}
                    >
                      {REPORT_CATEGORIES.map((c) => (
                        <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>
                      ))}
                    </select>
                    <button onClick={() => removeFile(i)} style={{ background: "none", border: "none", color: "var(--danger, #e74c3c)", cursor: "pointer" }}>✕</button>
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
            {!jobId && (
              <div>
                <p style={{ fontSize: 13.5, color: "var(--muted, #888)", marginBottom: 16 }}>
                  The LLM reads the uploaded source documents (ABAData, Phaseview, Phase 1 ESA,
                  borehole logs) once and extracts the site facts. This typically takes 2–5 minutes.
                </p>
                <button className="btn primary" onClick={doExtract} disabled={busy}>
                  {busy ? "Extracting…" : "Extract site facts"}
                </button>
              </div>
            )}

            {jobId && job && job.status !== "done" && job.status !== "error" && (
              <div>
                {job.stages.map((s, i) => (
                  <div key={i} style={{ fontSize: 13, color: s.status === "done" ? "var(--success, #2ecc71)" : "var(--muted, #888)", marginBottom: 6 }}>
                    {s.status === "done" ? "✓" : "⏳"} {s.message}
                  </div>
                ))}
              </div>
            )}

            {jobId && job?.status === "done" && (
              <div>
                <div style={{ fontSize: 13.5, marginBottom: 12 }}>
                  <IcCheck className="nav-ico" /> Extraction complete. Review the extracted facts and resolve any flags below.
                </div>

                {flags.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <div className="subhead" style={{ marginBottom: 8 }}>Extraction flags — resolve each</div>
                    {flags.map((f, i) => (
                      <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 6, fontSize: 13 }}>
                        <IcAlert className="nav-ico" />
                        <span style={{ flex: 1 }}>{f.message}{f.field ? ` (field: ${f.field})` : ""}</span>
                      </div>
                    ))}
                  </div>
                )}

                <div className="subhead" style={{ marginBottom: 8 }}>Site facts (editable JSON)</div>
                <textarea
                  value={JSON.stringify(siteFacts, null, 2)}
                  onChange={(e) => {
                    try { setSiteFacts(JSON.parse(e.target.value)); } catch { /* keep last valid */ }
                  }}
                  rows={14}
                  style={{ width: "100%", background: "var(--bg-2, #1a1a1a)", color: "var(--fg, #eee)", border: "1px solid var(--line-2, #333)", borderRadius: 8, padding: 12, fontFamily: "monospace", fontSize: 12.5 }}
                />

                <div style={{ marginTop: 16 }}>
                  <button className="btn primary" onClick={doConfirmExtract} disabled={busy}>
                    {busy ? "Saving…" : "Confirm & continue"}
                  </button>
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
                <p style={{ fontSize: 13.5, color: "var(--muted, #888)", marginBottom: 16 }}>
                  Analyze the data to determine which intake questions apply.
                </p>
                <button className="btn primary" onClick={doPrepare} disabled={busy}>
                  {busy ? "Analyzing…" : "Analyze data"}
                </button>
              </div>
            )}

            {intake && (
              <div>
                {intake.auto_derived.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <div className="subhead" style={{ marginBottom: 8 }}>Auto-derived (from the data)</div>
                    {intake.auto_derived.map((a) => (
                      <div key={a.id} style={{ fontSize: 13, marginBottom: 4 }}>
                        <b>{a.title}:</b> {typeof a.value === "object" ? JSON.stringify(a.value) : String(a.value ?? "—")}
                      </div>
                    ))}
                  </div>
                )}

                {intake.questions.map((q) => (
                  <QuestionField key={q.id} q={q} value={answers[q.id]} onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))} />
                ))}

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
                <p style={{ fontSize: 13.5, color: "var(--muted, #888)", marginBottom: 16 }}>
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
                  <div key={i} style={{ fontSize: 13, color: s.status === "done" ? "var(--success, #2ecc71)" : "var(--muted, #888)", marginBottom: 6 }}>
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
    <div style={{ marginBottom: 16 }}>
      <div className="subhead" style={{ marginBottom: 6 }}>{q.title}</div>
      <div style={{ fontSize: 13, color: "var(--muted, #888)", marginBottom: 8 }}>{q.prompt}</div>
      {q.type === "radio" && q.options && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {q.options.map((opt) => (
            <label key={opt} style={{ fontSize: 13, display: "flex", gap: 8, alignItems: "center" }}>
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
          style={{ width: "100%", background: "var(--bg-2, #1a1a1a)", color: "var(--fg, #eee)", border: "1px solid var(--line-2, #333)", borderRadius: 8, padding: 10, fontSize: 13 }}
        />
      )}
      {q.type === "text" && (
        <input
          type="text"
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          style={{ width: "100%", background: "var(--bg-2, #1a1a1a)", color: "var(--fg, #eee)", border: "1px solid var(--line-2, #333)", borderRadius: 8, padding: 10, fontSize: 13 }}
        />
      )}
    </div>
  );
}