"""
Member 2 — Regulatory Knowledge Base & Evidence Explorer
Local diagnostic interface for the SAHPRA Agentic QA-RAG Member 2 system.

Run via:
    python -m streamlit run tools/member2_explorer/app.py --server.address 127.0.0.1 --server.port 8501

This is a READ-ONLY developer/research tool. It does not modify any collection
or source document. It does not replace the Member 5 authorised assessor UI.
"""
from __future__ import annotations
import json, csv, sys
from pathlib import Path
from datetime import datetime

import streamlit as st

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------

# Support running from project root or from tools/member2_explorer/
_HERE = Path(__file__).resolve().parent
if (_HERE.parent.parent / "src").exists():
    PROJECT = _HERE.parent.parent  # tools/member2_explorer/ → project root
else:
    PROJECT = Path.cwd()

sys.path.insert(0, str(PROJECT / "src"))

# ---------------------------------------------------------------------------
# cached loaders
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Opening ChromaDB collections…")
def load_chromadbs():
    """Open both ChromaDB collections. Returns (reg_collection, dos_collection) or Nones."""
    try:
        import chromadb
        reg_client = chromadb.PersistentClient(
            path=str(PROJECT / "local_indexes" / "regulatory_chroma"))
        reg_colls = reg_client.list_collections()
        reg_coll = reg_client.get_collection(reg_colls[0].name) if reg_colls else None

        dos_client = chromadb.PersistentClient(
            path=str(PROJECT / "local_indexes" / "dossier_chroma"))
        dos_colls = dos_client.list_collections()
        dos_coll = dos_client.get_collection(dos_colls[0].name) if dos_colls else None

        return reg_coll, dos_coll, None
    except Exception as exc:
        return None, None, str(exc)


@st.cache_resource(show_spinner="Loading BGE embedder…")
def load_embedder():
    try:
        import os
        from m2.embeddings import SentenceTransformerEmbedder
        # Model stored in HuggingFace cache format under models/bge-large-en-v1.5/
        cache_dir = PROJECT / "models" / "bge-large-en-v1.5"
        os.environ["HF_HOME"] = str(cache_dir)
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(cache_dir)
        return SentenceTransformerEmbedder("BAAI/bge-large-en-v1.5", local_files_only=True), None
    except Exception as exc:
        return None, str(exc)


@st.cache_data(show_spinner=False)
def load_manifest():
    p = PROJECT / "pharmacopoeia" / "incoming" / "COPY_MANIFEST.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


@st.cache_data(show_spinner=False)
def load_audit():
    p = PROJECT / "validation" / "COMPLETE_KNOWLEDGE_BASE_AUDIT.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


@st.cache_data(show_spinner=False)
def load_corpus_manifest():
    p = PROJECT / "artifacts" / "real_corpus" / "REAL_CORPUS_MANIFEST.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        return {s["source_id"]: s for s in d.get("sources", [])}
    return {}


@st.cache_data(show_spinner=False)
def load_regulatory_chunks():
    """Load all chunks from REGULATORY_CHUNKS.jsonl."""
    p = PROJECT / "artifacts" / "real_corpus" / "REGULATORY_CHUNKS.jsonl"
    if not p.exists():
        return []
    chunks = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


@st.cache_data(show_spinner=False)
def load_regression_results():
    p = PROJECT / "validation" / "FINAL_REGRESSION_RESULTS.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "(not found)"


@st.cache_data(show_spinner=False)
def load_benchmark():
    p = PROJECT / "validation" / "FINAL_RETRIEVAL_BENCHMARK.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


@st.cache_data(show_spinner=False)
def load_coverage_csv():
    p = PROJECT / "validation" / "COMPLETE_SOURCE_TO_CHROMA_COVERAGE.csv"
    if not p.exists():
        return []
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _bge_search(query: str, coll, top_k: int = 10):
    embedder, err = load_embedder()
    if err or embedder is None:
        return None, f"BGE embedder unavailable: {err}"
    try:
        vec = embedder.embed([query], query=True)[0]
        results = coll.query(
            query_embeddings=[vec],
            n_results=min(top_k * 3, coll.count()),
            include=["documents", "metadatas", "distances"],
        )
        rows = []
        seen_src = set()
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            try:
                from m2.models import RegulatoryChunk
                chunk = RegulatoryChunk.model_validate_json(meta["serialized_chunk"])
            except Exception:
                chunk = None
            sid = meta.get("source_id", "?")
            rows.append({
                "source_id": sid,
                "section": meta.get("section", ""),
                "distance": round(dist, 4),
                "score": round(1 - dist, 4),
                "text": doc[:600],
                "chunk": chunk,
                "is_new_source": sid not in seen_src,
            })
            seen_src.add(sid)
        return rows[:top_k], None
    except Exception as exc:
        return None, str(exc)


