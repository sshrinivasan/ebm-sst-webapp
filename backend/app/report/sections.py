"""Step 3 — one-call authoring (authored.json).

All Claude-written report content is authored in **one** LLM call following
``prompts/one_call_authoring.md``. The response is ``authored.json``: a list
of blocks per section key (``exec_summary``, ``s4_3_chloride``,
``s5_1_phase1``, ``s5_2_transport``, ``s5_3_footprint``, ``s8_summary``)
plus a ``practitioner_information`` object. ``scripts/assemble_operations.py``
turns it into the operations JSON (Step 3 → 4), so this module never writes
operations or marker names itself.

Sections whose content is fully Python-authored (1, 1.1, 1.2.1, 2.x, 3.2,
4.1, 4.2, 4.2.1, 5 intro, 5.3 figures, 5.4, 7.1, 7.2, Appendix E) are not
authored here — the generator handles them.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .llm import LLMClient, LLMError, model_for
from .session import ReportSession

_SKILL_ROOT = Path(__file__).resolve().parents[2] / "report_skill"
_PROMPTS = _SKILL_ROOT / "prompts"

# (authored.json key, prompt file) — the Claude-authored content keys, in the
# order one_call_authoring.md lists them. Everything else is Python-authored.
AUTHORED_KEYS: list[tuple[str, str]] = [
    ("exec_summary", "exec_summary.md"),
    ("s4_3_chloride", "s4_3_chloride.md"),
    ("s5_1_phase1", "s5_1_phase1.md"),
    ("s5_2_transport", "s5_2_transport.md"),
    ("s5_3_footprint", "s5_3_footprint.md"),
    ("s8_summary", "s8_summary.md"),
]

MASTER_PROMPT = "one_call_authoring.md"
PRACTITIONER_PROMPT = "practitioner_information.md"

# Keys that must be null when Section 5 is absent (section5_present false).
SECTION5_KEYS = {"s5_1_phase1", "s5_2_transport", "s5_3_footprint"}

# Default max output tokens for the single consolidated authoring call.
# Claude models cap at 64k output tokens; DeepSeek caps much lower (8k).
# Override with the REPORT_MAX_TOKENS env var.
DEFAULT_AUTHOR_MAX_TOKENS = 64_000
DEEPSEEK_MAX_TOKENS = 8_000


def _author_max_tokens() -> int:
    """Resolve the authoring max_tokens, capped to the model's output limit.

    ``REPORT_MAX_TOKENS`` wins when set; otherwise DeepSeek models are capped
    at 8k (their provider limit) and everything else defaults to 64k.
    """
    env = os.environ.get("REPORT_MAX_TOKENS")
    if env:
        try:
            return int(env)
        except ValueError:
            pass
    if "deepseek" in model_for("author").lower():
        return DEEPSEEK_MAX_TOKENS
    return DEFAULT_AUTHOR_MAX_TOKENS


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


def _system_prompt() -> str:
    """Build the one-call system prompt.

    The master guide (``one_call_authoring.md``) defines the authored.json
    contract and the Section 5 gate; each per-key prompt file supplies the
    wording rules for its key. The model cannot read files, so they are all
    concatenated here.
    """
    parts = [
        _prompt_text(MASTER_PROMPT),
        "",
        "Below are the per-key wording rules. Use them as written, but return "
        "blocks only — ignore every operation/marker instruction in them.",
        "",
    ]
    for key, prompt_file in AUTHORED_KEYS:
        parts.append(f"# KEY: {key} — rules in {prompt_file}")
        parts.append(_prompt_text(prompt_file))
        parts.append("")
    parts.append(f"# KEY: practitioner_information — rules in {PRACTITIONER_PROMPT}")
    parts.append(_prompt_text(PRACTITIONER_PROMPT))
    return "\n".join(parts)


def _user_prompt(context: str, section5_present: bool) -> str:
    if section5_present:
        s5_rule = (
            "Author s5_1_phase1, s5_2_transport and s5_3_footprint. "
            "s5_1_phase1 is null when no Phase 1 ESA was provided "
            "(phase1_esa.provided is false)."
        )
    else:
        s5_rule = (
            "Set s5_1_phase1, s5_2_transport and s5_3_footprint to null, do "
            "not read those three prompt files, and write no reference to "
            "Section 5 anywhere (the generator has already removed it)."
        )
    return (
        "Author all Claude-written report content in a single pass, following "
        "the master guide and the per-key rules in the system prompt exactly.\n\n"
        f"Section 5 gate: section5_present is {'true' if section5_present else 'false'}. "
        f"{s5_rule}\n\n"
        "Return a single JSON object matching the authored.json schema in the "
        "master guide: exec_summary, s4_3_chloride, s5_1_phase1, s5_2_transport, "
        "s5_3_footprint and s8_summary (each a list of blocks, or null where the "
        "rules say so) plus practitioner_information (an object with site, report, "
        "check, uncertain, not_found and incomplete). Do not include any text "
        "outside the JSON.\n\n"
        "CONTEXT (site_facts.json, excel_data.json, intake answers):\n\n"
        f"{context}"
    )


def _normalize_authored(result: Any, section5_present: bool) -> dict[str, Any]:
    """Validate the one-call response and enforce the Section 5 gate.

    The response must be a JSON object (authored.json). When Section 5 is
    absent, the s5_* keys are forced to null regardless of what the model
    returned (assemble_operations.py rejects a non-null Section 5 key).
    """
    if not isinstance(result, dict):
        raise LLMError(
            "Section authoring returned an unexpected shape: expected a JSON "
            f"object (authored.json), got {type(result).__name__}."
        )
    if not section5_present:
        for key in SECTION5_KEYS:
            result[key] = None
    return result


def author_sections(
    session: ReportSession,
    llm: LLMClient,
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    progress: Any = None,
) -> dict[str, Any]:
    """Author all Claude-written content in a single LLM call.

    Returns the ``authored.json`` dict (blocks per section key +
    ``practitioner_information``) and persists it to ``authored.json`` in the
    session dir. ``progress`` is an optional callable
    ``(stage_message: str) -> None`` used by the background job to report the
    (single) authoring stage.
    """
    context = _context_payload(session)
    section5_present = bool((session.excel_data or {}).get("section5_present"))
    if progress:
        progress("Authoring all report sections (single LLM call)…")
    result = llm.complete_json(
        _system_prompt(),
        _user_prompt(context, section5_present),
        model=model or model_for("author"),
        max_tokens=max_tokens or _author_max_tokens(),
    )
    authored = _normalize_authored(result, section5_present)

    session.authored = authored
    session.save_authored()
    return authored