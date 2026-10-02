"""Extraction + pipeline tests with a mocked LLM client."""
import json
from pathlib import Path

import pytest

from app.report.extract import extract_site_facts
from app.report.llm import LLMError
from app.report.session import ReportSession


class FakeLLM:
    """Returns canned JSON for complete_json; records calls."""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.calls = []

    def complete_json(self, system, user, **kwargs):
        self.calls.append({"system": system, "user": user, **kwargs})
        if self.responses:
            return self.responses.pop(0)
        return {"site_lsd": "08-13-016-01 W4", "extraction_flags": []}


def _session_with_docs(tmp_path: Path) -> ReportSession:
    s = ReportSession(id="t", dir=tmp_path / "s")
    s.dir.mkdir(parents=True, exist_ok=True)
    doc = s.dir / "abadata" / "Abadata.docx"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("ABAData content", encoding="utf-8")
    s.add_file("abadata", doc.name, doc)
    return s


def test_extract_site_facts_stores_and_persists(tmp_path: Path):
    session = _session_with_docs(tmp_path)
    llm = FakeLLM([{"site_lsd": "08-13-016-01 W4", "site_type": "wellsite", "extraction_flags": []}])
    result = extract_site_facts(session, llm)
    assert result["site_lsd"] == "08-13-016-01 W4"
    assert session.site_facts["site_type"] == "wellsite"
    assert session.extraction_flags == []
    assert (session.dir / "site_facts.json").exists()


def test_extract_splits_flags(tmp_path: Path):
    session = _session_with_docs(tmp_path)
    llm = FakeLLM([{
        "site_lsd": None,
        "extraction_flags": [{"message": "no LSD found", "field": "site_lsd"}],
    }])
    extract_site_facts(session, llm)
    assert session.site_facts.get("site_lsd") is None
    assert session.extraction_flags[0]["message"] == "no LSD found"


def test_extract_requires_sources(tmp_path: Path):
    session = ReportSession(id="t", dir=tmp_path / "s")
    with pytest.raises(ValueError):
        extract_site_facts(session, FakeLLM())


def test_extract_uses_extract_model(tmp_path: Path):
    session = _session_with_docs(tmp_path)
    llm = FakeLLM()
    extract_site_facts(session, llm)
    assert llm.calls[0]["model"] is not None


def test_llm_error_propagates(tmp_path: Path):
    session = _session_with_docs(tmp_path)

    class BoomLLM:
        def complete_json(self, system, user, **kwargs):
            raise LLMError("boom")

    with pytest.raises(LLMError):
        extract_site_facts(session, BoomLLM())


def test_ingest_documents_reads_text(tmp_path: Path):
    from app.report.llm import ingest_documents

    f = tmp_path / "notes.txt"
    f.write_text("hello world", encoding="utf-8")
    blocks = ingest_documents([f])
    assert blocks[0]["name"] == "notes.txt"
    assert "hello world" in blocks[0]["text"]


def test_ingest_documents_skips_missing(tmp_path: Path):
    from app.report.llm import ingest_documents

    blocks = ingest_documents([tmp_path / "missing.pdf"])
    assert blocks == []