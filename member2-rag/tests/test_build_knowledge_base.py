"""scripts/build_knowledge_base.py: the download step (no network: urlopen is replaced)."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_knowledge_base.py"


@pytest.fixture
def build(monkeypatch):
    spec = importlib.util.spec_from_file_location("build_knowledge_base", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_knowledge_base"] = module
    spec.loader.exec_module(module)
    return module


def _manifest(tmp_path: Path, entries: list[dict]) -> Path:
    path = tmp_path / "sources" / "manifest.json"
    path.parent.mkdir()
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def _entry(name: str, url: str | None = "https://example.org/doc.pdf") -> dict:
    e = {"pdf": f"../raw/{name}.pdf", "issuing_organization": "TEST", "source_identifier": name,
         "document_version": "1"}
    if url:
        e["url"] = url
    return e


def _fake_urlopen(body: bytes, calls: list[str]):
    def urlopen(request, timeout=None):
        calls.append(request.full_url)
        return io.BytesIO(body)
    return urlopen


def test_downloads_missing_and_skips_existing(build, tmp_path, monkeypatch):
    manifest = _manifest(tmp_path, [_entry("A"), _entry("B")])
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "A.pdf").write_bytes(b"%PDF-1.7 already here")
    calls: list[str] = []
    monkeypatch.setattr(build.urllib.request, "urlopen", _fake_urlopen(b"%PDF-1.7 new", calls))
    assert build.download_sources(manifest) == []
    assert len(calls) == 1  # only B was fetched
    assert (tmp_path / "raw" / "B.pdf").read_bytes().startswith(b"%PDF-")


def test_reports_missing_url_and_non_pdf(build, tmp_path, monkeypatch):
    manifest = _manifest(tmp_path, [_entry("NoUrl", url=None), _entry("Html")])
    monkeypatch.setattr(build.urllib.request, "urlopen", _fake_urlopen(b"<html>login</html>", []))
    problems = build.download_sources(manifest)
    assert len(problems) == 2
    assert "no 'url'" in problems[0] and "did not return a PDF" in problems[1]
    assert not (tmp_path / "raw" / "Html.pdf").exists()  # nothing written for a bad download


def test_failed_download_is_reported_not_raised(build, tmp_path, monkeypatch):
    manifest = _manifest(tmp_path, [_entry("Down")])

    def boom(request, timeout=None):
        raise OSError("network down")

    monkeypatch.setattr(build.urllib.request, "urlopen", boom)
    problems = build.download_sources(manifest)
    assert len(problems) == 1 and "download failed" in problems[0]


def test_every_committed_source_has_an_official_url():
    manifest = json.loads((SCRIPT.parent.parent / "sources" / "kb_v2_manifest.json").read_text(encoding="utf-8"))
    assert manifest and all(e.get("url", "").startswith("https://") for e in manifest)
