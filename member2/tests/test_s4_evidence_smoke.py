"""S.4 smoke test: verifies correct distinction among evidence class types.

Tests that:
- Regulatory guidance is retrieved from the regulatory ChromaDB collection (Class A)
- Sponsor dossier evidence is retrieved only from the dossier ChromaDB (Class D)
- Provisional/unapproved sources remain quarantined (approved=False)
- Human-review flag is correctly set on dossier chunks
- Collections cannot be cross-queried (dossier != regulatory)
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent

REG_REPORT = PROJECT / "local_indexes" / "regulatory_chroma" / "ACTUAL_CHROMA_RUN.json"
DOSSIER_REPORT = PROJECT / "local_indexes" / "dossier_chroma" / "DOSSIER_CHROMA_RUN.json"
COPY_MANIFEST = PROJECT / "pharmacopoeia" / "incoming" / "COPY_MANIFEST.json"
QUARANTINE_DIR = PROJECT / "pharmacopoeia" / "quarantine"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def reg_store():
    """Return the live regulatory ChromaDB store."""
    pytest.importorskip("chromadb")
    if not REG_REPORT.exists():
        pytest.skip("Regulatory ChromaDB not built")
    from m2.embeddings import SentenceTransformerEmbedder
    from m2.storage import ChromaVectorStore
    embedder = SentenceTransformerEmbedder("BAAI/bge-large-en-v1.5")
    return ChromaVectorStore(
        embedder,
        str(PROJECT / "local_indexes" / "regulatory_chroma"),
        collection_prefix="regulatory_technical_unapproved",
    )


@pytest.fixture(scope="module")
def dossier_store():
    """Return the live dossier ChromaDB store."""
    pytest.importorskip("chromadb")
    if not DOSSIER_REPORT.exists():
        pytest.skip("Dossier ChromaDB not built")
    from m2.embeddings import SentenceTransformerEmbedder
    from m2.storage import ChromaVectorStore
    embedder = SentenceTransformerEmbedder("BAAI/bge-large-en-v1.5")
    return ChromaVectorStore(
        embedder,
        str(PROJECT / "local_indexes" / "dossier_chroma"),
        collection_prefix="sponsor_dossier_unverified",
    )


# ---------------------------------------------------------------------------
# S.4.1 — Regulatory evidence (Class A) retrieval
# ---------------------------------------------------------------------------

class TestRegulatoryEvidenceClass:
    """Regulatory ChromaDB returns Class A guidance chunks only."""

    def test_regulatory_chunks_are_not_dossier(self, reg_store):
        """No chunk in regulatory collection has chunk_kind='dossier'."""
        hits = reg_store.search("analytical procedure validation specification", limit=10)
        assert hits, "Regulatory store returned no results"
        for chunk, _ in hits:
            assert chunk.chunk_kind != "dossier", (
                f"Dossier chunk leaked into regulatory collection: {chunk.chunk_id}"
            )

    def test_regulatory_chunks_have_known_source_ids(self, reg_store):
        """Top results have source IDs matching known regulatory corpus entries."""
        reg_report = json.loads(REG_REPORT.read_text(encoding="utf-8"))
        # Regulatory chunks should not reference 'dossier_' prefixed source_ids
        hits = reg_store.search("ICH guideline drug substance specification", limit=10)
        for chunk, _ in hits:
            assert not chunk.source_id.startswith("dossier_"), (
                f"source_id '{chunk.source_id}' from dossier found in regulatory store"
            )

    def test_regulatory_chunk_metadata_approved_flag(self, reg_store):
        """Chunks in regulatory store must have approved=False in metadata (unapproved collection)."""
        hits = reg_store.search("ICH Q6A specification test procedure", limit=5)
        assert hits
        # The collection is labelled unapproved — no chunk should be marked approved=True
        for chunk, _ in hits:
            approved = chunk.metadata.get("approved", False)
            # Regulatory corpus: approved may be absent or False; never True in unapproved collection
            assert approved is not True, (
                f"Chunk {chunk.chunk_id} incorrectly marked approved=True in unapproved collection"
            )


# ---------------------------------------------------------------------------
# S.4.2 — Sponsor dossier evidence (Class D) isolation
# ---------------------------------------------------------------------------

class TestDossierEvidenceClass:
    """Dossier ChromaDB contains only Class D sponsor evidence and is isolated."""

    def test_dossier_chunks_have_class_d_classification(self, dossier_store):
        """All dossier chunks must have classification=D_SPONSOR_DOSSIER."""
        hits = dossier_store.search("valsartan analytical procedure validation", limit=10)
        assert hits, "Dossier store returned no results"
        for chunk, _ in hits:
            classification = chunk.metadata.get("classification")
            assert classification == "D_SPONSOR_DOSSIER", (
                f"Chunk {chunk.chunk_id} has unexpected classification '{classification}'"
            )

    def test_dossier_chunks_require_human_review(self, dossier_store):
        """All dossier chunks must have requires_human_review=True."""
        hits = dossier_store.search("batch analysis specification", limit=10)
        assert hits
        for chunk, _ in hits:
            assert chunk.metadata.get("requires_human_review") is True, (
                f"Chunk {chunk.chunk_id} missing requires_human_review=True"
            )

    def test_dossier_chunks_have_dossier_chunk_kind(self, dossier_store):
        """All dossier chunks must have chunk_kind='dossier'."""
        hits = dossier_store.search("hydrochlorothiazide stability impurities", limit=10)
        assert hits
        for chunk, _ in hits:
            assert chunk.chunk_kind == "dossier", (
                f"Chunk {chunk.chunk_id} has chunk_kind='{chunk.chunk_kind}', expected 'dossier'"
            )

    def test_dossier_source_ids_prefixed_correctly(self, dossier_store):
        """All dossier source_ids must start with 'dossier_'."""
        hits = dossier_store.search("amlodipine reference standards", limit=10)
        assert hits
        for chunk, _ in hits:
            assert chunk.source_id.startswith("dossier_"), (
                f"Unexpected source_id '{chunk.source_id}' — must start with 'dossier_'"
            )

    def test_dossier_approved_is_false(self, dossier_store):
        """No dossier chunk may have approved=True."""
        hits = dossier_store.search("valsartan impurities qualification", limit=10)
        assert hits
        for chunk, _ in hits:
            assert chunk.metadata.get("approved") is False, (
                f"Chunk {chunk.chunk_id} has approved != False"
            )


# ---------------------------------------------------------------------------
# S.4.3 — Collection isolation (cross-query impossibility)
# ---------------------------------------------------------------------------

class TestCollectionIsolation:
    """Verify that regulatory and dossier stores cannot cross-contaminate."""

    def test_regulatory_collection_name_differs_from_dossier(self, reg_store, dossier_store):
        """Collection names must be different."""
        assert reg_store.collection_name != dossier_store.collection_name, (
            "Regulatory and dossier collections have the same name — isolation violated"
        )

    def test_regulatory_collection_has_no_dossier_substance_chunks(self, reg_store):
        """Regulatory store must not contain chunks whose source_id starts with 'dossier_'."""
        chunks = reg_store.all_chunks()
        dossier_leaks = [c for c in chunks if c.source_id.startswith("dossier_")]
        assert not dossier_leaks, (
            f"{len(dossier_leaks)} dossier chunk(s) found in regulatory collection"
        )

    def test_dossier_collection_has_no_regulatory_chunks(self, dossier_store):
        """Dossier store must not contain chunks whose chunk_kind != 'dossier'."""
        chunks = dossier_store.all_chunks()
        non_dossier = [c for c in chunks if c.chunk_kind != "dossier"]
        assert not non_dossier, (
            f"{len(non_dossier)} non-dossier chunk(s) found in dossier collection"
        )


# ---------------------------------------------------------------------------
# S.4.4 — Provisional (quarantine) sources remain quarantined
# ---------------------------------------------------------------------------

class TestProvisionalSources:
    """HTML sources in quarantine must have approved=False in the manifest."""

    def test_quarantine_manifest_entries_have_approved_false(self):
        """COPY_MANIFEST quarantine entries must all have approved=False."""
        manifest = json.loads(COPY_MANIFEST.read_text(encoding="utf-8"))
        # Structure: {"copies": [...], "html_quarantine": [...]}
        quarantine_entries = manifest.get("html_quarantine", []) if isinstance(manifest, dict) else []
        assert quarantine_entries, "No html_quarantine entries in COPY_MANIFEST"
        for entry in quarantine_entries:
            assert entry.get("approved") is False, (
                f"Quarantine entry {entry.get('filename')} has approved != False"
            )

    def test_quarantine_html_files_exist(self):
        """Quarantine directory must contain HTML files."""
        html_files = list(QUARANTINE_DIR.glob("*.html"))
        assert html_files, f"No HTML files found in quarantine: {QUARANTINE_DIR}"
        assert len(html_files) == 5, f"Expected 5 quarantine HTML files, found {len(html_files)}"

    def test_quarantine_files_not_in_regulatory_corpus(self, reg_store):
        """Quarantined HTML sources must not appear in the regulatory ChromaDB."""
        html_files = list(QUARANTINE_DIR.glob("*.html"))
        quarantine_names = {f.stem for f in html_files}
        chunks = reg_store.all_chunks()
        for chunk in chunks:
            for q_name in quarantine_names:
                assert q_name not in chunk.source_id, (
                    f"Quarantined source '{q_name}' found in regulatory chunk {chunk.chunk_id}"
                )


# ---------------------------------------------------------------------------
# S.4.5 — Human-review annotation round-trip
# ---------------------------------------------------------------------------

class TestHumanReviewAnnotation:
    """Dossier search results correctly surface the human-review requirement."""

    def test_search_results_surface_human_review_flag(self, dossier_store):
        """search() must return chunks with requires_human_review=True for dossier queries."""
        hits = dossier_store.search("specification analytical method validation", limit=5)
        assert hits
        flagged = [c for c, _ in hits if c.metadata.get("requires_human_review") is True]
        assert len(flagged) == len(hits), (
            f"Only {len(flagged)}/{len(hits)} hits have requires_human_review=True"
        )

    def test_dossier_chunk_kind_in_search_results(self, dossier_store):
        """search() results must all have chunk_kind='dossier'."""
        hits = dossier_store.search("batch release analytical procedure", limit=5)
        assert hits
        for chunk, score in hits:
            assert chunk.chunk_kind == "dossier"
            assert 0.0 <= score <= 1.0, f"Score {score} out of [0,1] range"
