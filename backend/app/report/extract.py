"""Step 1c — unified site-facts extraction (one LLM call).

Reads every source document (ABAData, Phaseview, Phase 1 ESA, borehole logs,
other assessments, SST report) once, feeds the ingested text to a single LLM
call whose system prompt is ``prompts/site_facts_cache.md`` (the extraction
field list + rules), and returns ``site_facts.json``.

Per the skill's rules the LLM never guesses: unresolvable fields are recorded
as ``null`` plus an entry in ``extraction_flags[]``. The Excel is never read
here — it is read mechanically by the generator.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .llm import LLMClient, assemble_document_payload, ingest_documents, model_for
from .session import ReportSession

# Path to the vendored extraction field list (system prompt).
_SKILL_ROOT = Path(__file__).resolve().parents[2] / "report_skill"
SITE_FACTS_PROMPT = _SKILL_ROOT / "prompts" / "site_facts_cache.md"

# Top-level keys the extraction pass owns (everything else is a raw fact).
_FLAG_KEY = "extraction_flags"


def _system_prompt() -> str:
    if not SITE_FACTS_PROMPT.exists():
        raise FileNotFoundError(f"Missing extraction prompt: {SITE_FACTS_PROMPT}")
    return SITE_FACTS_PROMPT.read_text(encoding="utf-8")


def _user_prompt(payload: str) -> str:
    return (
        "Extract the site facts from the documents below, following the field "
        "list and rules in the system prompt exactly.\n\n"
        "Return a single JSON object matching the site_facts.json schema. "
        "Every field you cannot resolve from the documents must be `null`, and "
        "you must add an entry to the top-level `extraction_flags` array for "
        "each unresolved/ambiguous item (a short `message` plus the `field` "
        "name). Do not guess, do not invent values, do not write narrative.\n\n"
        "DOCUMENTS:\n\n"
        f"{payload}"
    )


def extract_site_facts(
    session: ReportSession,
    llm: LLMClient,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Run the extraction pass for a session; returns the site_facts dict.

    The result is stored on the session (``session.site_facts`` and
    ``session.extraction_flags``) and persisted to ``site_facts.json``.
    """
    sources = session.extract_sources()
    if not sources:
        raise ValueError("No source documents uploaded for extraction.")

    blocks = ingest_documents(sources)
    payload = assemble_document_payload(blocks)
    system = _system_prompt()
    user = _user_prompt(payload)

    result = llm.complete_json(
        system,
        user,
        model=model or model_for("extract"),
        max_tokens=16_000,
    )

    # Split the flags out of the facts object.
    flags = result.pop(_FLAG_KEY, []) or []
    if not isinstance(flags, list):
        flags = [{"message": str(flags), "field": None}]

    session.site_facts = result
    session.extraction_flags = flags
    session.save_site_facts()
    return result


def merge_cached_facts(session: ReportSession, cached: dict[str, Any]) -> None:
    """Reuse cached facts for unchanged files (skill Step 0 cache).

    The cached facts are loaded wholesale; the caller decides which files
    changed and whether to re-extract. Borehole logs are always read fresh
    per the skill (a rerun can add new logs), so callers should re-extract
    when new logs are present.
    """
    session.site_facts = dict(cached)
    session.extraction_flags = list(cached.get(_FLAG_KEY, []) or [])
    session.save_site_facts()