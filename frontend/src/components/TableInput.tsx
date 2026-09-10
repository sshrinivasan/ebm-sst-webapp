import type { Params, TableColumn, OptionMap } from "../types";
import { MultiSelect } from "./MultiSelect";

type Row = Record<string, unknown>;

function optionsFor(
  col: TableColumn,
  row: Row,
  options: OptionMap,
  params: Params,
): { value: string; label: string }[] {
  // Per-row option list: options is an object keyed by a row field's value
  // (e.g. sst_subarea_boreholes[subarea] -> borehole ids).
  if (col.options_by_row) {
    const key = String(row[col.options_by_row] ?? "");
    const map = options[col.options ?? ""] as unknown as Record<string, string[]> | undefined;
    const vals = map?.[key];
    if (Array.isArray(vals)) return vals.map((v) => ({ value: String(v), label: String(v) }));
    return [];
  }
  // Options sourced from another param's rows (e.g. the Additional Guidelines
  // table's "Label" column). options_param names the source table param; the
  // label column of that table is always "Label".
  if (col.options_param) {
    const src = params[col.options_param];
    if (Array.isArray(src)) {
      const labels = src
        .map((r) => String((r as Row)["Label"] ?? "").trim())
        .filter(Boolean);
      return [...new Set(labels)].map((l) => ({ value: l, label: l }));
    }
    return [];
  }
  if (col.choices) return col.choices.map((c) => ({ value: c, label: c }));
  if (col.options && options[col.options]) {
    const src = options[col.options];
    if (Array.isArray(src)) return src.map((v) => ({ value: String(v), label: String(v) }));
    const td = src as { columns: string[]; rows: Record<string, unknown>[] };
    const vcol = td.columns[0];
    const dcol = td.columns[td.columns.length - 1];
    return td.rows.map((r) => ({ value: String(r[vcol]), label: String(r[dcol] ?? r[vcol]) }));
  }
  return [];
}

export function TableInput({
  columns, value, options, params, onChange,
}: {
  columns: TableColumn[];
  value: Row[];
  options?: OptionMap;
  params?: Params;
  onChange: (rows: Row[]) => void;
}) {
  const rows = Array.isArray(value) ? value : [];

  const setCell = (i: number, key: string, v: unknown) => {
    const next = rows.map((r, ri) => (ri === i ? { ...r, [key]: v } : r));
    onChange(next);
  };
  const addRow = () => onChange([...rows, Object.fromEntries(columns.map((c) => [c.key, ""]))]);
  const removeRow = (i: number) => onChange(rows.filter((_, ri) => ri !== i));

  return (
    <div className="tbl-input">
      <table>
        <thead>
          <tr>
            {columns.map((c) => <th key={c.key}>{c.label}</th>)}
            <th className="tbl-input-actions" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.key}>
                  {c.control === "select" ? (
                    <select value={String(row[c.key] ?? "")} onChange={(e) => setCell(i, c.key, e.target.value)}>
                      <option value="">—</option>
                      {(c.choices ?? []).map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                    </select>
                  ) : c.control === "multiselect" ? (
                    <MultiSelect
                      options={optionsFor(c, row, options ?? {}, params ?? {})}
                      value={Array.isArray(row[c.key]) ? (row[c.key] as string[]) : []}
                      onChange={(v) => setCell(i, c.key, v)}
                      placeholder="None"
                    />
                  ) : (
                    <input
                      type={c.control === "number" ? "number" : "text"}
                      value={String(row[c.key] ?? "")}
                      onChange={(e) => setCell(i, c.key, e.target.value)}
                    />
                  )}
                </td>
              ))}
              <td className="tbl-input-actions">
                <button type="button" className="tbl-input-x" onClick={() => removeRow(i)} title="Remove row">×</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button type="button" className="tbl-input-add" onClick={addRow}>+ Add row</button>
    </div>
  );
}
