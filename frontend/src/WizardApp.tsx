import { useEffect, useMemo, useRef, useState } from "react";
import { getSchema, uploadFile, runWorkflow } from "./api";
import type {
  Schema, RunResult, Params, InputSpec, OptionMap, TableData, Notice,
} from "./types";
import { Field } from "./components/Field";
import ResultsViewer from "./ResultsViewer";
import {
  IcUpload, IcSliders, IcChart, IcCheck, IcFile, IcPlay, IcInbox, IcDownload,
} from "./components/icons";

/* ------------------------------------------------------------------ */
/* Wizard steps                                                        */
/* ------------------------------------------------------------------ */

const STEPS = [
  { id: 1, title: "Upload", desc: "Add your soil analytical file", icon: IcUpload },
  { id: 2, title: "Configure", desc: "Set analysis parameters", icon: IcSliders },
  { id: 3, title: "Workflows", desc: "Review every workflow", icon: IcChart },
  { id: 4, title: "Confirm", desc: "Download outputs", icon: IcCheck },
];

function initialParams(schema: Schema): Params {
  const p: Params = {};
  for (const inp of schema.inputs) {
    if (["multiselect", "file"].includes(inp.control)) continue;
    if (inp.control === "toggle") p[inp.name] = inp.example ?? false;
    else if (inp.example != null) p[inp.name] = inp.example;
  }
  return p;
}

// references are compared `> 0` in the notebook, so null must become 0.
function cleanParams(p: Params): Params {
  const out: Params = { ...p };
  for (const k of Object.keys(out)) {
    if (k.endsWith("_reference") && (out[k] == null || out[k] === "")) out[k] = 0;
  }
  return out;
}

/* ------------------------------------------------------------------ */
/* Main wizard                                                         */
/* ------------------------------------------------------------------ */

