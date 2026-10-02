"""Per-session file storage + non-linear state machine for report generation.

Mirrors the analysis app's ``_CONTEXT_CACHE`` pattern: an in-memory store keyed
by session id, with files persisted under a per-session directory on disk.

State machine (non-linear, with back-edges):

    files ⇄ extracting ⇄ facts_review → preparing → intake → generating → done

Back-transitions:
- a flag needing a missing file returns to ``files`` (re-extract after upload)
- changed intake answers return to ``preparing`` (re-run the background
  generator to recompute conditional questions)

Re-extraction can reuse cached facts for unchanged files (mirrors the skill's
Step 0 cache).
"""
from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

# Valid session states (non-linear; see module docstring).
State = Literal[
    "files", "extracting", "facts_review", "preparing", "intake",
    "generating", "done",
]

# File categories accepted by POST /api/report/start.
CATEGORIES = [
    "excel", "figures_zip", "abadata", "phaseview", "phase1_esa",
    "borehole_logs", "other_assessment", "sst_report",
]

# Categories whose documents are read by the LLM during extraction.
EXTRACT_CATEGORIES = [
    "abadata", "phaseview", "phase1_esa", "borehole_logs",
    "other_assessment", "sst_report",
]

# Category -> site_facts.json block key (see prompts/site_facts_cache.md).
CATEGORY_TO_FACTS_KEY = {
    "abadata": "abadata",
    "phaseview": "phaseview",
    "phase1_esa": "phase1_esa",
    "borehole_logs": "borehole_logs",
    "other_assessment": "other_previous_assessments",
    "sst_report": "sst_report",
}


class SessionError(ValueError):
    """Raised for invalid session operations; surfaced as HTTP 400/404."""


@dataclass
class ReportSession:
    """One report-generation session: files, extracted facts, and progress."""

    id: str
    dir: Path
    state: State = "files"
    files: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # category -> [{name, path, size}]
    site_facts: dict[str, Any] = field(default_factory=dict)
    extraction_flags: list[dict[str, Any]] = field(default_factory=list)
    excel_data: dict[str, Any] = field(default_factory=dict)
    intake_answers: dict[str, Any] = field(default_factory=dict)
    operations: list[dict[str, Any]] = field(default_factory=list)
    practitioner_info: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    # Paths produced by the pipeline (filled in as stages complete).
    partial_docx: str | None = None
    final_docx: str | None = None
    practitioner_docx: str | None = None
    excel_data_path: str | None = None
    site_facts_path: str | None = None

    # -- file helpers -----------------------------------------------------
    def add_file(self, category: str, name: str, path: Path) -> None:
        if category not in CATEGORIES:
            raise SessionError(f"Unknown category: {category}")
        self.files.setdefault(category, []).append(
            {"name": name, "path": str(path), "size": path.stat().st_size}
        )

    def file_paths(self, category: str) -> list[Path]:
        return [Path(f["path"]) for f in self.files.get(category, [])]

    def has_category(self, category: str) -> bool:
        return bool(self.files.get(category))

    def extract_sources(self) -> list[Path]:
        """Paths of all documents the LLM extraction pass should read."""
        paths: list[Path] = []
        for cat in EXTRACT_CATEGORIES:
            paths.extend(self.file_paths(cat))
        return paths

    def excel_path(self) -> Path | None:
        files = self.files.get("excel", [])
        return Path(files[0]["path"]) if files else None

    def figures_zip_path(self) -> Path | None:
        files = self.files.get("figures_zip", [])
        return Path(files[0]["path"]) if files else None

    # -- persistence ------------------------------------------------------
    def save_site_facts(self) -> Path:
        path = self.dir / "site_facts.json"
        path.write_text(
            json.dumps(self.site_facts, indent=2, default=str), encoding="utf-8"
        )
        self.site_facts_path = str(path)
        return path

    def save_excel_data(self, data: dict[str, Any]) -> Path:
        path = self.dir / "excel_data.json"
        path.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )
        self.excel_data = data
        self.excel_data_path = str(path)
        return path

    def save_operations(self) -> Path:
        path = self.dir / "operations.json"
        path.write_text(
            json.dumps(self.operations, indent=2, default=str), encoding="utf-8"
        )
        return path

    def save_practitioner_info(self) -> Path:
        path = self.dir / "practitioner_info.json"
        path.write_text(
            json.dumps(self.practitioner_info, indent=2, default=str),
            encoding="utf-8",
        )
        return path

    def to_public(self) -> dict[str, Any]:
        """JSON-safe view for the frontend (no absolute server paths)."""
        return {
            "id": self.id,
            "state": self.state,
            "files": {
                cat: [{"name": f["name"], "size": f["size"]} for f in files]
                for cat, files in self.files.items()
            },
            "site_facts": self.site_facts,
            "extraction_flags": self.extraction_flags,
            "intake_answers": self.intake_answers,
            "messages": self.messages,
            "created_at": self.created_at,
        }


class SessionStore:
    """In-memory session store with per-session dirs under a temp root."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(tempfile.gettempdir()) / "ebm_report_sessions"
        self.root.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, ReportSession] = {}

    def create(self) -> ReportSession:
        sid = uuid.uuid4().hex
        sdir = self.root / sid
        sdir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone

        session = ReportSession(
            id=sid,
            dir=sdir,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> ReportSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionError("Unknown or expired report session; please start a new one.")
        return session

    def delete(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is not None:
            shutil.rmtree(session.dir, ignore_errors=True)

    def set_state(self, session: ReportSession, state: State) -> None:
        session.state = state

    def clear(self) -> None:
        for sid in list(self._sessions):
            self.delete(sid)


# Module-level singleton (mirrors _CONTEXT_CACHE in main.py).
store = SessionStore()