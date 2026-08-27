import type { Schema, RunResult, Params, OptionMap } from "./types";

export async function getSchema(): Promise<Schema> {
  const r = await fetch("/api/schema");
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
