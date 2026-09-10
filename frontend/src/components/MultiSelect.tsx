import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
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
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const triggerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (triggerRef.current && !triggerRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const toggleOpen = () => {
    const next = !open;
    if (next && triggerRef.current) {
      const r = triggerRef.current.getBoundingClientRect();
      setPos({ top: r.bottom + 6, left: r.left, width: r.width });
    }
    setOpen(next);
  };

  const toggle = (v: string) =>
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);

  const filtered = options.filter((o) =>
    o.label.toLowerCase().includes(q.toLowerCase())
  );
  const labelFor = (v: string) => options.find((o) => o.value === v)?.label ?? v;

  // Portal the popup to document.body so it escapes any scroll/clip container
  // (e.g. the collapsible .rv-inputs-body in the wizard). Anchored to the
  // trigger's viewport rect; re-measured on open.
  const portal = open && pos
    ? createPortal(
        <div className="ms-pop ms-pop-portal"
          style={{ top: pos.top, left: pos.left, width: pos.width }}
          onMouseDown={(e) => e.stopPropagation()}>
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
        </div>,
        document.body
      )
    : null;

  return (
    <>
      <div className={`ms ${open ? "open" : ""}`} ref={triggerRef}>
        <div className="ms-trigger" onClick={toggleOpen}>
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
      </div>
      {portal}
    </>
  );
}
