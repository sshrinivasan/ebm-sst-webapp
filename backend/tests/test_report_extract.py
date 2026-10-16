"""Extraction + pipeline tests with a mocked LLM client."""
import json
from pathlib import Path

import pytest

from app.report.extract import _build_system_prompt, extract_site_facts
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


def test_system_prompt_filters_by_category():
    """The field list only includes sections for the uploaded filetypes."""
    full = _build_system_prompt({"abadata", "phaseview", "phase1_esa", "borehole_logs"})
    # All field-list section headers present when all categories uploaded.
    assert "### ABAData Word doc" in full
    assert "### Phaseview PDF" in full
    assert "### AER Phase 1 ESA" in full
    assert "### Borehole log PDFs" in full
    # Shared sections always present.
    assert "## Schema" in full
    assert "## Purpose" in full

    esa_only = _build_system_prompt({"phase1_esa"})
    assert "### AER Phase 1 ESA" in esa_only
    assert "### ABAData Word doc" not in esa_only
    assert "### Phaseview PDF" not in esa_only
    assert "### Borehole log PDFs" not in esa_only
    # Schema still kept.
    assert "## Schema" in esa_only
    assert len(esa_only) < len(full)


# ---------------------------------------------------------------------------
# Cached site facts (download / upload)
# ---------------------------------------------------------------------------


def test_source_files_lists_extract_categories(tmp_path: Path):
    from app.report.extract import source_files

    s = ReportSession(id="t", dir=tmp_path / "s")
    s.dir.mkdir(parents=True, exist_ok=True)
    for cat, name in [("abadata", "Abadata.docx"), ("phaseview", "Phaseview.pdf"), ("excel", "table.xlsm")]:
        p = s.dir / cat / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
        s.add_file(cat, name, p)
    files = source_files(s)
    # Only extract categories are listed (excel is not a source document).
    assert files == [
        {"category": "abadata", "name": "Abadata.docx"},
        {"category": "phaseview", "name": "Phaseview.pdf"},
    ]


def test_load_cached_facts_sets_and_persists(tmp_path: Path):
    from app.report.extract import load_cached_facts

    s = ReportSession(id="t", dir=tmp_path / "s")
    s.dir.mkdir(parents=True, exist_ok=True)
    load_cached_facts(
        s,
        {"client_name": "ACME", "site_lsd": "08-13-016-01 W4"},
        [{"message": "flag", "field": "x"}],
    )
    assert s.site_facts["client_name"] == "ACME"
    assert s.extraction_flags == [{"message": "flag", "field": "x"}]
    assert (s.dir / "site_facts.json").exists()


def test_facts_endpoints_round_trip(tmp_path: Path):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.report.session import store

    store.clear()
    session = store.create()
    doc = session.dir / "abadata" / "Abadata.docx"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("x", encoding="utf-8")
    session.add_file("abadata", "Abadata.docx", doc)

    client = TestClient(app)

    # Download before any facts exist -> 404.
    r = client.get(f"/api/report/facts/{session.id}")
    assert r.status_code == 404

    # Load cached facts -> state becomes facts_review.
    r = client.post(
        f"/api/report/facts/load?session_id={session.id}",
        json={
            "site_facts": {"client_name": "ACME", "site_lsd": "08-13-016-01 W4"},
            "extraction_flags": [{"message": "flag", "field": "x"}],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "facts_review"
    assert body["site_facts"]["client_name"] == "ACME"

    # Download now returns the wrapped JSON with source_files.
    r = client.get(f"/api/report/facts/{session.id}")
    assert r.status_code == 200
    payload = r.json()
    assert payload["site_facts"]["client_name"] == "ACME"
    assert payload["source_files"] == [{"category": "abadata", "name": "Abadata.docx"}]

    # Inspect a cached file -> returns client + LSD + source_files, no mutation.
    cached = {
        "site_facts": {"client_name": "ACME", "site_lsd": "08-13-016-01 W4"},
        "extraction_flags": [],
        "source_files": [{"category": "abadata", "name": "Abadata.docx"}],
    }
    r = client.post(
        f"/api/report/facts/inspect?session_id={session.id}",
        files={"file": ("site_facts.json", json.dumps(cached), "application/json")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["client_name"] == "ACME"
    assert body["site_lsd"] == "08-13-016-01 W4"
    assert body["source_files"] == [{"category": "abadata", "name": "Abadata.docx"}]

    # Inspect rejects invalid JSON.
    r = client.post(
        f"/api/report/facts/inspect?session_id={session.id}",
        files={"file": ("bad.json", "not json", "application/json")},
    )
    assert r.status_code == 400


def test_confirm_extract_persists_edited_facts(tmp_path: Path):
    """The curated review edits site_facts; /extract/confirm must persist them."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.report.session import store

    store.clear()
    session = store.create()
    session.site_facts = {"client_name": "Old Client", "site_lsd": "08-13-016-01 W4"}
    session.extraction_flags = [{"message": "flag", "field": "client_name"}]
    session.save_site_facts()

    client = TestClient(app)
    r = client.post(
        f"/api/report/extract/confirm?session_id={session.id}",
        json={
            "site_facts": {"client_name": "Corrected Client", "site_lsd": "08-13-016-01 W4"},
            "extraction_flags": [],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["site_facts"]["client_name"] == "Corrected Client"
    assert body["extraction_flags"] == []
    # Persisted to disk too.
    import json as _json

    on_disk = _json.loads((session.dir / "site_facts.json").read_text(encoding="utf-8"))
    assert on_disk["client_name"] == "Corrected Client"