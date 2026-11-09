"""Knowledge base: schema validation, input files, IDs, duplicates, persistence."""

from __future__ import annotations

import json

import pytest

from app.hashing import compute_content_hash, make_chunk_id
from app.knowledge_base.document_store import ChromaDocumentStore, EmbeddingModelMismatchError, natural_key
from app.knowledge_base.indexing import InputFileError, index_jsonl, load_jsonl, parse_records
from app.knowledge_base.metadata import from_chroma_metadata, to_chroma_metadata
from app.schemas import ApplicabilityStatus, PassageRecord
from tests.conftest import FakeEmbedder, make_record, write_jsonl


# --- schema validation --------------------------------------------------------
def test_valid_record_gets_hash_and_normalised_ctd():
    rec = PassageRecord(**make_record(ctd_section="3.2.s.4.1"))
    meta = rec.to_metadata()
    assert meta.ctd_section == "3.2.S.4.1"
    assert meta.content_hash == compute_content_hash(rec.text)
    assert meta.provenance_complete


@pytest.mark.parametrize(
    "override, field",
    [
        ({"text": "   "}, "text"),
        ({"source_title": ""}, "source_title"),
        ({"document_type": "blog_post"}, "document_type"),
        ({"publication_date": "15/01/2020"}, "publication_date"),
        ({"page_number": 0}, "page_number"),
        ({"ctd_section": "section four"}, "ctd_section"),
        ({"chunk_id": "has spaces!"}, "chunk_id"),
        ({"unexpected_field": 1}, "unexpected_field"),
    ],
)
def test_invalid_records_are_rejected_with_field_name(override, field):
    result = parse_records([json.dumps(make_record(**override))])
    assert not result.records
    assert len(result.errors) == 1
    assert field in result.errors[0].message
    # error messages must not echo passage text
    assert "Synthetic test passage" not in result.errors[0].message


def test_content_hash_mismatch_rejected():
    result = parse_records([json.dumps(make_record(content_hash="0" * 64))])
    assert result.errors and "content_hash" in result.errors[0].message


def test_missing_optional_metadata_is_explicit_not_invented():
    rec = PassageRecord(**make_record(document_version=None, publication_date=None, page_number=None,
                                      applicability_status="unknown"))
    meta = rec.to_metadata()
    assert meta.document_version is None
    assert set(meta.missing_provenance()) == {
        "document_version", "page_number", "publication_or_effective_date", "applicability_status"
    }
    flat = to_chroma_metadata(meta, "m")
    assert "document_version" not in flat and "page_number" not in flat  # omitted, not faked
    assert flat["provenance_complete"] is False
    assert from_chroma_metadata(flat) == meta


# --- input files ---------------------------------------------------------------
def test_missing_file(tmp_path):
    with pytest.raises(InputFileError, match="not found"):
        load_jsonl(tmp_path / "nope.jsonl")


