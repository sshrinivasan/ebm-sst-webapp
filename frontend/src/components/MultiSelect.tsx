import { useEffect, useRef, useState } from "react";
import { IcCheck } from "./icons";

interface Opt { value: string; label: string }

export function MultiSelect({
  options, value, onChange, placeholder = "Select…", noSearch = false,
}: {
  options: Opt[];
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  noSearch?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const toggle = (v: string) =>
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);

  const filtered = options.filter((o) =>
    o.label.toLowerCase().includes(q.toLowerCase())
  );
  const labelFor = (v: string) => options.find((o) => o.value === v)?.label ?? v;

  return (
    <div className={`ms ${open ? "open" : ""}`} ref={ref}>
      <div className="ms-trigger" onClick={() => setOpen((o) => !o)}>
        {value.length === 0 && <span className="ms-placeholder">{placeholder}</span>}
        {value.map((v) => (
          <span className="ms-chip" key={v}>
            <b>{labelFor(v)}</b>
            <span className="x" onClick={(e) => { e.stopPropagation(); toggle(v); }}>×</span>
          </span>
        ))}
        <span className="ms-caret">
          <svg width="12" height="12" viewBox="0 0 12 12"><path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" /></svg>
        </span>
      </div>
      {open && (
        <div className="ms-pop">
          {!noSearch && <input className="ms-search" placeholder="Search…" value={q}
            onChange={(e) => setQ(e.target.value)} autoFocus />}
          <div className="ms-actions">
            <button onClick={() => onChange(options.map((o) => o.value))}>Select all</button>
            <button onClick={() => onChange([])}>Clear</button>
            <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)" }}>
              {value.length} selected
            </span>
          </div>
          <div className="ms-list">
            {filtered.length === 0 && <div className="ms-empty">No matches</div>}
            {filtered.map((o) => {
              const sel = value.includes(o.value);
              return (
                <div key={o.value} className={`ms-opt ${sel ? "sel" : ""}`} onClick={() => toggle(o.value)}>
                  <span className="ms-check">{sel && <IcCheck className="" />}</span>
                  {o.label}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
