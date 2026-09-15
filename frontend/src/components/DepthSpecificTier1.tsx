import type { RunResult } from "../types";
import { DataTable } from "./DataTable";

/**
 * "Depth Specific Tier 1 Exceedances" subtab on the Exceedances tab.
 *
 * Renders the three Tier 1 salinity summary tables (root zone / subsoil / all
 * depths) as stacked cards, each with its own heading. The tables are produced
 * by depth_specific_tier1_exceedances in the backend and serialized under the
 * tier1_*_param_summary output keys.
 */
const DEPTH_SPECIFIC_TIER1_TABLES: { key: string; title: string }[] = [
  { key: "tier1_shallow_param_summary", title: "Tier 1 Root Zone (0-1.5 m) Salinity Exceedances (mg/kg)" },
  { key: "tier1_deep_param_summary", title: "Tier 1 Subsoil (>1.5 m) Salinity Exceedances (mg/kg)" },
  { key: "tier1_all_param_summary", title: "Tier 1 Salinity Exceedances - ALL DEPTHS (mg/L)" },
];

export function DepthSpecificTier1({ result }: { result: RunResult | null }) {
  return (
    <>
      {DEPTH_SPECIFIC_TIER1_TABLES.map((t) => (
        <div className="card" key={t.key}>
          <div className="card-head">
            <div className="card-title">{t.title}</div>
            <div className="card-meta">{result?.outputs[t.key]?.rows.length ?? 0} rows</div>
          </div>
          {result?.outputs[t.key]
            ? <DataTable data={result.outputs[t.key]} />
            : <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Run the analysis to populate.</div>}
        </div>
      ))}
    </>
  );
}