export default function WizardApp() {
  const [schema, setSchema] = useState<Schema | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [filename, setFilename] = useState("");
  const [options, setOptions] = useState<OptionMap>({});
  const [params, setParams] = useState<Params>({});
  const [result, setResult] = useState<RunResult | null>(null);
  const [step, setStep] = useState(1);
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);
  const [drag, setDrag] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getSchema().then((s) => { setSchema(s); setParams(initialParams(s)); });
  }, []);

  const setParam = (name: string, v: unknown) => {
    setParams((p) => ({ ...p, [name]: v }));
    // Option A: when the SST toggle changes, re-fetch the schema so the
    // SST tabs/outputs/charts/params appear or disappear immediately.
    if (name === "sst_flag") {
      getSchema(Boolean(v)).then((s) => {
        setSchema(s);
        // Preserve the user's current params where possible; the new schema
        // may have dropped SST params, so re-seed from the fresh schema but
        // keep any values the user already set.
        const merged: Params = { ...initialParams(s), ...params, [name]: v };
        setParams(merged);
      });
    }
  };

  async function doUpload(file: File) {
    setUploading(true);
    try {
      const res = await uploadFile(file);
      setToken(res.token); setFilename(res.filename); setOptions(res.options);
      const prefilled: Params = { ...params };
      for (const inp of schema?.inputs ?? []) {
        if (inp.control === "multiselect" && inp.prefill === "all" && inp.options) {
          const src = res.options[inp.options];
          if (Array.isArray(src)) prefilled[inp.name] = src.map(String);
        }
        if (inp.control === "subarea_assigner" && inp.options) {
          const src = res.options[inp.options] as TableData | undefined;
          if (src && Array.isArray(src.rows)) {
            prefilled[inp.name] = src.rows.map((r) => ({
              subarea: String(r.Subarea ?? ""),
              boreholes: String(r.Boreholes ?? "")
                .split(",").map((s) => s.trim()).filter(Boolean),
            }));
          }
        }
        // Seed the SST Charts Chloride Plot Config table from the file-derived
        // subarea default (each row: { subarea, excluded_boreholes: [],
        // additional_reference_lines: [] }).
        if (inp.control === "table" && inp.options) {
          const src = res.options[inp.options] as TableData | undefined;
          if (src && Array.isArray(src.rows)) {
            prefilled[inp.name] = src.rows.map((r) => ({
              subarea: String(r.subarea ?? ""),
              excluded_boreholes: Array.isArray(r.excluded_boreholes)
                ? (r.excluded_boreholes as string[])
                : [],
              additional_reference_lines: Array.isArray(r.additional_reference_lines)
                ? (r.additional_reference_lines as string[])
                : [],
            }));
          }
        }
      }
      setParams(prefilled);
      // auto-run once so the user immediately sees results
      await doRun(res.token, prefilled);
    } catch (e) {
      alert(`Upload failed: ${(e as Error).message}`);
    } finally { setUploading(false); }
  }

  async function doRun(tok = token, p = params) {
    if (!tok) return;
    setRunning(true);
    try {
      const res = await runWorkflow(tok, cleanParams(p));
      setResult(res);
      if (res.options) setOptions((o) => ({ ...o, ...res.options }));
    } catch (e) {
      alert(`Run failed: ${(e as Error).message}`);
    } finally { setRunning(false); }
  }

  async function runAndAdvance() {
    await doRun();
    setStep(3);
  }

  if (!schema) {
    return (
      <div className="wizard">
        <div className="wizard-loading">
          <div className="spinner" />
          <p>Loading workspace…</p>
        </div>
      </div>
    );
  }

  const canGo = (s: number) => {
    if (s === 1) return true;
    if (s === 2) return Boolean(token);
    if (s === 3) return Boolean(token);
    if (s === 4) return Boolean(result);
    return false;
  };

  const go = (s: number) => { if (canGo(s)) setStep(s); };

  return (
    <div className="wizard">
      {/* ---------- Header ---------- */}
      <header className="wz-header">
        <div className="wz-brand">
          <div className="wz-brand-mark">SS</div>
          <div>
            <div className="wz-brand-name">EBM Soil / SST</div>
            <div className="wz-brand-sub">Guided analytical workspace</div>
          </div>
        </div>
        <div className="wz-file">
          {token ? (
            <div className="wz-file-chip"><span className="dot" /><span className="wz-file-name">{filename}</span></div>
          ) : (
            <span className="wz-file-empty">No file loaded</span>
          )}
        </div>
      </header>

      {/* ---------- Stepper ---------- */}
      <nav className="wz-stepper">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          const active = step === s.id;
          const done = step > s.id;
          const reachable = canGo(s.id);
          return (
            <div key={s.id} className={`wz-step ${active ? "active" : ""} ${done ? "done" : ""} ${reachable ? "reachable" : ""}`}
              onClick={() => go(s.id)}>
              <div className="wz-step-ico">
                {done ? <IcCheck className="" style={{ width: 16, height: 16 }} /> : <Icon className="" style={{ width: 16, height: 16 }} />}
              </div>
              <div className="wz-step-text">
                <div className="wz-step-title">{s.title}</div>
                <div className="wz-step-desc">{s.desc}</div>
              </div>
              {i < STEPS.length - 1 && <div className={`wz-step-line ${done ? "done" : ""}`} />}
            </div>
          );
        })}
      </nav>

      {/* ---------- Body ---------- */}
      <main className={`wz-body ${step === 3 ? "wide" : ""}`}>
        {step === 1 && (
          <UploadStep
            token={token} filename={filename} uploading={uploading} drag={drag}
            setDrag={setDrag} fileInput={fileInput} doUpload={doUpload}
            onNext={() => go(2)}
          />
        )}

        {step === 2 && (
          <ConfigureStep
            schema={schema} params={params} options={options} setParam={setParam}
            running={running} onRun={runAndAdvance} onBack={() => go(1)}
          />
        )}

        {step === 3 && (
          <ResultsStep
            schema={schema} result={result} options={options} params={params}
            setParam={setParam} running={running} onRun={() => doRun()}
            onBack={() => go(2)} onNext={() => go(4)}
          />
        )}

        {step === 4 && (
          <ConfirmStep
            schema={schema} result={result} filename={filename}
            onBack={() => go(3)} onRestart={() => { setStep(1); setResult(null); setToken(null); setFilename(""); setParams(initialParams(schema)); }}
          />
        )}
      </main>

      {/* ---------- Footer nav ---------- */}
      <footer className="wz-footer">
        <div className="wz-footer-left">
          {step > 1 && (
            <button className="btn btn-ghost" onClick={() => go(step - 1)}>← Back</button>
          )}
        </div>
        <div className="wz-footer-right">
          {step === 1 && (
            <button className="btn btn-primary" disabled={!token} onClick={() => go(2)}>
              Continue to Configure →
            </button>
          )}
          {step === 2 && (
            <button className="btn btn-primary" disabled={!token || running} onClick={runAndAdvance}>
              {running ? <><span className="spinner" style={{ borderTopColor: "#fff", borderColor: "rgba(255,255,255,0.4)" }} /> Running…</> : <><IcPlay className="" style={{ width: 15, height: 15 }} /> Run analysis & view results</>}
            </button>
          )}
          {step === 3 && (
            <button className="btn btn-primary" disabled={!result} onClick={() => go(4)}>
              Continue to Confirm →
            </button>
          )}
          {step === 4 && (
            <button className="btn btn-ghost" onClick={() => { setStep(1); setResult(null); setToken(null); setFilename(""); setParams(initialParams(schema)); }}>
              Start over
            </button>
          )}
        </div>
      </footer>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Step 1 — Upload                                                     */
