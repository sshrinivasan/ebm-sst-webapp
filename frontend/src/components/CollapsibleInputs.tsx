import { useState } from "react";
import type { InputSpec, Params, OptionMap } from "../types";
import { Field } from "./Field";
import { IcChevron, IcSliders } from "./icons";

export function FormGrid({ inputs, params, options, setParam, resetValues }: {
  inputs: InputSpec[]; params: Params; options: OptionMap; setParam: (n: string, v: unknown) => void;
  resetValues?: Record<string, unknown>;
}) {
  return (
    <div className="form-grid">
      {inputs.map((inp) => (
        <Field key={inp.name} spec={inp} value={params[inp.name]} options={options} params={params}
          resetValue={resetValues?.[inp.name]}
          onChange={(v) => setParam(inp.name, v)} />
      ))}
    </div>
  );
}

/**
 * Collapsible input card for a workflow's parameters. Collapsed by default so
 * the results (tables/charts) are immediately visible; expand to tweak inputs.
 * Styled as an accordion panel (see .rv-inputs in wizard.css).
 */
export function CollapsibleInputs({ title, inputs, params, options, setParam, resetValues, children, defaultOpen = false }: {
  title: string; inputs?: InputSpec[]; params: Params; options: OptionMap;
  setParam: (n: string, v: unknown) => void;
  resetValues?: Record<string, unknown>;
  children?: React.ReactNode;   // optional custom body (e.g. markdown notes)
  defaultOpen?: boolean;        // start expanded (e.g. when there's no default result)
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`card rv-inputs ${open ? "open" : ""}`}>
      <button className="rv-inputs-head" onClick={() => setOpen(!open)}>
        <span className="rv-inputs-title">
          <IcSliders className="rv-inputs-ico" />
          {title}
        </span>
        <span className="rv-inputs-meta">
          <span className="rv-inputs-badge">{open ? "Hide" : "Show"} parameters</span>
          <IcChevron className={`rv-inputs-chev ${open ? "open" : ""}`} />
        </span>
      </button>
      {open && (
        <div className="rv-inputs-body">
          {children}
          {inputs && inputs.length > 0 && (
            <FormGrid inputs={inputs} params={params} options={options} setParam={setParam} resetValues={resetValues} />
          )}
        </div>
      )}
    </div>
  );
}