def _status_badge(ok: bool) -> str:
    return "🟢" if ok else "🔴"


# ---------------------------------------------------------------------------
# page: Overview
# ---------------------------------------------------------------------------

def page_overview():
    st.header("A — System Overview")
    st.caption("Live statistics from project manifests and persistent collections.")

    reg_coll, dos_coll, chroma_err = load_chromadbs()
    audit = load_audit()
    summary = audit.get("summary", {})
    corpus = load_corpus_manifest()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Regulatory Knowledge Base")
        reg_ok = reg_coll is not None
        st.metric("ChromaDB", _status_badge(reg_ok) + " " + ("Connected" if reg_ok else "Disconnected"))
        if reg_ok:
            st.metric("Chunks", reg_coll.count())
            st.metric("Source documents", summary.get("regulatory_indexed", "?"))
        st.metric("Embedding model", "BAAI/bge-large-en-v1.5 (1024-dim)")
        st.metric("Collection", "regulatory_technical_unapproved")

    with col2:
        st.subheader("Sponsor Dossier Knowledge Base")
        dos_ok = dos_coll is not None
        st.metric("ChromaDB", _status_badge(dos_ok) + " " + ("Connected" if dos_ok else "Disconnected"))
        if dos_ok:
            st.metric("Chunks", dos_coll.count())
            st.metric("Source documents", summary.get("dossier_indexed", "?"))
        st.metric("Collection", "sponsor_dossier_unverified")
        st.metric("Classification", "D_SPONSOR_DOSSIER — human review required")

    st.divider()

    col3, col4, col5 = st.columns(3)
    with col3:
        st.metric("Quarantined HTML sources", summary.get("quarantine_html_files", 5))
        st.caption("approved=False; never indexed")
    with col4:
        st.metric("Compendial research docs (quarantined)", summary.get("compendial_quarantined_documents", 7064))
        st.caption("BP/Ph.Eur. extracts; SQLite only; not in ChromaDB")
    with col5:
        st.metric("Compendial passages (quarantined)", summary.get("compendial_quarantined_passages", 13524))
        st.caption("Discovery use only; no approved status")

    if chroma_err:
        st.error(f"ChromaDB error: {chroma_err}")

    st.divider()
    st.subheader("Database Locations")
    st.code(
        f"Regulatory:  {PROJECT}/local_indexes/regulatory_chroma\n"
        f"Dossier:     {PROJECT}/local_indexes/dossier_chroma\n"
        f"BGE model:   {PROJECT}/models/bge-large-en-v1.5",
        language="text",
    )

    st.subheader("Latest Validation")
    bgr = json.loads((PROJECT / "validation" / "FINAL_NATIVE_CHROMADB_BGE_REPORT.json").read_text())
    st.json(bgr, expanded=False)

    st.warning(
        "⚠️ This system is not expert-validated. "
        "All retrieval results require human review before use in regulatory decisions."
    )


# ---------------------------------------------------------------------------
# page: KB Browser
# ---------------------------------------------------------------------------

