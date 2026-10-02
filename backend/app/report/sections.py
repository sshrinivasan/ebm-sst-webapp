"""Step 3 — per-section LLM authoring.

Iterates the Step 3 section table (SKILL.md), one API call per prompt file:
system = the section's prompt file (a Claude-authoring guide), user = the
relevant context (site_facts.json + excel_data.json + intake answers), and
the response is a single operation object (``replace_between`` for every
Claude-authored section). Operations are collected into the session's
``operations`` list and persisted to ``operations.json``.

Sections whose content is fully Python-authored (2.x, 3.2, 5.3 figures,
5.4, 7.1, 7.2) are not in this table — the generator handles them.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .llm import LLMClient, model_for
from .session import ReportSession

_SKILL_ROOT = Path(__file__).resolve().parents[2] / "report_skill"
_PROMPTS = _SKILL_ROOT / "prompts"

# (section, prompt file, start marker, end marker) — from SKILL.md Step 3.
SECTION_PROMPTS: list[tuple[str, str, str, str]] = [
    ("1 Introduction", "s1_introduction.md", "<INSERT_1_START>", "<INSERT_1_END>"),
    ("1.1 Objectives and Scope", "s1_1_objectives_scope.md", "<INSERT_1_1_START>", "<INSERT_1_1_END>"),
    ("Executive Summary", "exec_summary.md", "<INSERT_EXEC_SUMMARY_START>", "<INSERT_EXEC_SUMMARY_END>"),
    ("4.2 DWDA", "s4_2_dwda.md", "<INSERT_42_DWDA_START>", "<INSERT_42_DWDA_END>"),
    ("4.2 DWDA-NIL", "s4_2_dwda_nil.md", "<INSERT_42_DWDA_NIL_START>", "<INSERT_42_DWDA_NIL_END>"),
    ("4.2.2 APECs", "s4_2_2_apecs.md", "<INSERT_42_APECS_START>", "<INSERT_42_APECS_END>"),
    ("4.3 Chloride Delineation", "s4_3_chloride.md", "<INSERT_43_START>", "<INSERT_43_END>"),
    ("5 Background Chloride Intro", "s5_intro.md", "<INSERT_5_INTRO_START>", "<INSERT_5_INTRO_END>"),
    ("5.1 Phase 1 ESA Review", "s5_1_phase1.md", "<INSERT_5_1_START>", "<INSERT_5_1_END>"),
    ("5.2 Contaminant Transport", "s5_2_transport.md", "<INSERT_5_2_START>", "<INSERT_5_2_END>"),
    ("5.3 Chemistry Footprint", "s5_3_footprint.md", "<INSERT_5_3_START>", "<INSERT_5_3_END>"),
    ("8 Summary and Conclusions", "s8_summary.md", "<INSERT_8_START>", "<INSERT_8_END>"),
]


def _prompt_text(prompt_file: str) -> str:
    path = _PROMPTS / prompt_file
    if not path.exists():
        raise FileNotFoundError(f"Missing section prompt: {path}")
    return path.read_text(encoding="utf-8")


def _context_payload(session: ReportSession) -> str:
    """Compact JSON context for the authoring call (facts + data + answers)."""
    payload: dict[str, Any] = {
        "site_facts": session.site_facts,
        "excel_data": session.excel_data,
        "intake_answers": session.intake_answers,
    }
    return json.dumps(payload, indent=2, default=str)


def _user_prompt(section: str, context: str) -> str:
    return (
        f"Author the content for section '{section}' following the system "
        "prompt (the section's authoring guide) exactly.\n\n"
        "Return a single JSON object: the operation object for this section, "
        "with the exact shape the guide specifies (typically "
        '{"op": "replace_between", "start_text": ..., "end_text": ..., '
        '"blocks": [...]}). Do not return an array — one operation object '
        "only. Do not include any text outside the JSON.\n\n"
        "CONTEXT (site_facts.json, excel_data.json, intake answers):\n\n"
        f"{context}"
    )


def author_sections(
    session: ReportSession,
    llm: LLMClient,
    *,
    model: str | None = None,
    progress: Any = None,
) -> list[dict[str, Any]]:
    """Author every Step 3 section; returns the collected operations list.

    ``progress`` is an optional callable ``(stage_message: str) -> None``
    used by the background job to report per-section progress.
    """
    context = _context_payload(session)
    operations: list[dict[str, Any]] = []

    for section, prompt_file, start_marker, end_marker in SECTION_PROMPTS:
        if progress:
            progress(f"Authoring {section}…")
        system = _prompt_text(prompt_file)
        user = _user_prompt(section, context)
        op = llm.complete_json(
            system,
            user,
            model=model or model_for("author"),
            max_tokens=16_000,
        )
        # Normalise: the guide may return the op with or without markers.
        op.setdefault("start_text", start_marker)
        op.setdefault("end_text", end_marker)
        op.setdefault("op", "replace_between")
        operations.append(op)

    session.operations = operations
    session.save_operations()
    return operations