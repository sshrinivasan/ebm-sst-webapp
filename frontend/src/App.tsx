import { useEffect, useMemo, useRef, useState } from "react";
import { getSchema, uploadFile, runWorkflow } from "./api";
import type { Schema, RunResult, Params, InputSpec, OptionMap, NavNode, Notice, TableData } from "./types";
import { Field } from "./components/Field";
import { DataTable } from "./components/DataTable";
import { DepthSpecificTier1 } from "./components/DepthSpecificTier1";
import { FormGrid, CollapsibleInputs } from "./components/CollapsibleInputs";
import {
  IcSliders, IcTable, IcChart, IcAlert, IcMap, IcUpload, IcFile,
  IcSpark, IcPlay, IcInbox, IcChevron,
} from "./components/icons";

const ICONS: Record<string, (p: { className?: string }) => JSX.Element> = {
  sliders: IcSliders, table: IcTable, chart: IcChart, alert: IcAlert, map: IcMap,
};

function initialParams(schema: Schema): Params {
  const p: Params = {};
  for (const inp of schema.inputs) {
    // Prefill non-dataset controls from the example seed; leave wells/zones empty.
    if (inp.control === "file") continue;
    if (inp.control === "toggle") p[inp.name] = inp.example ?? false;
    // Multiselects with a default (e.g. show_chloride_exceedances) get seeded
    // here; file-derived multiselects have no default and stay empty until upload.
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

export default function App() {
  const [schema, setSchema] = useState<Schema | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [filename, setFilename] = useState<string>("");
  const [options, setOptions] = useState<OptionMap>({});
  const [params, setParams] = useState<Params>({});
  const [result, setResult] = useState<RunResult | null>(null);
  const [active, setActive] = useState("input_config");
  const [chartTab, setChartTab] = useState(1);
  const [bgChlorideSub, setBgChlorideSub] = useState<"data" | "charts">("data");
  const [bgChloridePlot, setBgChloridePlot] = useState(1);
  const [sstChartsSub, setSstChartsSub] = useState<"chloride" | "sodium" | "sar">("chloride");
  const [t1Sub, setT1Sub] = useState<"graphs" | "variable">("graphs");
  const [textureSub, setTextureSub] = useState<"tables" | "profile">("tables");
  const [p95Subarea, setP95Subarea] = useState<string | null>(null);
  const [p95Sub, setP95Sub] = useState<string>("subsoil");
  const [p95View, setP95View] = useState<"data" | "subareas">("data");
  const [outVar, setOutVar] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);
  const [drag, setDrag] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // SST is off by default, so fetch the schema without the SST tabs/params.
    getSchema(false).then((s) => { setSchema(s); setParams(initialParams(s)); });
  }, []);

  const setParam = (name: string, v: unknown) => {
    // Experimental-feature guard: turning SST on requires confirmation.
    if (name === "sst_flag" && Boolean(v) && !Boolean(params.sst_flag)) {
      if (!window.confirm("Site-specific (SST) analysis is an experimental feature. Are you sure you want to continue?")) {
        return;
      }
    }
    setParams((p) => ({ ...p, [name]: v }));
  };

  async function doUpload(file: File) {
    setUploading(true);
    try {
      const res = await uploadFile(file);
      setToken(res.token); setFilename(res.filename); setOptions(res.options);
      // preselect every option for multiselects marked prefill:"all" now that
      // their file-derived option lists are known (e.g. plot all boreholes).
      const prefilled: Params = { ...params };
      // Reset the editable SCARG guidelines table on a new upload so the first
      // run recomputes them from the new file (the auto-populate in doRun only
      // fills the table when it's empty).
      prefilled["scarg_guidelines"] = [];
      for (const inp of schema?.inputs ?? []) {
        if (inp.control === "multiselect" && inp.prefill === "all" && inp.options) {
          const src = res.options[inp.options];
          if (Array.isArray(src)) prefilled[inp.name] = src.map(String);
        }
        // Seed the subarea assigner from the file-derived borehole_sa_df mapping.
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

  if (!schema) return <div className="empty-state" style={{ marginTop: 120 }}><div className="spinner" style={{ margin: "0 auto" }} /></div>;

  const tab = schema.tabs.find((t) => t.id === active)!;
  const tabInputs = schema.inputs.filter((i) => i.tab === active && i.control !== "file");
  const tabOutputs = schema.outputs.filter((o) => o.tab === active);
  const tabCharts = schema.charts.filter((c) => c.tab === active);
  // Dynamic outputs (e.g. texture_split_0/1/...) present in the run result for
  // this tab, rendered as their own subtabs. Label derived from the key suffix.
  const dynamicOutputs = (schema.dynamic_outputs ?? [])
    .filter((d) => d.tab === active)
    .flatMap((d) =>
      Object.keys(result?.outputs ?? {})
        .filter((k) => k.startsWith(d.prefix))
        .map((k) => {
          // key suffix is "start-end" (e.g. "0-1.5") -> "Depth: 0-1.5m"
          const range = k.slice(d.prefix.length).replace("-", " to ");
          return { var: k, label: `${d.label_prefix ?? ""}${range}m` };
        })
    );
  const allOutputs = [...tabOutputs, ...dynamicOutputs];
  // when a tab has >1 output, show them as in-page subtabs (one at a time)
  const selectedOut = allOutputs.find((o) => o.var === outVar) ?? allOutputs[0];
  const shownOutputs = allOutputs.length > 1 ? (selectedOut ? [selectedOut] : []) : allOutputs;
  // breadcrumb: find the group (if any) that contains the active leaf
  const parent = schema.nav.find((n) => n.children?.some((c) => c.id === active));
  const leafCount = (id: string) =>
    schema.outputs.filter((o) => o.tab === id && result?.outputs[o.var]?.rows.length).length;

  return (
    <div className="app">
      {/* ---------- Sidebar ---------- */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">SS</div>
          <div>
            <div className="brand-name">EBM Soil / SST</div>
            <div className="brand-sub">Analytical workspace</div>
          </div>
        </div>
        <div className="nav-label">Workspace</div>
        <nav className="nav">
          {schema.nav.map((node) => {
            if (!node.children) {
              const Icon = ICONS[node.icon ?? "table"] ?? IcTable;
              const count = leafCount(node.id!);
              return (
                <button key={node.id} className={`nav-item ${active === node.id ? "active" : ""}`} onClick={() => setActive(node.id!)}>
                  <Icon className="nav-ico" />{node.title}
                  {count > 0 && <span className="nav-badge">{count}</span>}
                </button>
              );
            }
            // group with children
            const GIcon = ICONS[node.icon ?? "table"] ?? IcTable;
            const open = collapsed[node.title] !== true;
            const childActive = node.children.some((c) => c.id === active);
            return (
              <div key={node.title}>
                <button className={`nav-item group ${childActive ? "has-active" : ""}`}
                  onClick={() => setCollapsed((c) => ({ ...c, [node.title]: open }))}>
                  <GIcon className="nav-ico" />{node.title}
                  <IcChevron className={`nav-chev ${open ? "open" : ""}`} />
                </button>
                {open && (
                  <div className="nav-children">
                    {node.children.map((c) => {
                      const count = leafCount(c.id!);
                      return (
                        <button key={c.id} className={`nav-item child ${active === c.id ? "active" : ""}`} onClick={() => setActive(c.id!)}>
                          <span className="child-dot" />{c.title}
                          {count > 0 && <span className="nav-badge">{count}</span>}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          {token ? (
            <div className="file-chip"><span className="dot" /><span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{filename}</span></div>
          ) : (
            <span>No file loaded yet</span>
          )}
        </div>
      </aside>

      {/* ---------- Main ---------- */}
      <main className="main">
        <div className="topbar">
          <div>
            <div className="crumb">Soil / SST{parent ? ` · ${parent.title}` : ""} · {tab.title}</div>
            <h1>{parent ? `${parent.title} — ${tab.title}` : tab.title}</h1>
          </div>
          <button className="btn btn-primary" disabled={!token || running} onClick={() => doRun()}>
            {running ? <><span className="spinner" style={{ borderTopColor: "#fff", borderColor: "rgba(255,255,255,0.4)" }} /> Running…</> : <><IcPlay className="" style={{ width: 15, height: 15 }} /> Re-run analysis</>}
          </button>
        </div>

        <div className={`content ${active !== "input_config" ? "wide" : ""}`}>
          <Notices messages={result?.messages} />
          {/* ===== Input Configuration ===== */}
          {active === "input_config" && (
            <div className="stack fade-in">
              <UploadZone {...{ token, filename, uploading, drag, setDrag, fileInput, doUpload }} />
              <AiSeam />
              <div className="card">
                <div className="card-head"><div className="card-title">Shared inputs</div><div className="card-meta">Apply to every workflow</div></div>
                <div style={{ padding: 24 }}>
                  <FormGrid inputs={tabInputs.filter((i) => i.group !== "sst")} params={params} options={options} setParam={setParam} />
                </div>
              </div>
              {Boolean(params.sst_flag) && (
                <div className="card">
                  <div className="card-head"><div className="card-title">SST inputs</div><div className="card-meta">Site-specific (SST) analysis</div></div>
                  <div style={{ padding: 24 }}>
                    <FormGrid inputs={tabInputs.filter((i) => i.group === "sst")} params={params} options={options} setParam={setParam} />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ===== TDS Charts (in-page tab row, one graph at a time) ===== */}
          {active === "tds_charts" && (
            <div className="stack fade-in">
              {!token && <NeedFile />}
              <div className="subtabs">
                {[1, 2, 3].map((n) => {
                  const param = params[`gw_graph_${n}`] as string | undefined;
                  return (
                    <button key={n} className={`subtab ${chartTab === n ? "active" : ""}`}
                      onClick={() => setChartTab(n)}>
                      Graph {n}{param ? <span className="subtab-sub"> · {param}</span> : ""}
                    </button>
                  );
                })}
              </div>
              <GraphPanel n={chartTab} schema={schema} params={params} options={options}
                setParam={setParam} result={result} />
            </div>
          )}

          {/* ===== Tier 1 Graphs (sub-tabs: standard profiles + variable graphs) ===== */}
          {active === "tier1_graphs" && (
            <div className="stack fade-in">
              {!token && <NeedFile />}
              <div className="subtabs">
                <button className={`subtab ${t1Sub === "graphs" ? "active" : ""}`}
                  onClick={() => setT1Sub("graphs")}>Tier 1 Graphs</button>
                <button className={`subtab ${t1Sub === "variable" ? "active" : ""}`}
                  onClick={() => setT1Sub("variable")}>Variable Graphs</button>
              </div>

              {t1Sub === "graphs" && (
                <>
                  {!token && <NeedFile />}
                  {token && (
                    <div className="card">
                      <div className="card-head"><div className="card-title">Tier 1 Graphs inputs</div></div>
                      <div style={{ padding: 24 }}>
                        <FormGrid inputs={schema.inputs.filter((i) => i.name === "tier1_graph_samples")}
                          params={params} options={options} setParam={setParam} />
                      </div>
                    </div>
                  )}
                  {token && (
                    <div className="chart-row">
                      {schema.charts
                        .filter((c) => c.tab === "tier1_graphs" && !c.var.startsWith("tier1_variable_graph"))
                        .map((c) => (
                          <div className="card chart-card" key={c.var}>
                            <div className="card-head"><div className="card-title">{c.label}</div></div>
                            {result?.charts[c.var]
                              ? <img className="chart-img" src={result.charts[c.var]} alt={c.label} />
                              : <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Select samples and run to render.</div>}
                          </div>
                        ))}
                    </div>
                  )}
                </>
              )}

              {t1Sub === "variable" && token && (
                <>
                  {[1, 2, 3].map((n) => {
                    const mainInputs = schema.inputs.filter((i) =>
                      [`variable_graph_${n}`, `variable_graph${n}_boreholes`].includes(i.name)
                    ).sort((a, b) => a.name.length - b.name.length);
                    const axisInputs = schema.inputs.filter((i) =>
                      [`variable_graph${n}_x_max`, `variable_graph${n}_y_max`].includes(i.name)
                    );
                    return (
                      <div className="card" key={`inputs-${n}`}>
                        <div className="card-head"><div className="card-title">Graph {n}</div></div>
                        <div style={{ padding: 24 }}>
                          <FormGrid inputs={mainInputs} params={params} options={options} setParam={setParam} />
                          {axisInputs.length > 0 && (
                            <div style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
                              {axisInputs.map((inp) => (
                                <div key={inp.name} style={{ flex: "0 0 130px" }}>
                                  <Field spec={inp} value={params[inp.name]} options={options} params={params}
                                    onChange={(v) => setParam(inp.name, v)} />
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                  <div className="chart-row" style={{ justifyContent: "flex-start" }}>
                    {[1, 2, 3].map((n) => (
                      <VariableGraphPanel key={n} n={n} result={result} />
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {/* ===== BG Chloride (sub-tabs: Data table + Charts) ===== */}
          {active === "bg_chloride" && (
            <div className="stack fade-in">
              {!token && <NeedFile />}
              <div className="subtabs">
                <button className={`subtab ${bgChlorideSub === "data" ? "active" : ""}`}
                  onClick={() => setBgChlorideSub("data")}>BG Chloride Data</button>
                <button className={`subtab ${bgChlorideSub === "charts" ? "active" : ""}`}
                  onClick={() => setBgChlorideSub("charts")}>BG Chloride Charts</button>
              </div>

              {bgChlorideSub === "data" && token && (
                <div className="card">
                  <div className="card-head">
                    <div className="card-title">Background Chloride</div>
                    <div className="card-meta">{result?.outputs["bg_chloride_df"]?.rows.length ?? 0} rows</div>
                  </div>
                  {result?.outputs["bg_chloride_df"]
                    ? <DataTable data={result.outputs["bg_chloride_df"]} />
                    : <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Run the analysis to populate.</div>}
                </div>
              )}

              {bgChlorideSub === "charts" && (
                <>
                  <div className="subtabs">
                    {[1, 2, 3].map((n) => (
                      <button key={n} className={`subtab ${bgChloridePlot === n ? "active" : ""}`}
                        onClick={() => setBgChloridePlot(n)}>
                        Plot {n}
                      </button>
                    ))}
                  </div>
                  <BgChloridePanel n={bgChloridePlot} schema={schema} params={params} options={options}
                    setParam={setParam} result={result} />
                </>
              )}
            </div>
          )}

          {/* ===== Texture (sub-tabs: depth tables + saturation profile) ===== */}
          {active === "texture" && (
            <div className="stack fade-in">
              {!token && <NeedFile />}
              <div className="subtabs">
                <button className={`subtab ${textureSub === "tables" ? "active" : ""}`}
                  onClick={() => setTextureSub("tables")}>Depth Tables</button>
                <button className={`subtab ${textureSub === "profile" ? "active" : ""}`}
                  onClick={() => setTextureSub("profile")}>Saturation Profile</button>
              </div>

              {textureSub === "tables" && (
                <>
                  {token && allOutputs.length > 1 && (
                    <div className="subtabs">
                      {allOutputs.map((o) => (
                        <button key={o.var} className={`subtab ${selectedOut?.var === o.var ? "active" : ""}`}
                          onClick={() => setOutVar(o.var)}>
                          {o.label}
                        </button>
                      ))}
                    </div>
                  )}
                  {token && shownOutputs.map((o) => (
                    <div className="card" key={o.var}>
                      <div className="card-head">
                        <div className="card-title">{o.label}</div>
                        <div className="card-meta">{result?.outputs[o.var]?.rows.length ?? 0} rows</div>
                      </div>
                      {result?.outputs[o.var]
                        ? <DataTable data={result.outputs[o.var]} />
                        : <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Run the analysis to populate.</div>}
                    </div>
                  ))}
                </>
              )}

              {textureSub === "profile" && token && (
                <div className="chart-row">
                  <div className="card chart-card">
                    <div className="card-head"><div className="card-title">Saturation Profile</div></div>
                    {result?.charts["saturation_profile"]
                      ? <img className="chart-img texture-chart-img" src={result.charts["saturation_profile"]} alt="Saturation Profile" />
                      : <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Select samples and run to render.</div>}
                  </div>
                  <div className="card chart-card">
                    <div className="card-head"><div className="card-title">Sand / Clay Scatter</div></div>
                    {result?.charts["sand_clay_scatter"]
                      ? <img className="chart-img texture-chart-img" src={result.charts["sand_clay_scatter"]} alt="Sand / Clay Scatter" />
                      : <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Run to render.</div>}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ===== SST Charts (sub-tabs: SST Chloride / SST Sodium / SST SAR) ===== */}
          {active === "sst_charts" && (
            <div className="stack fade-in">
              {!token && <NeedFile />}
              <div className="subtabs">
                <button className={`subtab ${sstChartsSub === "chloride" ? "active" : ""}`}
                  onClick={() => setSstChartsSub("chloride")}>SST Chloride</button>
                <button className={`subtab ${sstChartsSub === "sodium" ? "active" : ""}`}
                  onClick={() => setSstChartsSub("sodium")}>SST Sodium</button>
                <button className={`subtab ${sstChartsSub === "sar" ? "active" : ""}`}
                  onClick={() => setSstChartsSub("sar")}>SST SAR</button>
              </div>

              {sstChartsSub === "chloride" && (
                <>
                  {/* X Axis Max numeric input for the SST Chloride profile charts */}
                  {token && (
                    <div className="card">
                      <div className="card-head">
                        <div className="card-title">X Axis Max</div>
                        <div className="card-meta">Profile x-axis limit (optional)</div>
                      </div>
                      <div style={{ padding: 24 }}>
                        <FormGrid
                          inputs={schema.inputs.filter((i) => i.name === "sst_cl_x_axis_max")}
                          params={params} options={options} setParam={setParam} />
                      </div>
                    </div>
                  )}
                  {/* Additional Guidelines input table */}
                  {token && (
                    <div className="card">
                      <div className="card-head">
                        <div className="card-title">Additional Guidelines</div>
                        <div className="card-meta">Label · Depth Interval · Guideline</div>
                      </div>
                      <div style={{ padding: 24 }}>
                        <FormGrid
                          inputs={schema.inputs.filter((i) => i.name === "chloride_additional_guidelines")}
                          params={params} options={options} setParam={setParam} />
                      </div>
                    </div>
                  )}
                  {/* Chloride Plot Config input table (per-subarea excluded boreholes) */}
                  {token && (
                    <div className="card">
                      <div className="card-head">
                        <div className="card-title">Chloride Plot Config</div>
                        <div className="card-meta">Excluded Boreholes per Subarea</div>
                      </div>
                      <div style={{ padding: 24 }}>
                        <FormGrid
                          inputs={schema.inputs.filter((i) => i.name === "chloride_plot_config")}
                          params={params} options={options} setParam={setParam} />
                      </div>
                    </div>
                  )}
                  {/* SST Chloride profile charts (one per subarea) */}
                  {token && (
                    <div className="chart-row">
                      {Object.keys(result?.charts ?? {})
                        .filter((k) => k.startsWith("sst_cl_profile_chloride_"))
                        .map((key) => {
                          const subarea = key.replace("sst_cl_profile_chloride_", "").replace(/_/g, " ");
                          return (
                            <div className="card chart-card sst-cl-chart-card" key={key}>
                              <div className="card-head"><div className="card-title">SST Chloride — {subarea}</div></div>
                              {result?.charts[key]
                                ? <img className="chart-img sst-cl-chart-img" src={result.charts[key]} alt={`SST Chloride ${subarea}`} />
                                : <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Run to render.</div>}
                            </div>
                          );
                        })}
                      {Object.keys(result?.charts ?? {}).filter((k) => k.startsWith("sst_cl_profile_chloride_")).length === 0 && (
                        <div className="card">
                          <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>
                            Configure subareas and run to render the SST Chloride profiles.
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}

              {sstChartsSub === "sodium" && token && (
                <div className="card">
                  <div className="card-head"><div className="card-title">SST Sodium</div></div>
                  <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>
                    Coming soon.
                  </div>
                </div>
              )}

              {sstChartsSub === "sar" && token && (
                <div className="card">
                  <div className="card-head"><div className="card-title">SST SAR</div></div>
                  <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>
                    Coming soon.
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ===== 95th Percentile (subarea tabs, each with 4 table sub-tabs + chart) ===== */}
          {active === "95_percentile" && (
            <div className="stack fade-in">
              {!token && <NeedFile />}
              {tabInputs.length > 0 && (
                <div className="card">
                  <div className="card-head"><div className="card-title">{tab.title} inputs</div></div>
                  <div style={{ padding: 24 }}>
                    <FormGrid inputs={tabInputs} params={params} options={options} setParam={setParam} />
                  </div>
                </div>
              )}
              {token && (
                <P95Panel result={result} options={options} subarea={p95Subarea} setSubarea={setP95Subarea}
                  sub={p95Sub} setSub={setP95Sub} view={p95View} setView={setP95View} />
              )}
            </div>
          )}

          {/* ===== Generic output tabs (TDS Tables, Tier 1, Site Specific, Surfer) ===== */}
          {active !== "input_config" && active !== "tds_charts" && active !== "tier1_graphs" && active !== "bg_chloride" && active !== "texture" && active !== "95_percentile" && active !== "sst_charts" && (
            <div className="stack fade-in">
              {!token && <NeedFile />}
              {tabInputs.length > 0 && (
                <div className="card">
                  <div className="card-head"><div className="card-title">{tab.title} inputs</div></div>
                  <div style={{ padding: 24 }}>
                    <FormGrid inputs={tabInputs} params={params} options={options} setParam={setParam} />
                  </div>
                </div>
              )}
              {token && allOutputs.length > 1 && (
                <div className="subtabs">
                  {allOutputs.map((o) => (
                    <button key={o.var} className={`subtab ${selectedOut?.var === o.var ? "active" : ""}`}
                      onClick={() => setOutVar(o.var)}>
                      {o.label}
                    </button>
                  ))}
                </div>
              )}
              {token && shownOutputs.map((o) => (
                o.var === "depth_specific_tier1" ? (
                  <DepthSpecificTier1 result={result} key={o.var} />
                ) : (
                  <div className="card" key={o.var}>
                    <div className="card-head">
                      <div className="card-title">{o.label}</div>
                      <div className="card-meta">{result?.outputs[o.var]?.rows.length ?? 0} rows</div>
                    </div>
                    {result?.outputs[o.var]
                      ? <DataTable data={result.outputs[o.var]} />
                      : <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Run the analysis to populate.</div>}
                  </div>
                )
              ))}
              {token && tabCharts.length > 0 && (
                <div className="chart-row">
                  {tabCharts.map((c) => (
                    <div className="card chart-card" key={c.var}>
                      <div className="card-head"><div className="card-title">{c.label}</div></div>
                      {result?.charts[c.var]
                        ? <img className="chart-img" src={result.charts[c.var]} alt={c.label} />
                        : <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Select samples and run to render.</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

/* ---------- sub-components ---------- */

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

function GraphPanel({ n, schema, params, options, setParam, result }: {
  n: number; schema: Schema; params: Params; options: OptionMap;
  setParam: (name: string, v: unknown) => void; result: RunResult | null;
}) {
  const inputs = schema.inputs.filter((i) =>
    [`gw_graph_${n}`, `graph_${n}_wells`, `graph_${n}_reference`].includes(i.name)
  ).sort((a, b) => {
    const order = [`gw_graph_${n}`, `graph_${n}_reference`, `graph_${n}_wells`];
    return order.indexOf(a.name) - order.indexOf(b.name);
  });
  const chart = result?.charts[`plot${n}`];
  const table = result?.outputs[`mann_kendall_graph_${n}_df`];
  const param = params[`gw_graph_${n}`] as string | undefined;

  return (
    <div className="card">
      <div className="card-head">
        <div className="card-title">Graph {n}{param ? ` · ${param}` : ""}</div>
        <div className="card-meta">Mann-Kendall trend</div>
      </div>
      <div style={{ padding: 20, borderBottom: "1px solid var(--line-2)" }}>
        <FormGrid inputs={inputs} params={params} options={options} setParam={setParam} />
      </div>
      {chart
        ? <img className="chart-img" src={chart} alt={`Graph ${n}`} />
        : <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Run to render the chart.</div>}
      {table && table.rows.length > 0 && (
        <div style={{ borderTop: "1px solid var(--line-2)" }}>
          <div style={{ padding: "12px 20px 0" }} className="subhead">Statistics</div>
          <DataTable data={table} />
        </div>
      )}
    </div>
  );
}

function BgChloridePanel({ n, schema, params, options, setParam, result }: {
  n: number; schema: Schema; params: Params; options: OptionMap;
  setParam: (name: string, v: unknown) => void; result: RunResult | null;
}) {
  const order = [
    `plot${n}_x_axis_metric1`, `plot${n}_x_axis_metric2`, `plot${n}_x_operation`, `plot${n}_x_axis_max`,
    `plot${n}_y_axis_metric1`, `plot${n}_y_axis_metric2`, `plot${n}_y_operation`, `plot${n}_y_axis_max`,
  ];
  const inputs = schema.inputs.filter((i) => order.includes(i.name))
    .sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name));
  const chart = result?.charts[`bg_chloride_plot_${n}`];

  return (
    <div className="card">
      <div className="card-head"><div className="card-title">Plot {n}</div></div>
      <CollapsibleInputs title={`Plot ${n} Config`} inputs={inputs} params={params} options={options} setParam={setParam} />
      {chart
        ? <img className="chart-img" src={chart} alt={`Plot ${n}`} />
        : <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Run to render the chart.</div>}
    </div>
  );
}

function VariableGraphPanel({ n, result }: {
  n: number; result: RunResult | null;
}) {
  const chart = result?.charts[`tier1_variable_graph_${n}`];

  return (
    <div className="card chart-card" style={{ flex: "1 1 calc(33.333% - 16px)", maxWidth: "calc(33.333% - 16px)" }}>
      <div className="card-head">
        <div className="card-title">Parameter {n}</div>
      </div>
      {chart
        ? <img className="chart-img" src={chart} alt={`Parameter ${n}`} />
        : <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Choose a parameter and boreholes, then run.</div>}
    </div>
  );
}

const P95_SUBT: { key: string; label: string; prefix?: string }[] = [
  { key: "subsoil", label: "Subsoil Mass", prefix: "p95_subsoil_mass_" },
  { key: "vertical", label: "Vertical Mass", prefix: "p95_vertical_mass_" },
  { key: "stats", label: "1-1.5m Stats", prefix: "p95_stats_" },
  { key: "outliers", label: "Outliers", prefix: "p95_outliers_" },
  { key: "profile", label: "Chloride Profile" },
];

function P95Panel({ result, options, subarea, setSubarea, sub, setSub, view, setView }: {
  result: RunResult | null;
  options: OptionMap;
  subarea: string | null;
  setSubarea: (s: string | null) => void;
  sub: string;
  setSub: (s: string) => void;
  view: "data" | "subareas";
  setView: (v: "data" | "subareas") => void;
}) {
  const outputs = result?.outputs ?? {};
  const charts = result?.charts ?? {};

  // slug -> display name map provided by the backend (authoritative source of
  // the subarea list). Keys are the slugs used in the p95_ output keys.
  const subareaNames = (options["p95_subareas"] as unknown as Record<string, string> | undefined) ?? {};
  const subareas = Object.keys(subareaNames);
  const labelFor = (slug: string) => subareaNames[slug] ?? slug;

  const activeSubarea = subarea && subareas.includes(subarea) ? subarea : subareas[0];
  const activeSub = P95_SUBT.find((s) => s.key === sub) ?? P95_SUBT[0];

  const tableVar = activeSubarea ? `${activeSub.prefix}${activeSubarea}` : null;
  const chartVar = activeSubarea ? `p95_chloride_profile_${activeSubarea}` : null;
  const table = tableVar ? outputs[tableVar] : undefined;
  const chart = chartVar ? charts[chartVar] : undefined;
  const dataTable = outputs["percentile_95_subarea_data"];

  if (subareas.length === 0) {
    return (
      <div className="empty-state">
        <h3>No subarea results</h3>
        <p>Assign boreholes to subareas and run the analysis to populate results.</p>
      </div>
    );
  }

  return (
    <>
      {/* Top-level view tabs (mirrors Texture's Depth Tables / Saturation Profile). */}
      <div className="subtabs">
        <button className={`subtab ${view === "data" ? "active" : ""}`}
          onClick={() => setView("data")}>
          95th Percentile Data
        </button>
        <button className={`subtab ${view === "subareas" ? "active" : ""}`}
          onClick={() => setView("subareas")}>
          Subarea Data
        </button>
      </div>

      {view === "data" ? (
        <div className="card">
          <div className="card-head">
            <div className="card-title">95th Percentile Data</div>
            <div className="card-meta">{dataTable?.rows.length ?? 0} rows</div>
          </div>
          {dataTable ? <DataTable data={dataTable} /> : <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Run the analysis to populate.</div>}
        </div>
      ) : (
        <>
          {/* Subarea tabs */}
          <div className="subtabs">
            {subareas.map((s) => (
              <button key={s} className={`subtab ${activeSubarea === s ? "active" : ""}`}
                onClick={() => setSubarea(s)}>
                {labelFor(s)}
              </button>
            ))}
          </div>
          {/* Per-subarea sub-tabs (4 tables + chloride profile) */}
          <div className="subtabs">
            {P95_SUBT.map((s) => (
              <button key={s.key} className={`subtab ${activeSub.key === s.key ? "active" : ""}`}
                onClick={() => setSub(s.key)}>
                {s.label}
              </button>
            ))}
          </div>
          {activeSub.key === "profile" ? (
            <div className="card chart-card">
              <div className="card-head"><div className="card-title">Chloride Profile</div></div>
              {chart
                ? <img className="chart-img p95-chart-img" src={chart} alt="Chloride Profile" />
                : <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Run to render.</div>}
            </div>
          ) : (
            <div className="card">
              <div className="card-head">
                <div className="card-title">{activeSub.label}</div>
                <div className="card-meta">{table?.rows.length ?? 0} rows</div>
              </div>
              {table ? <DataTable data={table} /> : <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Run the analysis to populate.</div>}
            </div>
          )}
        </>
      )}
    </>
  );
}

function UploadZone({ token, filename, uploading, drag, setDrag, fileInput, doUpload }: any) {
  return (
    <div>
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
    </div>
  );
}

function AiSeam() {
  return (
    <div className="ai-card">
      <div className="ai-badge"><IcSpark className="" style={{ width: 20, height: 20 }} /></div>
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <h3>Configure with AI</h3><span className="soon-tag">Coming soon</span>
        </div>
        <p>Let an assistant ask a few questions about this site and set up wells, zones, and guideline references for you.</p>
        <button className="btn btn-ai" disabled><IcSpark className="" style={{ width: 15, height: 15 }} /> Set up with assistant</button>
      </div>
    </div>
  );
}

function NeedFile() {
  return (
    <div className="empty-state">
      <IcInbox className="es-ico" />
      <h3>No data loaded</h3>
      <p>Upload a Soil Analytical File on the <b>Input Configuration</b> tab to run this workflow.</p>
    </div>
  );
}
