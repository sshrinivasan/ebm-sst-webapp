import { useState } from "react";
import type { Schema, RunResult, Params, OptionMap, Notice, TableData, InputSpec } from "./types";
import { Field } from "./components/Field";
import { DataTable } from "./components/DataTable";
import { MarkdownNotes } from "./components/MarkdownNotes";
import {
  IcSliders, IcTable, IcChart, IcAlert, IcMap, IcRefresh, IcInbox, IcChevron,
} from "./components/icons";

const ICONS: Record<string, (p: { className?: string }) => JSX.Element> = {
  sliders: IcSliders, table: IcTable, chart: IcChart, alert: IcAlert, map: IcMap,
};

// Markdown notes shown below the "NPP Test Results" table (reusable via MarkdownNotes).
const NPP_TEST_RESULTS_NOTES = `* **Test A, Part 1**: Evaluates if there is a decrease in sulphate concentration from 1 mbgs to the surface.
* **Test A, Part 2 & 3**: Evaluates whether there is any increase in the sulphate trend within 0.3 m of the surface.
* **Test B**: Evaluates whether the depth of the sulphate maximum is greater than 1 mbgs
* **Test C**: Evaluates whether the concentration close to surface is less than the "baseline" sulphate concentration from deeper samples below the sulphate maximum.`;

// Checklist shown on the "NPP Practitioner Notes" tab (with the toggle below).
const NPP_PRACTITIONER_NOTES_MARKDOWN = `* There is a minimum of three soil profiles from background areas of the site. = Count Backgrounds (<3 results = Fail)
* All Background locations are in SIMILAR topographic positions. = Practitioner to check (unchecked = Incomplete)
* There is at least one Near-APEC profile for each source area. = Practitioner to check (unchecked = Incomplete)
* All Near-APEC locations are close to the APEC and in the SAME topographic position. = Practitioner to check (unchecked = Incomplete)
* All soil profiles are undisturbed with chloride concentrations within the background range. = Practitioner to check (unchecked = Incomplete)
* There are a sufficient number of samples per profile (8 from 0-4.5 m). Fewer samples can be justified. = Practitioner to check (unchecked = Incomplete)
* The water table depth and measurement type has been confirmed? = List the water table depth and measurement type i.e. 3.0 m (inferred) or 2.0 m (measured). (Less than 3 m inferred or 2 m measured = Fail)
* When all soil profiles are not definitely downwards, gleying, mottling, and soil moisture observations confirm that the inferred water table depth is 3 m or deeper at all site locations? = Practitioner to check
* When all soil profiles are not definitely downwards, groundwater measurements have been collected from at least 3 monitoring wells in similar topographic positions as the APEC, not all of which are upgradient, with at least one monitoring event from the spring, resulting in measured water table depths greater than 2 m at each well? = Practitioner to check
* This profile assessment is imperfect, and all soil profiles should be manually assessed. Potentially ambiguous profile types need to be manually designated as this evaluation cannot do that.`;

/**
 * Results viewer for the wizard's "Workflows" step.
 *
 * Uses a narrow left sidebar listing every workflow (scrollable when there are
 * many), so the full remaining width is available for tables and charts.
 */