def test_empty_file(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("\n\n", encoding="utf-8")
    with pytest.raises(InputFileError, match="empty"):
        load_jsonl(path)


def test_wrong_extension(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("a,b", encoding="utf-8")
    with pytest.raises(InputFileError, match=r"\.jsonl"):
        load_jsonl(path)


def test_malformed_lines_reported_and_valid_lines_kept(tmp_path):
    path = write_jsonl(tmp_path / "mixed.jsonl", [
        make_record(chunk_id="ok-1"),
        "{not json",
        "[1, 2, 3]",
        make_record(chunk_id="ok-2", text="Another synthetic passage."),
    ])
    result = load_jsonl(path)
    assert [r.chunk_id for r in result.records] == ["ok-1", "ok-2"]
    assert [e.line_number for e in result.errors] == [2, 3]


def test_strict_mode_aborts(tmp_path, store, embedder):
    path = write_jsonl(tmp_path / "bad.jsonl", [make_record(), "{oops"])
    with pytest.raises(InputFileError, match="strict"):
        index_jsonl(path, store, embedder, strict=True)
    assert store.count() == 0


def test_windows_bom_tolerated(tmp_path):
    path = tmp_path / "bom.jsonl"
    path.write_text(json.dumps(make_record()) + "\n", encoding="utf-8-sig")
    assert len(load_jsonl(path).records) == 1


# --- stable IDs and duplicates -------------------------------------------------
def test_generated_chunk_id_is_stable():
    a = PassageRecord(**make_record(chunk_id=None))
    b = PassageRecord(**make_record(chunk_id=None))
    assert a.chunk_id == b.chunk_id and a.chunk_id.startswith("m2-")


def test_positional_id_survives_text_correction():
    a = PassageRecord(**make_record(chunk_id=None, text="Original text."))
    b = PassageRecord(**make_record(chunk_id=None, text="Corrected text."))
    assert a.chunk_id == b.chunk_id  # same page + chunk_index -> update, not duplicate


def test_id_without_position_uses_content():
    h1, h2 = compute_content_hash("x"), compute_content_hash("y")
    assert make_chunk_id("S", "1", None, None, h1) != make_chunk_id("S", "1", None, None, h2)


def test_whitespace_only_difference_same_hash():
    assert compute_content_hash("NMT  0.1%\n") == compute_content_hash("NMT 0.1%")


def test_identical_duplicate_lines_skipped():
    line = json.dumps(make_record())
    result = parse_records([line, line])
    assert len(result.records) == 1 and result.skipped_duplicates == ["syn-001"]


def test_conflicting_duplicate_ids_both_rejected():
    result = parse_records([
        json.dumps(make_record(text="Version one.")),
        json.dumps(make_record(text="Version two.")),
    ])
    assert not result.records
    assert len(result.errors) == 2 and all("conflicting" in e.message for e in result.errors)


# --- indexing and persistence ----------------------------------------------------
def test_index_add_unchanged_update(tmp_path, store, embedder):
    path = write_jsonl(tmp_path / "p.jsonl", [make_record(chunk_id="a"), make_record(chunk_id="b", text="B text")])
    r1 = index_jsonl(path, store, embedder)
    assert (r1.added, r1.updated, r1.unchanged) == (2, 0, 0)
    calls = embedder.document_calls

    r2 = index_jsonl(path, store, embedder)
    assert (r2.added, r2.updated, r2.unchanged) == (0, 0, 2)
    assert embedder.document_calls == calls  # unchanged passages are not re-embedded

    write_jsonl(path, [make_record(chunk_id="a", text="A corrected"), make_record(chunk_id="b", text="B text")])
    r3 = index_jsonl(path, store, embedder)
    assert (r3.added, r3.updated, r3.unchanged) == (0, 1, 1)
    assert store.get(["a"])[0].text == "A corrected"
    assert store.count() == 2


def test_metadata_only_change_is_stored_without_re_embedding(tmp_path, store, embedder):
    path = write_jsonl(tmp_path / "p.jsonl", [make_record(chunk_id="a", page_number=7)])
    index_jsonl(path, store, embedder)
    calls = embedder.document_calls

    # Same text, new detail (the printed page number): stored, but not re-embedded.
    write_jsonl(path, [make_record(chunk_id="a", page_number=7, page_label="3")])
    report = index_jsonl(path, store, embedder)
    assert (report.added, report.updated, report.unchanged) == (0, 1, 0)
    assert embedder.document_calls == calls
    assert store.get(["a"])[0].metadata.page_label == "3"

    again = index_jsonl(path, store, embedder)
    assert (again.updated, again.unchanged) == (0, 1)


def test_page_label_is_validated(tmp_path):
    loaded = load_jsonl(write_jsonl(tmp_path / "p.jsonl", [make_record(page_label="3; DROP TABLE")]))
    assert loaded.errors and "page_label" in loaded.errors[0].message


def test_dry_run_writes_nothing(tmp_path, store, embedder):
    path = write_jsonl(tmp_path / "p.jsonl", [make_record()])
    report = index_jsonl(path, store, embedder, dry_run=True)
    assert report.valid_records == 1 and store.count() == 0 and embedder.document_calls == 0


def test_persistence_across_instances(settings, embedder, populated_store):
    reopened = ChromaDocumentStore(settings.chroma_dir, settings.collection_name, embedder.model_name)
    assert reopened.count() == populated_store.count() == 5
    stored = reopened.get(["syn-val-1"])[0]
    assert stored.metadata.ctd_section == "3.2.S.4.3"
    assert stored.metadata.applicability_status == ApplicabilityStatus.CURRENT


def test_collection_pinned_to_embedding_model(settings, populated_store):
    with pytest.raises(EmbeddingModelMismatchError):
        ChromaDocumentStore(settings.chroma_dir, settings.collection_name, "another-model")


def test_dimension_mismatch_detected(settings, populated_store):
    other = FakeEmbedder(dim=32)
    with pytest.raises(EmbeddingModelMismatchError):
        ChromaDocumentStore(settings.chroma_dir, settings.collection_name, "fake-embedder", other.dimension)


def test_natural_key_orders_page_numbers_numerically():
    ids = ["doc-p10-c0", "doc-p2-c1", "doc-p1-c0", "doc-p2-c0", "alpha"]
    assert sorted(ids, key=natural_key) == ["alpha", "doc-p1-c0", "doc-p2-c0", "doc-p2-c1", "doc-p10-c0"]


def test_get_missing_ids_returns_only_existing(populated_store):
    assert [p.chunk_id for p in populated_store.get(["syn-val-1", "does-not-exist"])] == ["syn-val-1"]