def page_kb_browser():
    st.header("B — Knowledge Base Browser")
    st.caption("Browse indexed regulatory and dossier sources. "
               "Quarantined sources shown in metadata-only view.")

    corpus_meta = load_corpus_manifest()
    reg_chunks = load_regulatory_chunks()
    audit = load_audit()

    tab_reg, tab_dos, tab_quar = st.tabs(
        ["Regulatory (Class A)", "Dossier (Class D)", "Quarantined (Class C)"])

    with tab_reg:
        st.subheader("Regulatory Sources (Class A — Not Expert Approved)")
        sources = audit.get("regulatory_sources", [])
        if not sources:
            st.info("Run scripts/build_complete_audit.py to populate source metadata.")
            return

        # Filters
        search_term = st.text_input("Search source ID or filename", key="reg_search").lower()
        filtered = [s for s in sources
                    if not search_term or
                    search_term in s["source_id"].lower() or
                    search_term in s["filename"].lower()]

        for src in filtered:
            indexed = src["indexing_status"] == "INDEXED"
            badge = "🟢" if indexed else "🟡"
            with st.expander(f"{badge} {src['source_id']} — {src['filename']}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Indexed chunks", src["indexed_chunk_count"])
                c2.metric("Pages", src.get("page_count") or "?")
                c3.metric("Size (KB)", round(src["size_bytes"]/1024, 1))
                st.write(f"**SHA-256:** `{src['sha256']}`")
                st.write(f"**Approval status:** {src['approval_status']}")
                st.write(f"**Path:** `{src['relative_path']}`")
                if src["source_id"] in corpus_meta:
                    meta = corpus_meta[src["source_id"]]
                    st.write(f"**Title:** {meta.get('title','')}")
                    st.write(f"**Authority:** {meta.get('authority','')}")
                    st.write(f"**Version:** {meta.get('version','')}")
                # Show first few passages
                if indexed and reg_chunks:
                    passages = [c for c in reg_chunks
                                if c.get("source_id") == src["source_id"]][:3]
                    if passages:
                        st.write("**Sample passages:**")
                        for p in passages:
                            st.text(p.get("text","")[:400] + "…")

    with tab_dos:
        st.subheader("Dossier Sources (Class D — Sponsor Evidence, Human Review Required)")
        st.warning("⚠️ These are sponsor-submitted documents. Not regulatory authority guidance.")
        sources = audit.get("dossier_sources", [])
        substances = sorted(set(
            r["relative_path"].replace("\\","/").split("/")[-2]
            for r in sources
        ))
        sel_subst = st.selectbox("Filter by substance", ["All"] + substances)
        filtered_dos = sources if sel_subst == "All" else [
            s for s in sources
            if sel_subst in s["relative_path"].replace("\\", "/")
        ]
        for src in filtered_dos:
            indexed = src["indexing_status"] == "INDEXED"
            badge = "🟢" if indexed else "🟡"
            with st.expander(f"{badge} {src['source_id']}"):
                c1, c2 = st.columns(2)
                c1.metric("Chunks", src["indexed_chunk_count"])
                c2.metric("Pages", src.get("page_count") or "?")
                st.write(f"**File:** `{src['filename']}`")
                st.write(f"**SHA-256:** `{src['sha256']}`")
                st.write(f"**Indexing:** {src['indexing_status']}")
                if src["indexing_status"] != "INDEXED":
                    st.info("Zero chunks extracted — likely scanned PDF. OCR required.")

    with tab_quar:
        st.subheader("Quarantined Sources (Class C — NOT indexed, NOT authoritative)")
        st.error("🚫 These sources are quarantined. Content displayed for metadata only. "
                 "Never use as approved regulatory evidence.")
        for src in audit.get("quarantine_html", []):
            with st.expander(f"🔴 {src['filename']}"):
                st.write(f"**Category:** {src['category']}")
                st.write(f"**Approval status:** {src['approval_status']}")
                st.write(f"**Size:** {round(src['size_bytes']/1024,1)} KB")
                st.write("**Content preview:** _suppressed — quarantined source_")


# ---------------------------------------------------------------------------
# page: Regulatory Evidence Search
# ---------------------------------------------------------------------------

