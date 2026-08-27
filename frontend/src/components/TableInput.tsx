import type { TableColumn } from "../types";

type Row = Record<string, unknown>;

export function TableInput({
  columns, value, onChange,
}: {
  columns: TableColumn[];
  value: Row[];
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
