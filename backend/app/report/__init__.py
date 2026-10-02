"""AI report generation — webapp integration of the ebm-routine-report skill.

Submodules:
- session: per-session file storage + non-linear state machine
- llm: OpenRouter-backed, provider-agnostic LLM client
- extract: Step 1c site-facts extraction (one LLM call)
- generator: subprocess wrapper for generate_ebm_report.py
- intake: intake question definitions + applicability logic
- sections: per-section LLM authoring (Step 3)
- operations: operation JSON validation + apply_operations.py wrapper
- practitioner: Step 6 practitioner hand-off DOCX
- jobs: non-blocking background job runner
- pipeline: hands-off generation orchestrator
- router: FastAPI router exposing /api/report/*
"""
from __future__ import annotations