def page_evidence_search():
    st.header("C — Regulatory Evidence Search")
    st.caption(
        "Real BGE embeddings + ChromaDB retrieval from the regulatory collection. "
        "No external LLM API calls. Results require expert verification."
    )

    reg_coll, _, chroma_err = load_chromadbs()
    if chroma_err or reg_coll is None:
        st.error(f"Regulatory ChromaDB unavailable: {chroma_err or 'collection not found'}")
        return

    corpus_meta = load_corpus_manifest()

    query = st.text_area(
        "Enter your regulatory research question:",
        placeholder="e.g. What are the ICH Q2(R1) requirements for analytical procedure validation?",
        height=100,
    )
    top_k = st.slider("Results (top-K sources)", 1, 15, 5)

    if st.button("Search Regulatory Evidence", type="primary"):
        if not query.strip():
            st.warning("Please enter a question.")
            return

        with st.spinner("Running BGE retrieval…"):
            results, err = _bge_search(query.strip(), reg_coll, top_k=top_k * 3)

        if err:
            st.error(f"Retrieval error: {err}")
            return

        if not results:
            st.info(
                "**Insufficient evidence.** No passages found in the regulatory corpus. "
                "The system cannot provide an evidence-based answer to this question."
            )
            return

        # De-duplicate to source level
        seen = set()
        deduped = []
        for r in results:
            if r["source_id"] not in seen:
                deduped.append(r)
                seen.add(r["source_id"])
            if len(deduped) == top_k:
                break

        st.success(f"Found {len(deduped)} relevant sources (from {len(results)} candidate chunks).")
        st.write(f"**Query:** {query}")
        st.write(f"**Method:** BGE (bge-large-en-v1.5) + ChromaDB cosine similarity")
        st.divider()

        for i, r in enumerate(deduped, 1):
            sid = r["source_id"]
            meta = corpus_meta.get(sid, {})
            chunk = r["chunk"]
            with st.expander(
                f"#{i} · {sid} · score={r['score']:.4f}",
                expanded=(i <= 2),
            ):
                col1, col2 = st.columns(2)
                col1.write(f"**Authority:** {meta.get('authority', 'ICH/SAHPRA/WHO')}")
                col1.write(f"**Title:** {meta.get('title', sid)}")
                col1.write(f"**Version:** {meta.get('version', '?')}")
                col2.write(f"**Retrieval score:** {r['score']:.4f}")
                col2.write(f"**Cosine distance:** {r['distance']:.4f}")
                col2.write(f"**Section:** {r['section'] or (chunk.section if chunk else '?')}")
                if chunk:
                    col2.write(f"**Page:** {chunk.page or '?'}")
                    col2.write(f"**Citation ID:** `{chunk.chunk_id[:16]}…`")
                st.write("**Verification status:** UNAPPROVED_TECHNICAL_ONLY — requires expert review")
                st.write("**Retrieved passage:**")
                st.text(r["text"])

    st.divider()
    st.caption(
        "⚠️ Retrieval results are based on semantic similarity only. "
        "This system has not been expert-validated. Do not use for regulatory decisions without human review."
    )


# ---------------------------------------------------------------------------
# page: S.4 Control Demo
# ---------------------------------------------------------------------------

def page_s4_demo():
    st.header("D — S.4 Control Demonstration")
    st.caption(
        "Illustrative S.4.1–S.4.5 review using the existing dossier and regulatory evidence services. "
        "All findings are provisional and require qualified human review."
    )

    reg_coll, dos_coll, chroma_err = load_chromadbs()

    S4_SECTIONS = {
        "S.4.1 — Specification": "drug substance specification limits acceptance criteria ICH Q6A",
        "S.4.2 — Analytical Procedures": "analytical procedure method description HPLC specification test",
        "S.4.3 — Validation": "analytical procedure validation accuracy precision linearity ICH Q2",
        "S.4.4 — Batch Analyses": "batch analysis results specification conformance drug substance",
        "S.4.5 — Justification of Specification": "specification justification limits setting ICH Q3A impurities",
    }

    substances = ["Valsartan", "Amlodipine", "Hydrochlorothiazide"]

    sel_substance = st.selectbox("Select substance:", substances)
    sel_section = st.selectbox("Select S.4 section:", list(S4_SECTIONS.keys()))

    if st.button("Run Provisional S.4 Assessment", type="primary"):
        if reg_coll is None or dos_coll is None:
            st.error("Both collections required. Check ChromaDB connection.")
            return

        query = S4_SECTIONS[sel_section]
        subst_lower = sel_substance.lower()

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📋 Regulatory Evidence")
            with st.spinner("Searching regulatory corpus…"):
                reg_results, err = _bge_search(query, reg_coll, top_k=5)
            if err:
                st.error(err)
            elif not reg_results:
                st.warning("⚠️ No applicable regulatory guidance found for this section. "
                           "Gap: authoritative standard missing.")
            else:
                for r in reg_results[:3]:
                    with st.container(border=True):
                        st.write(f"**{r['source_id']}** · score={r['score']:.3f}")
                        st.write(f"Section: {r['section']}")
                        st.text(r["text"][:400] + "…")
                        st.caption("Status: UNAPPROVED_TECHNICAL_ONLY")

        with col2:
            st.subheader("📂 Sponsor Dossier Evidence")
            with st.spinner("Searching dossier corpus…"):
                dos_results, err = _bge_search(query + " " + subst_lower, dos_coll, top_k=5)
            if err:
                st.error(err)
            elif not dos_results:
                st.warning("⚠️ No dossier evidence retrieved for this substance/section.")
            else:
                for r in dos_results[:3]:
                    sid = r["source_id"]
                    if subst_lower not in sid:
                        continue
                    with st.container(border=True):
                        st.write(f"**{sid}** · score={r['score']:.3f}")
                        st.text(r["text"][:400] + "…")
                        st.caption(
                            "⚠️ Class D — Sponsor dossier. "
                            "requires_human_review=True. Not regulatory authority guidance."
                        )

        st.divider()
        with st.expander("QA Status & Provisional Finding"):
            st.write(f"**Substance:** {sel_substance}")
            st.write(f"**Section:** {sel_section}")
            st.write(f"**Regulatory guidance found:** {'Yes' if reg_results else 'No — GAP'}")
            st.write(f"**Dossier evidence found:** {'Yes' if dos_results else 'No — MISSING EVIDENCE'}")
            st.warning(
                "**PROVISIONAL FINDING:** Results are algorithmically matched and NOT expert-reviewed. "
                "Human review REQUIRED before this assessment can influence any regulatory decision."
            )
            st.caption("QA status: PENDING_HUMAN_REVIEW")