export default function ResultsViewer({
  schema, result, options, params, setParam, running, onRun,
}: {
  schema: Schema;
  result: RunResult | null;
  options: OptionMap;
  params: Params;
  setParam: (name: string, v: unknown) => void;
  running: boolean;
  onRun: () => void;
}) {
  const [active, setActive] = useState("data");
  const [chartTab, setChartTab] = useState(1);
  const [bgChlorideTab, setBgChlorideTab] = useState(1);
  const [sstChartsSub, setSstChartsSub] = useState<"chloride" | "sodium" | "sar">("chloride");
  const [t1Sub, setT1Sub] = useState<"graphs" | "variable">("graphs");
  const [textureSub, setTextureSub] = useState<"tables" | "profile">("tables");
  const [nppSub, setNppSub] = useState<"tables" | "charts">("tables");
  const [nppTable, setNppTable] = useState<string>("npp_test_results");
  const [p95Subarea, setP95Subarea] = useState<string | null>(null);
  const [p95Sub, setP95Sub] = useState<string>("subsoil");
  const [p95View, setP95View] = useState<"data" | "subareas">("data");
  const [outVar, setOutVar] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

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

  // Flatten nav into a list of workflow tabs (skip input_config — handled by wizard).
  const workflowTabs = schema.nav.flatMap((node) => {
    if (node.id === "input_config") return [];
    if (!node.children) return [{ id: node.id!, title: node.title, icon: node.icon }];
    return node.children.map((c) => ({ id: c.id!, title: c.title, icon: node.icon }));
  });

  return (
    <div className="rv">
      {/* ---------- Narrow workflow sidebar ---------- */}
      <aside className="rv-sidebar">
        <div className="rv-nav-label">Workflows</div>
        <nav className="rv-nav">
          {workflowTabs.map((w) => {
            const Icon = ICONS[w.icon ?? "table"] ?? IcTable;
            const count = leafCount(w.id);
            return (
              <button key={w.id} className={`rv-nav-item ${active === w.id ? "active" : ""}`} onClick={() => setActive(w.id)}>
                <Icon className="rv-nav-ico" />
                <span className="rv-nav-title">{w.title}</span>
                {count > 0 && <span className="rv-nav-badge">{count}</span>}
              </button>
            );
          })}
        </nav>
      </aside>

      {/* ---------- Main ---------- */}
      <div className="rv-main">
        <div className="rv-topbar">
          <div>
            <div className="rv-crumb">Workflows{parent ? ` · ${parent.title}` : ""} · {tab.title}</div>
            <h1>{parent ? `${parent.title} — ${tab.title}` : tab.title}</h1>
          </div>
          <button className="btn btn-primary" disabled={running} onClick={onRun}>
            {running ? <><span className="spinner" style={{ borderTopColor: "#fff", borderColor: "rgba(255,255,255,0.4)" }} /> Running…</> : <><IcRefresh className="" style={{ width: 15, height: 15 }} /> Re-run analysis</>}
          </button>
        </div>

        <div className="rv-content">
          <Notices messages={result?.messages} />

          {/* ===== TDS Charts (in-page tab row, one graph at a time) ===== */}
          {active === "tds_charts" && (
            <div className="stack fade-in">
              {!result && <NeedFile />}
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
              {!result && <NeedFile />}
              <div className="subtabs">
                <button className={`subtab ${t1Sub === "graphs" ? "active" : ""}`}
                  onClick={() => setT1Sub("graphs")}>Tier 1 Graphs</button>
                <button className={`subtab ${t1Sub === "variable" ? "active" : ""}`}
                  onClick={() => setT1Sub("variable")}>Variable Graphs</button>
              </div>

              {t1Sub === "graphs" && (
                <>
                  {!result && <NeedFile />}
                  {result && (
                    <div className="card">
                      <div className="card-head"><div className="card-title">Tier 1 Graphs inputs</div></div>
                      <div style={{ padding: 24 }}>
                        <FormGrid inputs={schema.inputs.filter((i) => i.name === "tier1_graph_samples")}
                          params={params} options={options} setParam={setParam} />
                      </div>
                    </div>
                  )}
                  {result && (
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

              {t1Sub === "variable" && result && (
                <>
                  {[1, 2].map((n) => {
                    const inputs = schema.inputs.filter((i) =>
                      [`variable_graph_${n}`, `variable_graph${n}_boreholes`].includes(i.name)
                    ).sort((a, b) => a.name.length - b.name.length);
                    return (
                      <div className="card" key={`inputs-${n}`}>
                        <div className="card-head"><div className="card-title">Graph {n}</div></div>
                        <div style={{ padding: 24 }}>
                          <FormGrid inputs={inputs} params={params} options={options} setParam={setParam} />
                        </div>
                      </div>
                    );
                  })}
                  <div className="chart-row" style={{ justifyContent: "flex-start" }}>
                    {[1, 2].map((n) => (
                      <VariableGraphPanel key={n} n={n} result={result} />
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {/* ===== BG Chloride (sub-tabs: Plot 1/2/3, one at a time) ===== */}
          {active === "bg_chloride" && (
            <div className="stack fade-in">
              {!result && <NeedFile />}
              <div className="subtabs">
                {[1, 2, 3].map((n) => (
                  <button key={n} className={`subtab ${bgChlorideTab === n ? "active" : ""}`}
                    onClick={() => setBgChlorideTab(n)}>
                    Plot {n}
                  </button>
                ))}
              </div>
              <BgChloridePanel n={bgChlorideTab} schema={schema} params={params} options={options}
                setParam={setParam} result={result} />
            </div>
          )}

          {/* ===== Texture (sub-tabs: depth tables + saturation profile) ===== */}
          {active === "texture" && (
            <div className="stack fade-in">
              {!result && <NeedFile />}
              <div className="subtabs">
                <button className={`subtab ${textureSub === "tables" ? "active" : ""}`}
                  onClick={() => setTextureSub("tables")}>Depth Tables</button>
                <button className={`subtab ${textureSub === "profile" ? "active" : ""}`}
                  onClick={() => setTextureSub("profile")}>Saturation Profile</button>
              </div>

              {textureSub === "tables" && (
                <>
                  {result && allOutputs.length > 1 && (
                    <div className="subtabs">
                      {allOutputs.map((o) => (
                        <button key={o.var} className={`subtab ${selectedOut?.var === o.var ? "active" : ""}`}
                          onClick={() => setOutVar(o.var)}>
                          {o.label}
                        </button>
                      ))}
                    </div>
                  )}
                  {result && shownOutputs.map((o) => (
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

              {textureSub === "profile" && result && (
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

          {/* ===== 95th Percentile (subarea tabs, each with 4 table sub-tabs + chart) ===== */}
          {active === "95_percentile" && (
            <div className="stack fade-in">
              {!result && <NeedFile />}
              {tabInputs.filter((i) => i.name !== "npp_practitioner_notes").length > 0 && (
                <CollapsibleInputs title={`${tab.title} inputs`} inputs={tabInputs.filter((i) => i.name !== "npp_practitioner_notes")} params={params} options={options} setParam={setParam} />
              )}
              {result && (
                <P95Panel result={result} options={options} subarea={p95Subarea} setSubarea={setP95Subarea}
                  sub={p95Sub} setSub={setP95Sub} view={p95View} setView={setP95View} />
              )}
            </div>
          )}

          {/* ===== NPP (page subtabs: Tables | Charts, plus per-table subtabs) ===== */}
          {active === "npp" && (
            <div className="stack fade-in">
              {!result && <NeedFile />}
              {tabInputs.filter((i) => i.name !== "npp_practitioner_notes").length > 0 && (
                <CollapsibleInputs title={`${tab.title} inputs`} inputs={tabInputs.filter((i) => i.name !== "npp_practitioner_notes")} params={params} options={options} setParam={setParam} />
              )}
              {result && options["npp_suitable"] != null && (
                <div className={`npp-suitability npp-suitability-${String(options["npp_suitable"]).toLowerCase()}`}>
                  Site NPP Suitability: <b>{String(options["npp_suitable"])}</b>
                </div>
              )}
              {result && (
                <>
                  <div className="subtabs">
                    <button className={`subtab ${nppSub === "tables" ? "active" : ""}`}
                      onClick={() => setNppSub("tables")}>Tables</button>
                    <button className={`subtab ${nppSub === "charts" ? "active" : ""}`}
                      onClick={() => setNppSub("charts")}>Charts</button>
                  </div>

                  {nppSub === "tables" && (
                    <>
                      <div className="subtabs">
                        {["npp_test_results", "npp_numerical_ref_info", "npp_test_statistics", "npp_marginal_results", "npp_selected_data"].map((varName) => (
                          <button key={varName} className={`subtab ${nppTable === varName ? "active" : ""}`}
                            onClick={() => setNppTable(varName)}>
                            {schema.outputs.find((o) => o.var === varName)?.label ?? varName}
                          </button>
                        ))}
                      </div>
                      {(() => {
                        const out = schema.outputs.find((o) => o.var === nppTable);
                        const data = result.outputs[nppTable];
                        return (
                          <div className="card">
                            <div className="card-head">
                              <div className="card-title">{nppTable === "npp_test_results" ? "Sulphate Profile Interpretation" : (out?.label ?? nppTable)}</div>
                              <div className="card-meta">{data?.rows.length ?? 0} rows</div>
                            </div>
                            {data
                              ? <DataTable data={data} />
                              : <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Run the analysis to populate.</div>}
                            {nppTable === "npp_test_results" && (
                              <>
                                <MarkdownNotes markdown={NPP_TEST_RESULTS_NOTES} />
                                <div className="notes-header">Practitioner Notes</div>
                                <MarkdownNotes markdown={NPP_PRACTITIONER_NOTES_MARKDOWN} />
                                <div style={{ padding: "8px 20px 20px" }}>
                                  <FormGrid inputs={tabInputs.filter((i) => i.name === "npp_practitioner_notes")} params={params} options={options} setParam={setParam} />
                                </div>
                              </>
                            )}
                          </div>
                        );
                      })()}
                    </>
                  )}

                  {nppSub === "charts" && (
                    <div className="chart-row">
                      {schema.charts.filter((c) => c.tab === "npp").map((c) => (
                        <div className="card chart-card" key={c.var}>
                          <div className="card-head"><div className="card-title">{c.label}</div></div>
                          {result.charts[c.var]
                            ? <img className="chart-img npp-chart-img" src={result.charts[c.var]} alt={c.label} />
                            : <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Select samples and run to render.</div>}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* ===== SST Charts (sub-tabs: SST Chloride / SST Sodium / SST SAR) ===== */}
          {active === "sst_charts" && (
            <div className="stack fade-in">
              {!result && <NeedFile />}
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
                  {result && (
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
                  {result && (
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
                  {result && (
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
                  {result && (
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

              {sstChartsSub === "sodium" && result && (
                <div className="card">
                  <div className="card-head"><div className="card-title">SST Sodium</div></div>
                  <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>
                    Coming soon.
                  </div>
                </div>
              )}

              {sstChartsSub === "sar" && result && (
                <div className="card">
                  <div className="card-head"><div className="card-title">SST SAR</div></div>
                  <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>
                    Coming soon.
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ===== Generic output tabs (TDS Tables, Tier 1, Site Specific, Surfer) ===== */}
          {active !== "tds_charts" && active !== "tier1_graphs" && active !== "bg_chloride" && active !== "texture" && active !== "95_percentile" && active !== "npp" && active !== "sst_charts" && (
            <div className="stack fade-in">
              {!result && <NeedFile />}
              {tabInputs.length > 0 && (
                <CollapsibleInputs title={`${tab.title} inputs`} inputs={tabInputs} params={params} options={options} setParam={setParam} />
              )}
              {result && allOutputs.length > 1 && (
                <div className="subtabs">
                  {allOutputs.map((o) => (
                    <button key={o.var} className={`subtab ${selectedOut?.var === o.var ? "active" : ""}`}
                      onClick={() => setOutVar(o.var)}>
                      {o.label}
                    </button>
                  ))}
                </div>
              )}
              {result && shownOutputs.map((o) => (
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
              {result && tabCharts.length > 0 && (
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
      </div>
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

/**
 * Collapsible input card for a workflow's parameters. Collapsed by default so
 * the results (tables/charts) are immediately visible; expand to tweak inputs.
 */
function CollapsibleInputs({ title, inputs, params, options, setParam, children }: {
  title: string; inputs?: InputSpec[]; params: Params; options: OptionMap;
  setParam: (n: string, v: unknown) => void;
  children?: React.ReactNode;   // optional custom body (e.g. markdown notes)
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`card rv-inputs ${open ? "open" : ""}`}>
      <button className="rv-inputs-head" onClick={() => setOpen(!open)}>
        <span className="rv-inputs-title">{title}</span>
        <span className="rv-inputs-meta">
          {open ? "Hide" : "Show"} parameters
          <IcChevron className={`rv-inputs-chev ${open ? "open" : ""}`} />
        </span>
      </button>
      {open && (
        <div className="rv-inputs-body">
          {children}
          {inputs && inputs.length > 0 && (
            <FormGrid inputs={inputs} params={params} options={options} setParam={setParam} />
          )}
        </div>
      )}
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
  const table = result?.outputs[`bg_chloride_df`];

  return (
    <>
      <div className="card">
        <div className="card-head"><div className="card-title">Plot {n}</div></div>
        <div style={{ padding: 20, borderBottom: "1px solid var(--line-2)" }}>
          <FormGrid inputs={inputs} params={params} options={options} setParam={setParam} />
        </div>
        {chart
          ? <img className="chart-img" src={chart} alt={`Plot ${n}`} />
          : <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Run to render the chart.</div>}
      </div>
      {table && (
        <div className="card">
          <div className="card-head">
            <div className="card-title">Background Chloride</div>
            <div className="card-meta">{table.rows.length} rows</div>
          </div>
          <DataTable data={table} />
        </div>
      )}
    </>
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

function NeedFile() {
  return (
    <div className="empty-state">
      <IcInbox className="es-ico" />
      <h3>No data loaded</h3>
      <p>Upload a Soil Analytical File on the <b>Upload</b> step to run this workflow.</p>
    </div>
  );
}