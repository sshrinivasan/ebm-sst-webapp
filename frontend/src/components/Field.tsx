import type { InputSpec, OptionMap, TableData } from "../types";
import { MultiSelect } from "./MultiSelect";
import { TableInput } from "./TableInput";

function optionsFor(spec: InputSpec, options: OptionMap): { value: string; label: string }[] {
  if (spec.choices) return spec.choices.map((c) => ({ value: c, label: c }));
  if (spec.options && options[spec.options]) {
    const src = options[spec.options];
    if (Array.isArray(src)) return src.map((v) => ({ value: String(v), label: String(v) }));
    // df-backed options (e.g. surfer parameter): use value/display columns
    const td = src as TableData;
    const vcol = spec.value_column ?? td.columns[0];
    const dcol = spec.display_column ?? td.columns[td.columns.length - 1];
    return td.rows.map((r) => ({ value: String(r[vcol]), label: String(r[dcol] ?? r[vcol]) }));
  }
  return [];
}

export function Field({
  spec, value, options, onChange,
}: {
  spec: InputSpec;
  value: unknown;
  options: OptionMap;
  onChange: (v: unknown) => void;
}) {
  const opts = optionsFor(spec, options);
  const full = spec.full ?? (spec.control === "multiselect" || spec.control === "file" || spec.control === "table");

  let control: React.ReactNode;
  switch (spec.control) {
    case "table":
      control = (
        <TableInput columns={spec.columns ?? []} value={(value as Record<string, unknown>[]) ?? []} onChange={onChange} />
      );
      break;
    case "select":
      control = (
        <select className="control" value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value || null)}>
          <option value="">— choose —</option>
          {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
      break;
    case "multiselect":
      const isBorehole = spec.name?.includes("boreholes") || spec.name === "tier1_graph_samples";
      control = (
        <MultiSelect options={opts} value={(value as string[]) ?? []}
          onChange={onChange} placeholder="None selected"
          noSearch={isBorehole} />
      );
      break;
    case "toggle":
      control = (
        <div className="toggle" onClick={() => onChange(!value)}>
          <div className={`toggle-track ${value ? "on" : ""}`}><div className="toggle-knob" /></div>
          <span className="toggle-text">{value ? "Enabled" : "Disabled"}</span>
        </div>
      );
      break;
    case "number":
      control = (
        <input className="control" type="number" value={(value as number | string) ?? ""}
          placeholder={spec.example != null ? `e.g. ${spec.example}` : "0"}
          onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />
      );
      break;
    case "date":
      control = (
        <input className="control" type="date" value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value || null)} />
      );
      break;
    default:
      control = <input className="control" value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} />;
  }

  return (
    <div className={`field ${full ? "full" : ""}`}>
      <label>{spec.label}</label>
      {control}
    </div>
  );
}
