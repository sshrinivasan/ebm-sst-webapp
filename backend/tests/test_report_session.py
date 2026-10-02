"""Session store + state machine tests for the report module."""
from pathlib import Path

import pytest

from app.report.session import ReportSession, SessionError, SessionStore, CATEGORIES


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(root=tmp_path / "sessions")


def test_create_and_get(store: SessionStore):
    session = store.create()
    assert session.state == "files"
    assert session.dir.exists()
    assert store.get(session.id) is session


def test_get_unknown_raises(store: SessionStore):
    with pytest.raises(SessionError):
        store.get("nope")


def test_add_file_validates_category(store: SessionStore):
    session = store.create()
    with pytest.raises(SessionError):
        session.add_file("bogus", "x.txt", Path("/tmp/x.txt"))


def test_add_file_and_helpers(store: SessionStore, tmp_path: Path):
    session = store.create()
    f = tmp_path / "soil.xlsm"
    f.write_bytes(b"data")
    session.add_file("excel", "soil.xlsm", f)
    assert session.excel_path() == f
    assert session.has_category("excel")
    assert not session.has_category("figures_zip")
    assert session.extract_sources() == []  # excel is not an extract source


def test_extract_sources_only_documents(store: SessionStore, tmp_path: Path):
    session = store.create()
    for cat in ["abadata", "phaseview", "phase1_esa", "borehole_logs"]:
        f = tmp_path / f"{cat}.pdf"
        f.write_bytes(b"pdf")
        session.add_file(cat, f.name, f)
    assert len(session.extract_sources()) == 4


def test_site_facts_persistence(store: SessionStore):
    session = store.create()
    session.site_facts = {"site_lsd": "08-13-016-01 W4"}
    path = session.save_site_facts()
    assert path.exists()
    import json

    assert json.loads(path.read_text())["site_lsd"] == "08-13-016-01 W4"


def test_delete_removes_dir(store: SessionStore, tmp_path: Path):
    session = store.create()
    assert session.dir.exists()
    store.delete(session.id)
    assert not session.dir.exists()
    with pytest.raises(SessionError):
        store.get(session.id)


def test_categories_are_known():
    assert "excel" in CATEGORIES
    assert "figures_zip" in CATEGORIES
    assert "borehole_logs" in CATEGORIES


def test_to_public_hides_paths(store: SessionStore, tmp_path: Path):
    session = store.create()
    f = tmp_path / "soil.xlsm"
    f.write_bytes(b"data")
    session.add_file("excel", "soil.xlsm", f)
    public = session.to_public()
    assert "path" not in str(public)
    assert public["files"]["excel"][0]["name"] == "soil.xlsm"