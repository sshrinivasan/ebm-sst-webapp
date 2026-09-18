import { useState } from "react";
import type { Schema, RunResult, Params, OptionMap } from "../types";
import { Field } from "./Field";
import { IcChevron } from "./icons";

/**
 * Shared frontend component for every vertical-profile chart produced by the
 * backend's `plot_profile` helper. Renders one chart image (510px) with a thin,
 * collapsible "Plot config" bar above it containing ONLY the per-chart X/Y axis
 * max controls — identical across all plots. Chart-specific inputs (e.g. sample
 * selectors) belong in a separate Inputs collapsible, not here.
 *
 * Edit this component to change how ALL profile charts look/behave.
 */
export function ProfileChartPanel({ chartKey, title, xMaxParam, yMaxParam, schema, params, options, setParam, result, showConfig = true, cardClassName }: {
  chartKey: string;
  title: string;
  xMaxParam?: string;
  yMaxParam?: string;
  schema: Schema;
  params: Params;
  options: OptionMap;
  setParam: (name: string, v: unknown) => void;
  result: RunResult | null;
  /** Set false to render just the chart (no config bar). */
  showConfig?: boolean;
  /** Extra class(es) for the card (e.g. a fixed-width grid class). */
  cardClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const xMax = xMaxParam ? schema.inputs.find((i) => i.name === xMaxParam) : undefined;
  const yMax = yMaxParam ? schema.inputs.find((i) => i.name === yMaxParam) : undefined;
  const chart = result?.charts[chartKey];
  const hasConfig = showConfig && (xMax || yMax);

  return (
    <div className={`card chart-card${cardClassName ? ` ${cardClassName}` : ""}`}>
      <div className="card-head"><div className="card-title">{title}</div></div>
      {hasConfig && (
        <div className="profile-chart-config">
          <button className="profile-chart-config-toggle" onClick={() => setOpen(!open)}>
            <span>Plot config</span>
            <IcChevron className={`profile-chart-config-chev ${open ? "open" : ""}`} />
          </button>
          {open && (
            <div className="profile-chart-controls">
              <div className="profile-chart-axis">
                {xMax && (
                  <Field spec={xMax} value={params[xMax.name]} options={options} params={params}
                    onChange={(v) => setParam(xMax.name, v)} />
                )}
                {yMax && (
                  <Field spec={yMax} value={params[yMax.name]} options={options} params={params}
                    onChange={(v) => setParam(yMax.name, v)} />
                )}
              </div>
            </div>
          )}
        </div>
      )}
      {chart
        ? <img className="chart-img profile-chart-img" src={chart} alt={title} />
        : <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 13.5 }}>Run to render the chart.</div>}
    </div>
  );
}
