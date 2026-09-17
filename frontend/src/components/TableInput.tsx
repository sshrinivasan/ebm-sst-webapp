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
  columns, value, options, params, onChange, minRows = 0,
}: {
  columns: TableColumn[];
  value: Row[];
  options?: OptionMap;
  params?: Params;
  onChange: (rows: Row[]) => void;
  minRows?: number;   // minimum visible rows; empty rows make the table obviously editable
}) {
  const rows = Array.isArray(value) ? value : [];
  // Pad with empty rows up to minRows so an empty table still shows a row.
  const visibleRows = rows.length >= minRows
    ? rows
    : [
        ...rows,
        ...Array.from({ length: minRows - rows.length }, () =>
          Object.fromEntries(columns.map((c) => [c.key, ""]))),
      ];

  const setCell = (i: number, key: string, v: unknown) => {
    const next = [...rows];
    while (next.length <= i) {
      next.push(Object.fromEntries(columns.map((c) => [c.key, ""])));
    }
    next[i] = { ...next[i], [key]: v };
    onChange(next);
  };
  const addRow = () => onChange([...rows, Object.fromEntries(columns.map((c) => [c.key, ""]))]);
  const removeRow = (i: number) => {
    if (i >= rows.length) return; // placeholder row: nothing to remove
    onChange(rows.filter((_, ri) => ri !== i));
  };

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
          {visibleRows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.key}>
                  {c.control === "select" ? (
                    (() => {
                      // Static choices, or a file-derived option list (e.g. the
                      // Chloride Plot Config Subarea column -> sst_subareas).
                      const opts = c.choices
                        ? c.choices.map((o) => ({ value: o, label: o }))
                        : optionsFor(c, row, options ?? {}, params ?? {});
                      return (
                        <select value={String(row[c.key] ?? "")} onChange={(e) => setCell(i, c.key, e.target.value)}>
                          <option value="">—</option>
                          {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                      );
                    })()
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
