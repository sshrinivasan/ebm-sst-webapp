import type { Schema, RunResult, Params, OptionMap } from "./types";

export async function getSchema(sstFlag: boolean = true): Promise<Schema> {
  const r = await fetch(`/api/schema?sst_flag=${sstFlag}`);
  if (!r.ok) throw new Error("Failed to load schema");
  return r.json();
}

export async function uploadFile(
  file: File
): Promise<{ token: string; filename: string; options: OptionMap }> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch("/api/upload", { method: "POST", body: fd });
  if (!r.ok) throw new Error((await r.text()) || "Upload failed");
  return r.json();
}

export async function runWorkflow(token: string, params: Params): Promise<RunResult> {
  const r = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, params }),
  });
  if (!r.ok) throw new Error((await r.text()) || "Run failed");
  return r.json();
}

export async function exportWorkbook(token: string, params: Params): Promise<Blob> {
  const r = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, params }),
  });
  if (!r.ok) throw new Error((await r.text()) || "Export failed");
  return r.blob();
}

export async function exportCharts(
  token: string,
  params: Params
): Promise<{ blob: Blob; filename: string }> {
  const r = await fetch("/api/export-charts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, params }),
  });
  if (!r.ok) throw new Error((await r.text()) || "Charts export failed");
  // The server names the zip after the uploaded Excel file
  // (e.g. "output_20261022_123456_figures.zip") via Content-Disposition.
  const cd = r.headers.get("Content-Disposition") || "";
  const m = /filename="?([^";]+)"?/.exec(cd);
  const filename = m
    ? m[1]
    : `figures_${new Date().toISOString().replace(/[:.]/g, "-")}.zip`;
  return { blob: await r.blob(), filename };
}
