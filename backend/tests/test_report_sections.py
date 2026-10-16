"""Section authoring tests — single consolidated call producing authored.json.

``author_sections`` must make exactly ONE LLM call and return the
``authored.json`` dict (blocks per section key + practitioner_information),
persisting it to ``authored.json`` in the session dir. The Section 5 gate
forces the s5_* keys to null when ``section5_present`` is false.
"""
from pathlib import Path

import pytest

from app.report.llm import LLMError
from app.report.sections import (
    AUTHORED_KEYS,
    SECTION5_KEYS,
    author_sections,
)
from app.report.session import ReportSession


class RecordingLLM:
    """Records every call and returns a canned response."""

    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def complete_json(self, system, user, **kwargs):
        self.calls.append({"system": system, "user": user, **kwargs})
        return self.response


def _session(tmp_path: Path, section5_present: bool = False) -> ReportSession:
    s = ReportSession(id="t", dir=tmp_path / "s")
    s.dir.mkdir(parents=True, exist_ok=True)
    s.site_facts = {"site_lsd": "08-13-016-01 W4", "client_name": "Canlin"}
    s.excel_data = {"dwda_data": None, "section5_present": section5_present}
    s.intake_answers = {"q21": "Standard Tier 1 P1"}
    return s


def _authored(section5_present: bool = False) -> dict:
    """A valid authored.json response (s5 keys null when Section 5 absent)."""
    s5 = {
        "s5_1_phase1": [{"style": "body", "text": "5.1"}],
        "s5_2_transport": [{"style": "body", "text": "5.2"}],
        "s5_3_footprint": [{"style": "body", "text": "5.3"}],
    } if section5_present else {
        "s5_1_phase1": None,
        "s5_2_transport": None,
        "s5_3_footprint": None,
    }
    return {
        "exec_summary": [{"style": "body", "text": "exec"}],
        "s4_3_chloride": [{"style": "body", "text": "4.3"}],
        **s5,
        "s8_summary": [{"style": "body", "text": "8"}],
        "practitioner_information": {
            "site": "x", "report": "x",
            "check": [], "uncertain": [], "not_found": [], "incomplete": [],
        },
    }


def test_author_sections_makes_single_call(tmp_path):
    s = _session(tmp_path)
    llm = RecordingLLM(_authored())
    authored = author_sections(s, llm)

    assert len(llm.calls) == 1
    # The system prompt contains the master guide and every per-key prompt.
    for key, prompt_file in AUTHORED_KEYS:
        assert f"# KEY: {key}" in llm.calls[0]["system"]
        assert prompt_file in llm.calls[0]["system"]
    assert "one_call_authoring.md" in llm.calls[0]["system"]
    # Persisted to the session.
    assert s.authored == authored
    assert (s.dir / "authored.json").exists()


def test_author_sections_section5_gate_forces_null(tmp_path):
    """When section5_present is false, s5_* keys are null even if the model
    returned content for them."""
    s = _session(tmp_path, section5_present=False)
    llm = RecordingLLM(_authored(section5_present=True))  # model wrongly authors 5.x
    authored = author_sections(s, llm)

    for key in SECTION5_KEYS:
        assert authored[key] is None


def test_author_sections_keeps_s5_when_present(tmp_path):
    s = _session(tmp_path, section5_present=True)
    llm = RecordingLLM(_authored(section5_present=True))
    authored = author_sections(s, llm)

    assert authored["s5_1_phase1"] == [{"style": "body", "text": "5.1"}]
    assert authored["s5_2_transport"] == [{"style": "body", "text": "5.2"}]
    assert authored["s5_3_footprint"] == [{"style": "body", "text": "5.3"}]


def test_author_sections_rejects_non_object_response(tmp_path):
    s = _session(tmp_path)
    llm = RecordingLLM([{"style": "body", "text": "x"}])
    with pytest.raises(LLMError):
        author_sections(s, llm)


def test_author_sections_passes_large_max_tokens(tmp_path, monkeypatch):
    # Clear model overrides so the default (Claude) 64k cap applies.
    monkeypatch.delenv("REPORT_MODEL_AUTHOR", raising=False)
    monkeypatch.delenv("REPORT_MODEL", raising=False)
    monkeypatch.delenv("REPORT_MAX_TOKENS", raising=False)
    s = _session(tmp_path)
    llm = RecordingLLM(_authored())
    author_sections(s, llm)
    assert llm.calls[0]["max_tokens"] >= 64_000


def test_author_sections_caps_tokens_for_deepseek(tmp_path, monkeypatch):
    """DeepSeek authoring models are capped at 8k output tokens."""
    monkeypatch.setenv("REPORT_MODEL_AUTHOR", "deepseek/deepseek-chat-v3-0324")
    monkeypatch.delenv("REPORT_MAX_TOKENS", raising=False)
    s = _session(tmp_path)
    llm = RecordingLLM(_authored())
    author_sections(s, llm)
    assert llm.calls[0]["max_tokens"] <= 8_000
    assert "deepseek" in llm.calls[0]["model"]


def test_author_sections_mentions_section5_gate_in_user_prompt(tmp_path):
    s = _session(tmp_path, section5_present=False)
    llm = RecordingLLM(_authored())
    author_sections(s, llm)
    assert "section5_present is false" in llm.calls[0]["user"]

    s2 = _session(tmp_path, section5_present=True)
    llm2 = RecordingLLM(_authored(section5_present=True))
    author_sections(s2, llm2)
    assert "section5_present is true" in llm2.calls[0]["user"]