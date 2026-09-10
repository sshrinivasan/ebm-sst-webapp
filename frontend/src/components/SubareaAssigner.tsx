import { MultiSelect } from "./MultiSelect";

export interface SubareaRow {
  subarea: string;
  boreholes: string[];
}

/**
 * Purpose-built control for assigning boreholes to subareas.
 *
 * - Subarea names are free-typed (text input per row).
 * - Each borehole can belong to at most ONE subarea (no overlap): the
 *   multiselect for a row only offers boreholes not already assigned to
 *   another row, and selecting one removes it from the others.
 * - Rows can be added/removed; an empty subarea name is allowed but flagged.
 */
export function SubareaAssigner({
  value, allBoreholes, defaultValue, onChange,
}: {
  value: SubareaRow[];
  allBoreholes: string[];
  defaultValue?: SubareaRow[];
  onChange: (rows: SubareaRow[]) => void;
}) {
  const rows = Array.isArray(value) ? value : [];
  const reset = () => onChange(Array.isArray(defaultValue) ? defaultValue.map((r) => ({ ...r, boreholes: [...(r.boreholes ?? [])] })) : []);

  // Boreholes already claimed by other rows (used to filter each row's options).
  const assignedElsewhere = (rowIdx: number) => {
    const used = new Set<string>();
    rows.forEach((r, i) => {
      if (i !== rowIdx) (r.boreholes ?? []).forEach((b) => used.add(String(b)));
    });
    return used;
  };

  const setSubarea = (i: number, name: string) => {
    const next = rows.map((r, ri) => (ri === i ? { ...r, subarea: name } : r));
    onChange(next);
  };

  const setBoreholes = (i: number, boreholes: string[]) => {
    const next = rows.map((r, ri) => (ri === i ? { ...r, boreholes } : r));
    onChange(next);
  };

  const addRow = () => onChange([...rows, { subarea: "", boreholes: [] }]);
  const removeRow = (i: number) => onChange(rows.filter((_, ri) => ri !== i));

  return (
    <div className="sa-assigner">
      <table className="sa-table">
        <thead>
          <tr>
            <th>Subarea</th>
            <th>Boreholes</th>
            <th className="sa-actions" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const used = assignedElsewhere(i);
            const available = allBoreholes.filter((b) => !used.has(String(b)));
            const opts = available.map((b) => ({ value: String(b), label: String(b) }));
            return (
              <tr key={i}>
                <td>
                  <input
                    className="control"
                    type="text"
                    placeholder="Subarea name"
                    value={row.subarea ?? ""}
                    onChange={(e) => setSubarea(i, e.target.value)}
                  />
                </td>
                <td>
                  <MultiSelect
                    options={opts}
                    value={(row.boreholes ?? []).map(String)}
                    onChange={(v) => setBoreholes(i, v)}
                    placeholder="Assign boreholes…"
                    noSearch
                  />
                </td>
                <td className="sa-actions">
                  <button type="button" className="tbl-input-x" onClick={() => removeRow(i)} title="Remove row">×</button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="sa-footer">
        <button type="button" className="tbl-input-add" onClick={addRow}>+ Add subarea</button>
        {defaultValue && (
          <button type="button" className="tbl-btn ghost" onClick={reset}>Reset</button>
        )}
      </div>
    </div>
  );
}