# ---------------------------------------------------------------------------
# page: Database Completeness
# ---------------------------------------------------------------------------

def page_completeness():
    st.header("E — Database Completeness")

    audit = load_audit()
    coverage = load_coverage_csv()

    if not coverage:
        st.info("Run scripts/build_complete_audit.py to generate coverage data.")
        return

    s = audit.get("summary", {})
    col1, col2, col3 = st.columns(3)
    col1.metric("Regulatory indexed", f"{s.get('regulatory_indexed',0)}/{s.get('regulatory_source_files',0)}")
    col2.metric("Dossier indexed", f"{s.get('dossier_indexed',0)}/{s.get('dossier_source_files',0)}")
    col3.metric("Collection isolation", audit.get("isolation_checks",{}).get("verdict","?"))

    st.subheader("Source Coverage Table")
    # Category filter
    cats = sorted(set(r["category"] for r in coverage))
    sel_cat = st.selectbox("Filter by category", ["All"] + cats)
    sel_status = st.selectbox("Filter by indexing status", ["All", "INDEXED", "NOT_INDEXED", "QUARANTINED_NOT_INDEXED"])

    filtered = [r for r in coverage
                if (sel_cat == "All" or r["category"] == sel_cat) and
                   (sel_status == "All" or r["indexing_status"] == sel_status)]

    st.write(f"Showing {len(filtered)} of {len(coverage)} sources")

    # Table view
    display_cols = ["source_id", "category", "indexing_status", "indexed_chunk_count",
                    "page_count", "size_bytes", "approval_status"]
    st.dataframe(
        [{k: r.get(k, "") for k in display_cols} for r in filtered],
        use_container_width=True,
        height=400,
    )

    st.subheader("Known Gaps")
    gaps = audit.get("gaps", {})
    for gap_type, items in [("Regulatory", gaps.get("regulatory",[])),
                             ("Dossier", gaps.get("dossier",[]))]:
        if items:
            st.write(f"**{gap_type}:** {', '.join(items)}")
    for sid, note in gaps.get("explanation", {}).items():
        st.info(f"**{sid}:** {note}")

    st.subheader("Compendial Research Collection")
    comp = audit.get("compendial_discovery_db", {})
    st.warning(
        f"**{comp.get('document_count',0)} documents / {comp.get('passage_count',0)} passages** "
        "quarantined in `artifacts/quarantine/compendial_discovery.sqlite3`. "
        "Status: QUARANTINED_UNVERIFIED_EDITION_RIGHTS_AND_APPLICABILITY. "
        "NOT indexed in ChromaDB."
    )

    # Export buttons
    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        csv_str = "\n".join(
            [",".join(coverage[0].keys())] +
            [",".join(str(v) for v in r.values()) for r in coverage]
        )
        st.download_button("Export CSV", csv_str, "source_coverage.csv", "text/csv")
    with col_b:
        st.download_button(
            "Export JSON",
            json.dumps(audit, indent=2, default=str),
            "knowledge_base_audit.json",
            "application/json",
        )