/* ------------------------------------------------------------------ */

function UploadStep({ token, filename, uploading, drag, setDrag, fileInput, doUpload, onNext }: {
  token: string | null; filename: string; uploading: boolean; drag: boolean;
  setDrag: (d: boolean) => void; fileInput: React.RefObject<HTMLInputElement>;
  doUpload: (f: File) => void; onNext: () => void;
}) {
  return (
    <div className="wz-panel fade-in">
      <div className="wz-panel-head">
        <h2>Upload your soil analytical file</h2>
        <p>Start by adding the <b>.xlsm</b> workbook. The file is parsed once, then every workflow runs against it.</p>
      </div>

      <input ref={fileInput} type="file" accept=".xlsm,.xlsx" style={{ display: "none" }}
        onChange={(e) => e.target.files?.[0] && doUpload(e.target.files[0])} />

      {token ? (
        <div className="dropzone loaded" onClick={() => fileInput.current?.click()}>
          <div className="dz-fileicon"><IcFile className="" style={{ width: 20, height: 20 }} /></div>
          <div style={{ flex: 1 }}>
            <div className="dz-title" style={{ fontSize: 14 }}>{filename}</div>
            <div className="dz-sub">Loaded and analyzed · click to replace</div>
          </div>
          <button className="btn btn-ghost">Replace file</button>
        </div>
      ) : (
        <div className={`dropzone ${drag ? "drag" : ""}`}
          onClick={() => fileInput.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); e.dataTransfer.files?.[0] && doUpload(e.dataTransfer.files[0]); }}>
          {uploading ? <div className="spinner" style={{ margin: "0 auto 12px" }} /> : <IcUpload className="dz-ico" />}
          <div className="dz-title">{uploading ? "Analyzing…" : "Drop your Soil Analytical File here"}</div>
          <div className="dz-sub">{uploading ? "Parsing the workbook and computing options" : "or click to browse · .xlsm"}</div>
        </div>
      )}

      <div className="wz-tip">
        <IcInbox className="" style={{ width: 18, height: 18 }} />
        <div>
          <b>What happens next?</b> Once the file loads, the analysis runs automatically. You'll review the parameters on the next step, then see every workflow's tables and charts.
        </div>
      </div>

      {token && (
        <div className="wz-panel-actions">
          <button className="btn btn-primary" onClick={onNext}>Continue to Configure →</button>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Step 2 — Configure                                                  */
/* ------------------------------------------------------------------ */

function ConfigureStep({ schema, params, options, setParam, running, onRun, onBack }: {
  schema: Schema; params: Params; options: OptionMap;
  setParam: (n: string, v: unknown) => void;
  running: boolean; onRun: () => void; onBack: () => void;
}) {
  // Only the shared (common) parameters belong on this step — the inputs on the
  // "input_config" tab (sheet name, chloride guideline, SST flag, topsoil
  // depths, water table depth). Workflow-specific inputs (TDS, Texture, Tier 1
  // Graphs, BG Chloride, 95th Percentile) are edited per-workflow in the
  // Results step, where their input cards live.
  const shared = useMemo(
    () => schema.inputs.filter((i) => i.tab === "input_config" && i.control !== "file"),
    [schema]
  );
  const sst = shared.filter((i) => i.group === "sst");
  const common = shared.filter((i) => i.group !== "sst");

  return (
    <div className="wz-panel fade-in">
      <div className="wz-panel-head">
        <h2>Configure the analysis</h2>
        <p>These are the shared parameters that apply to every workflow. Defaults are pre-filled from the file — adjust what you need. Workflow-specific settings are available on each workflow's tab in the Results step.</p>
      </div>

      <div className="wz-config">
        {common.length > 0 && (
          <div className="card">
            <div className="card-head">
              <div className="card-title">Shared inputs</div>
              <div className="card-meta">Apply to every workflow</div>
            </div>
            <div style={{ padding: 24 }}>
              <FormGrid inputs={common} params={params} options={options} setParam={setParam} />
            </div>
          </div>
        )}
        {sst.length > 0 && Boolean(params.sst_flag) && (
          <div className="card">
            <div className="card-head">
              <div className="card-title">Site-specific (SST) inputs</div>
              <div className="card-meta">SST analysis</div>
            </div>
            <div style={{ padding: 24 }}>
              <FormGrid inputs={sst} params={params} options={options} setParam={setParam} />
            </div>
          </div>
        )}
      </div>

      <div className="wz-panel-actions">
        <button className="btn btn-ghost" onClick={onBack}>← Back</button>
        <button className="btn btn-primary" disabled={running} onClick={onRun}>
          {running ? <><span className="spinner" style={{ borderTopColor: "#fff", borderColor: "rgba(255,255,255,0.4)" }} /> Running…</> : <><IcPlay className="" style={{ width: 15, height: 15 }} /> Run analysis & view results</>}
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Step 3 — Results                                                    */
/* ------------------------------------------------------------------ */

function ResultsStep({ schema, result, options, params, setParam, running, onRun, onBack, onNext }: {
  schema: Schema; result: RunResult | null; options: OptionMap; params: Params;
  setParam: (n: string, v: unknown) => void; running: boolean; onRun: () => void;
  onBack: () => void; onNext: () => void;
}) {
  return (
    <div className="wz-panel fade-in">
      {result && result.messages.length > 0 && <Notices messages={result.messages} />}

      {!result ? (
        <div className="empty-state">
          <IcInbox className="es-ico" />
          <h3>No results yet</h3>
          <p>Run the analysis to populate every workflow's tables and charts.</p>
        </div>
      ) : (
        <div className="wz-results-embed">
          <ResultsViewer
            schema={schema} result={result} options={options} params={params}
            setParam={setParam} running={running} onRun={onRun}
          />
        </div>
      )}

      <div className="wz-panel-actions">
        <button className="btn btn-ghost" onClick={onBack}>← Back</button>
        <button className="btn btn-primary" disabled={!result} onClick={onNext}>
          <IcDownload className="" style={{ width: 15, height: 15 }} /> Download Results
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Step 4 — Confirm                                                    */
/* ------------------------------------------------------------------ */

function ConfirmStep({ schema, result, filename, onBack, onRestart }: {
  schema: Schema; result: RunResult | null; filename: string;
  onBack: () => void; onRestart: () => void;
}) {
  const tableCount = result ? Object.keys(result.outputs).length : 0;
  const chartCount = result ? Object.keys(result.charts).length : 0;
  const rowCount = result
    ? Object.values(result.outputs).reduce((n, t) => n + (t?.rows.length ?? 0), 0)
    : 0;
  const errorCount = result?.messages.filter((m) => m.level === "error").length ?? 0;

  return (
    <div className="wz-panel fade-in">
      <div className="wz-panel-head">
        <h2>Confirm & export</h2>
        <p>Your analysis is complete. Review the summary below — file export is coming soon.</p>
      </div>

      <div className="wz-confirm-grid">
        <div className="card wz-confirm-card">
          <div className="card-head"><div className="card-title">Analysis summary</div></div>
          <div className="wz-confirm-body">
            <div className="wz-confirm-row">
              <span className="wz-confirm-label">Input file</span>
              <span className="wz-confirm-value">{filename || "—"}</span>
            </div>
            <div className="wz-confirm-row">
              <span className="wz-confirm-label">Workflows</span>
              <span className="wz-confirm-value">{schema.tabs.filter((t) => t.id !== "input_config").length}</span>
            </div>
            <div className="wz-confirm-row">
              <span className="wz-confirm-label">Tables</span>
              <span className="wz-confirm-value">{tableCount}</span>
            </div>
            <div className="wz-confirm-row">
              <span className="wz-confirm-label">Charts</span>
              <span className="wz-confirm-value">{chartCount}</span>
            </div>
            <div className="wz-confirm-row">
              <span className="wz-confirm-label">Rows of output</span>
              <span className="wz-confirm-value">{rowCount.toLocaleString()}</span>
            </div>
            <div className="wz-confirm-row">
              <span className="wz-confirm-label">Notices</span>
              <span className={`wz-confirm-value ${errorCount ? "err" : ""}`}>
                {result?.messages.length ?? 0}{errorCount ? ` (${errorCount} error${errorCount !== 1 ? "s" : ""})` : ""}
              </span>
            </div>
          </div>
        </div>

        <div className="card wz-confirm-card">
          <div className="card-head"><div className="card-title">Download results</div><span className="soon-tag">Coming soon</span></div>
          <div className="wz-confirm-body">
            <p className="wz-confirm-note">
              Export of the result tables and charts (Excel / PDF) is not implemented yet.
              This page is the placeholder for that flow.
            </p>
            <button className="btn btn-primary" disabled>
              <IcFile className="" style={{ width: 15, height: 15 }} /> Download results
            </button>
          </div>
        </div>
      </div>

      <div className="wz-panel-actions">
        <button className="btn btn-ghost" onClick={onBack}>← Back</button>
        <button className="btn btn-ghost" onClick={onRestart}>Start over</button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Shared bits                                                         */
/* ------------------------------------------------------------------ */

const NOTICE_ICON: Record<Notice["level"], string> = {
  error: "✕", warning: "⚠", info: "ℹ", success: "✓",
};

function Notices({ messages }: { messages?: Notice[] }) {
  if (!messages || messages.length === 0) return null;
  return (
    <div className="notices fade-in">
      {messages.map((m, i) => (
        <div key={i} className={`notice notice-${m.level}`}>
          <span className="notice-ico">{NOTICE_ICON[m.level] ?? "•"}</span>
          <div className="notice-body">
            {m.workflow && <span className="notice-wf">{m.workflow}</span>}
            <span className="notice-msg">{m.message}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function FormGrid({ inputs, params, options, setParam }: {
  inputs: InputSpec[]; params: Params; options: OptionMap; setParam: (n: string, v: unknown) => void;
}) {
  return (
    <div className="form-grid">
      {inputs.map((inp) => (
        <Field key={inp.name} spec={inp} value={params[inp.name]} options={options} params={params}
          onChange={(v) => setParam(inp.name, v)} />
      ))}
    </div>
  );
}