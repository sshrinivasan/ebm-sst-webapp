import { useMemo, useState } from "react";
import type { TableData } from "../types";

const isNum = (v: unknown) => typeof v === "number" && !Number.isNaN(v);
const isEmpty = (v: unknown) => v === null || v === undefined || v === "";

function fmt(v: unknown): string {
  if (isEmpty(v)) return "—";
  if (typeof v === "number") {
    return Number.isInteger(v) ? v.toLocaleString()
      : v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return String(v);
}

export function DataTable({ data }: { data: TableData }) {
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState<Record<string, string>>({});

  // Detect numeric columns from a sample -> drives alignment + sort comparison.
  const numericCols = useMemo(() => {
    const set = new Set<string>();
    for (const c of data.columns) {
      const sample = data.rows.slice(0, 30).map((r) => r[c]).filter((v) => !isEmpty(v));
      if (sample.length && sample.every(isNum)) set.add(c);
    }
    return set;
  }, [data]);

  const view = useMemo(() => {
    let rows = data.rows;
    const active = Object.entries(filters).filter(([, q]) => q.trim() !== "");
    if (active.length) {
      rows = rows.filter((r) =>
        active.every(([c, q]) => fmt(r[c]).toLowerCase().includes(q.toLowerCase()))
      );
    }
    if (sortCol) {
      const num = numericCols.has(sortCol);
      rows = [...rows].sort((a, b) => {
        const av = a[sortCol], bv = b[sortCol];
        if (isEmpty(av) && isEmpty(bv)) return 0;
        if (isEmpty(av)) return 1;
        if (isEmpty(bv)) return -1;
        const cmp = num ? (av as number) - (bv as number)
          : String(av).localeCompare(String(bv), undefined, { numeric: true });
        return sortDir === "asc" ? cmp : -cmp;
      });
    }
    return rows;
  }, [data, filters, sortCol, sortDir, numericCols]);

  const onSort = (c: string) => {
    if (sortCol === c) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortCol(c); setSortDir("asc"); }
  };

  if (!data || data.rows.length === 0) {
    return (
      <div className="table-empty">No rows for the current inputs.</div>
    );
  }

  const anyFilter = Object.values(filters).some((v) => v.trim() !== "");
  return (
    <div>
      <div className="table-toolbar">
        <button className={`tbl-btn ${showFilters ? "on" : ""}`} onClick={() => setShowFilters((s) => !s)}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" /></svg>
          Filter
        </button>
        {(anyFilter || sortCol) && (
          <button className="tbl-btn ghost" onClick={() => { setFilters({}); setSortCol(null); }}>Reset</button>
        )}
        <span className="tbl-count">{view.length}{view.length !== data.rows.length ? ` of ${data.rows.length}` : ""} rows</span>
      </div>
      <div className="table-scroll">
        <table className="data">
          <thead>
            <tr>
              {data.columns.map((c) => {
                const num = numericCols.has(c);
                const sorted = sortCol === c;
                return (
                  <th key={c} className={num ? "num" : ""} onClick={() => onSort(c)}>
                    <span className="th-inner">
                      {c}
                      <span className={`sort-ind ${sorted ? "active" : ""}`}>
                        {sorted ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                    </span>
                  </th>
                );
              })}
            </tr>
            {showFilters && (
              <tr className="filter-row">
                {data.columns.map((c) => (
                  <th key={c}>
                    <input value={filters[c] ?? ""} placeholder="Filter…"
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => setFilters((f) => ({ ...f, [c]: e.target.value }))} />
                  </th>
                ))}
              </tr>
            )}
          </thead>
          <tbody>
            {view.map((row, i) => (
              <tr key={i}>
                {data.columns.map((c) => {
                  const v = row[c];
                  const num = numericCols.has(c);
                  return (
                    <td key={c} className={`${num ? "num" : ""} ${isEmpty(v) ? "cell-empty" : ""}`}>
                      {fmt(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