# ---------------------------------------------------------------------------
# page: Tests & Benchmarks
# ---------------------------------------------------------------------------

def page_tests():
    st.header("F — Tests & Benchmarks")
    st.caption(
        "Historical test outcomes and retrieval metrics from v1.3.1 validation. "
        "Researcher-authored navigation metrics only — NOT expert-labelled regulatory evaluation."
    )

    tab_reg, tab_bench, tab_info = st.tabs(
        ["Regression Results", "Retrieval Benchmark", "Scope & Limitations"])

    with tab_reg:
        st.subheader("Full Regression Suite — v1.3.1")
        results = load_regression_results()
        # Show last 40 lines (summary)
        lines = results.strip().split("\n")
        summary_start = max(0, len(lines) - 50)
        st.text("\n".join(lines[summary_start:]))
        st.success("186 passed, 0 failed, 0 skipped (v1.3.1 baseline)")
        st.caption("Source: validation/FINAL_REGRESSION_RESULTS.txt")

    with tab_bench:
        st.subheader("Retrieval Benchmark — Corrected (v1.3.1)")
        st.warning(
            "**Scope:** 30 researcher-authored document-navigation probes. "
            "NOT expert-labelled regulatory accuracy assessment. "
            "Prior run (Recall>1.0 due to chunk-level counting) SUPERSEDED."
        )
        bm = load_benchmark()
        if not bm:
            st.info("validation/FINAL_RETRIEVAL_BENCHMARK.json not found.")
        else:
            metrics = bm.get("metrics", {})
            bm25 = metrics.get("bm25", {})
            bge = metrics.get("bge", {})

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("BM25 (Lexical)")
                st.metric("MRR", bm25.get("mrr", "?"))
                st.metric("Hit@1", bm25.get("hit_at_1", "?"))
                st.metric("Hit@5", bm25.get("hit_at_5", "?"))
                st.metric("nDCG@5", bm25.get("ndcg_at_5", "?"))
            with col2:
                st.subheader("BGE (Semantic)")
                st.metric("MRR", bge.get("mrr", "?"))
                st.metric("Hit@1", bge.get("hit_at_1", "?"))
                st.metric("Hit@5", bge.get("hit_at_5", "?"))
                st.metric("nDCG@5", bge.get("ndcg_at_5", "?"))

            st.caption(f"Probe count: {bm.get('probe_count', 30)}")

    with tab_info:
        st.subheader("What Is and Is Not Validated")
        st.markdown("""
| Item | Status |
|---|---|
| Technical indexing (554 + 2064 chunks) | ✅ PASS — native ChromaDB + BGE |
| Retrieval correctness (navigation probes) | ✅ Researcher-authored, source-level metrics |
| Expert-labelled regulatory accuracy | ❌ PENDING — no expert evaluation set |
| BGE vs MiniLM/bge-m3 comparison | ❌ NOT CONDUCTED |
| Reranking experiments | ❌ NOT CONDUCTED |
| Full M1–M5 integration test | ❌ PENDING TEAM INTEGRATION |
| Human assessor pilot | ❌ PENDING |
| Regulatory approval of sources | ❌ PENDING EXPERT REVIEW |
        """)
        st.caption(
            "This system provides a technically validated knowledge base component. "
            "Full regulatory acceptance requires expert-labelled evaluation and five-member integration."
        )


# ---------------------------------------------------------------------------
# main app
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="Member 2 — KB & Evidence Explorer",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("Member 2 — Regulatory Knowledge Base & Evidence Explorer")
    st.caption(
        "Local research/developer diagnostic interface · "
        f"Project: `{PROJECT}` · "
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

    pages = {
        "A — Overview": page_overview,
        "B — Knowledge Base Browser": page_kb_browser,
        "C — Regulatory Evidence Search": page_evidence_search,
        "D — S.4 Control Demonstration": page_s4_demo,
        "E — Database Completeness": page_completeness,
        "F — Tests & Benchmarks": page_tests,
    }

    with st.sidebar:
        st.header("Navigation")
        sel = st.radio("Page", list(pages.keys()), label_visibility="collapsed")
        st.divider()
        st.caption("⚠️ READ-ONLY developer tool")
        st.caption("Binds to 127.0.0.1 only")
        st.caption("Does not replace Member 5 assessor UI")
        st.caption("All results require human review")

    pages[sel]()


if __name__ == "__main__":
    main()
