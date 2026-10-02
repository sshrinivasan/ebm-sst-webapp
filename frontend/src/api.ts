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

export async function exportCharts(token: string, params: Params): Promise<Blob> {
  const r = await fetch("/api/export-charts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, params }),
  });
  if (!r.ok) throw new Error((await r.text()) || "Charts export failed");
  return r.blob();
}

// ---------------------------------------------------------------------------
// AI report generation (/api/report/*)
// ---------------------------------------------------------------------------

export interface ReportFileEntry {
  name: string;
  size: number;
}

export interface ReportSession {
  id: string;
  state: string;
  files: Record<string, ReportFileEntry[]>;
  site_facts: Record<string, unknown>;
  extraction_flags: { message?: string; field?: string; ambiguous?: boolean }[];
  intake_answers: Record<string, unknown>;
  messages: unknown[];
  created_at: string;
}

export interface IntakeQuestion {
  id: string;
  title: string;
  prompt: string;
  type: "radio" | "text" | "textarea";
  options?: string[];
  always?: boolean;
}

export interface IntakeData {
  questions: IntakeQuestion[];
  auto_derived: { id: string; title: string; value: unknown }[];
  answers: Record<string, unknown>;
}

export interface JobStatus {
  id: string;
  status: "pending" | "running" | "done" | "error";
  stages: { message: string; status: string }[];
  error?: string | null;
  created_at: string;
}

export const REPORT_CATEGORIES = [
  "excel", "figures_zip", "abadata", "phaseview", "phase1_esa",
  "borehole_logs", "other_assessment", "sst_report",
] as const;

export type ReportCategory = (typeof REPORT_CATEGORIES)[number];

export async function reportStart(
  files: File[],
  categories: string[],
  reuseToken?: string
): Promise<ReportSession> {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  categories.forEach((c) => fd.append("categories", c));
  if (reuseToken) fd.append("reuse_analysis_token", reuseToken);
  const r = await fetch("/api/report/start", { method: "POST", body: fd });
  if (!r.ok) throw new Error((await r.text()) || "Report start failed");
  return r.json();
}

export async function reportExtract(sessionId: string): Promise<{ job_id: string; session: ReportSession }> {
  const r = await fetch(`/api/report/extract?session_id=${sessionId}`, { method: "POST" });
  if (!r.ok) throw new Error((await r.text()) || "Extraction start failed");
  return r.json();
}

export async function reportConfirmExtract(
  sessionId: string,
  siteFacts: Record<string, unknown>,
  extractionFlags: { message?: string; field?: string; ambiguous?: boolean }[]
): Promise<ReportSession> {
  const r = await fetch(`/api/report/extract/confirm?session_id=${sessionId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ site_facts: siteFacts, extraction_flags: extractionFlags }),
  });
  if (!r.ok) throw new Error((await r.text()) || "Extraction confirm failed");
  return r.json();
}

export async function reportPrepare(sessionId: string): Promise<{ job_id: string; session: ReportSession }> {
  const r = await fetch(`/api/report/prepare?session_id=${sessionId}`, { method: "POST" });
  if (!r.ok) throw new Error((await r.text()) || "Prepare failed");
  return r.json();
}

export async function reportGetIntake(sessionId: string): Promise<IntakeData> {
  const r = await fetch(`/api/report/intake?session_id=${sessionId}`);
  if (!r.ok) throw new Error((await r.text()) || "Intake load failed");
  return r.json();
}

export async function reportSubmitIntake(
  sessionId: string,
  answers: Record<string, unknown>
): Promise<ReportSession> {
  const r = await fetch(`/api/report/intake?session_id=${sessionId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers }),
  });
  if (!r.ok) throw new Error((await r.text()) || "Intake submit failed");
  return r.json();
}

export async function reportGenerate(sessionId: string): Promise<{ job_id: string; session: ReportSession }> {
  const r = await fetch(`/api/report/generate?session_id=${sessionId}`, { method: "POST" });
  if (!r.ok) throw new Error((await r.text()) || "Generate failed");
  return r.json();
}

export async function reportStatus(jobId: string): Promise<JobStatus> {
  const r = await fetch(`/api/report/status/${jobId}`);
  if (!r.ok) throw new Error((await r.text()) || "Status failed");
  return r.json();
}

export async function reportDownload(sessionId: string, kind: "report" | "practitioner" = "report"): Promise<Blob> {
  const r = await fetch(`/api/report/download/${sessionId}?kind=${kind}`);
  if (!r.ok) throw new Error((await r.text()) || "Download failed");
  return r.blob();
}

export async function reportSession(sessionId: string): Promise<ReportSession> {
  const r = await fetch(`/api/report/session/${sessionId}`);
  if (!r.ok) throw new Error((await r.text()) || "Session load failed");
  return r.json();
}
