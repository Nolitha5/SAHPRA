# Member 2 — Retrieval & Knowledge Base (RAG)

**Agentic QA-RAG — SAHPRA Module 3.2.S** · Agents: **Evidence/RERA** and **S.4 Control**

> This is a research-support component. It finds and cites regulatory passages and does rule-based checks.
> It never decides that a dossier is compliant. Every finding is marked for review, and the qualified
> human SAHPRA assessor makes every final decision.

---

## 1. Project overview

The team is building a multi-agent system that helps an assessor review CTD Module 3.2.S (the drug
substance part of a medicine dossier). Member 2 owns the part that answers: *"What do the regulations and
guidelines say about this, and exactly where does it say it?"*

In one sentence: **processed passages from SAHPRA/ICH/WHO/pharmacopoeia documents go into a ChromaDB
vector database; questions are matched to passages with BGE embeddings, re-scored with a BGE reranker,
and returned as structured findings with full citations.**

## 2. My responsibilities as Member 2

| Responsibility (from the delegation sheet)          | Where it lives                                   | Status |
|------------------------------------------------------|--------------------------------------------------|--------|
| Build and load the knowledge base (ChromaDB + metadata) | `app/knowledge_base/`, `scripts/load_documents.py` | Done, tested |
| Embeddings with bge-large-en-v1.5                    | `app/embeddings/bge_embeddings.py`               | Done, tested with the real model (integration tests) |
| Reranking with bge-reranker                          | `app/retrieval/reranker.py`                      | Done, tested with the real model (integration tests) |
| One shared retrieval service for the whole team      | `app/retrieval/retrieval_service.py`             | Done, tested |
| Evidence/RERA agent (citations, "insufficient evidence") | `app/agents/evidence_rera.py`                 | Done, tested |
| S.4 Control agent (specs, limits, methods, validation, batches) | `app/agents/s4_control.py`, `spec_comparison.py` | Done, tested |
| Benchmark embeddings, chunk sizes, reranking         | `app/evaluation/`, `scripts/evaluate_retrieval.py` | Done; **pilot results** on 4 ICH guidelines with draft labels (section 13). Final results need Member 3's corpus + Member 5's expert labels |
| Ragas evaluation                                     | `app/evaluation/ragas_eval.py`                   | Done, run in the pilot (non-LLM metrics; chunk- or page-level labels) |

## 3. Architecture

```mermaid
flowchart LR
    M3["Member 3<br/>Ingestion pipeline<br/>(PDF, OCR, tables, CTD mapping, chunking)"]
    -->|"processed passages<br/>JSONL"| VAL["Validation<br/>(Pydantic PassageRecord)"]
    VAL -->|valid records| IDX["Indexing<br/>stable IDs, dedup, updates"]
    IDX -->|"embed passages<br/>bge-large-en-v1.5"| DB[("ChromaDB<br/>persistent, cosine")]

    subgraph RS["Shared Retrieval Service (one for the whole team)"]
        Q["Query + filters"] --> EMB["Embed query<br/>(+ BGE instruction)"]
        EMB --> VS["Vector search<br/>top candidate_k<br/>CTD / type / status filters"]
        VS --> RR["Cross-encoder rerank<br/>bge-reranker → top final_k"]
    end
    DB --- VS

    M1["Member 1<br/>Orchestrator"] -->|"AgentRequest"| EV["Evidence/RERA agent"]
    M1 -->|"AgentRequest"| S4["S.4 Control agent"]
    EV --> RS
    S4 --> RS
    S4 --> CMP["Rule-based numeric checks<br/>(units, limits, batches)"]
    EV -->|"Finding + citations"| M1
    S4 -->|"Finding(s)"| M1
    M1 --> M5["Member 5<br/>QA/Critic + assessor UI"]
    OTHER["Other members' agents<br/>S.1 S.2 S.3 S.5 S.6 S.7"] --> RS
```

Key rules from the team plan that this design follows:
* **One contract:** every agent returns the same `Finding` object (`app/schemas.py`).
* **Orchestrator is the hub:** my agents never call each other; they return findings to Member 1.
* **One shared retrieval service:** nobody else re-implements retrieval or opens ChromaDB directly.

## 4. Folder structure

```
member2-rag/
├── app/
│   ├── config.py                 # all settings, read from environment / .env
│   ├── schemas.py                # PassageRecord, SearchFilters, Finding, Citation, AgentRequest ...
│   ├── hashing.py                # content hashes + stable chunk IDs        (added)
│   ├── logging_utils.py          # JSON logs that never contain passage/sponsor text (added)
│   ├── integration.py            # one-call setup for Member 1               (added)
│   ├── knowledge_base/
│   │   ├── document_store.py     # ChromaDB wrapper (pinned model, upsert, query)
│   │   ├── metadata.py           # metadata <-> ChromaDB conversion + re-validation
│   │   └── indexing.py           # JSONL loading, validation, dedup, indexing
│   ├── embeddings/
│   │   └── bge_embeddings.py     # BGE wrapper + EmbeddingModel interface
│   ├── retrieval/
│   │   ├── vector_search.py      # query validation, filters, similarity search
│   │   ├── reranker.py           # BGE cross-encoder reranker
│   │   └── retrieval_service.py  # THE shared service
│   ├── agents/
│   │   ├── common.py             # shared evidence rules for both agents     (added)
│   │   ├── evidence_rera.py      # Evidence/RERA agent
│   │   ├── s4_control.py         # S.4 Control agent
│   │   └── spec_comparison.py    # numeric limits, units, batch checks      (added)
│   └── evaluation/
│       ├── metrics.py            # Recall@K, Precision@K, MRR, nDCG, latency
│       ├── benchmark.py          # benchmark format + runner
│       └── ragas_eval.py         # optional Ragas non-LLM metrics           (added)
├── data/processed/               # put Member 3's JSONL here (git-ignored)
├── data/chroma/                  # the vector database (git-ignored)
├── examples/                     # SYNTHETIC sample data + example S.4 request (added)
├── scripts/
│   ├── load_documents.py
│   ├── search.py                 # (added) try retrieval from the command line
│   ├── run_agent.py              # (added) run either agent from the command line
│   └── evaluate_retrieval.py
├── tests/                        # 160 unit tests + 2 integration tests
├── benchmarks/
│   ├── benchmark.jsonl           # template (synthetic items - replace!)
│   ├── pilot.jsonl               # 20 ICH pilot questions (page-level labels)
│   ├── pilot_sahpra.jsonl        # 18 SAHPRA pilot questions (page-level labels)
│   ├── configs.json              # the experiment arms
│   └── configs.minimal.json
├── docs/PRESENTING.md            # how to explain and defend this component (added)
├── results/                      # benchmark outputs (git-ignored)
├── requirements.txt, requirements-dev.txt, requirements-eval.txt, pytest.ini
├── .env.example, .gitignore
└── README.md
```

**Changes to the suggested structure, and why**
* `agents/common.py` — both agents must apply *identical* evidence rules, but agents may not call each
  other. Shared plain functions solve both.
* `agents/spec_comparison.py` — the numeric/unit logic is pure, safety-critical and heavily tested; it is
  easier to review on its own than buried in the agent.
* `hashing.py`, `logging_utils.py`, `integration.py`, `evaluation/ragas_eval.py`, extra scripts and
  `examples/` — small helpers that keep each file focused.
* Extra test files (`test_evaluation.py`, `test_security.py`, `test_integration_models.py`).

## 5. Prerequisites

* **Python 3.12 or 3.13** (3.10+ works with an older numpy). Check: `python --version`
* Disk: ~3 GB for the default models (bge-large ≈ 1.3 GB, bge-reranker-base ≈ 1.1 GB) plus PyTorch.
* RAM: 8 GB is enough on CPU. A GPU is optional (`M2_DEVICE=cuda`).
* Internet the **first** time, to download models from Hugging Face (they are cached afterwards).

**Low-resource laptop?** Use `BAAI/bge-small-en-v1.5` (≈130 MB, 384-dim) and/or switch the reranker
off. All unit tests run without downloading any model.

| Setup | Download | Speed on CPU | Quality |
|-------|----------|--------------|---------|
| bge-large + reranker-base (default) | ~2.4 GB | slowest | best expected |
| bge-small + reranker-base | ~1.2 GB | medium | good |
| bge-small, no reranker | ~130 MB | fastest | baseline |

## 6. Installation

### Windows PowerShell

```powershell
cd member2-rag
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
# If activation is blocked:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu   # CPU-only, smaller
pip install -r requirements.txt
pip install -r requirements-eval.txt       # optional, only for --ragas
pip install -r requirements-dev.txt        # tests and lint
copy .env.example .env
python -m pytest
python scripts/build_knowledge_base.py      # download, convert and index the 16 guidelines
```

### macOS / Linux

```bash
cd member2-rag
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu   # skip on macOS / if you have CUDA
pip install -r requirements.txt
pip install -r requirements-eval.txt       # optional
pip install -r requirements-dev.txt        # tests and lint
cp .env.example .env
python -m pytest
python scripts/build_knowledge_base.py      # download, convert and index the 16 guidelines
```

Expected: `160 passed, 2 deselected`.

**Once the models are downloaded** (after the first search), set `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1` in `.env` (see `.env.example`). Otherwise every server start checks Hugging
Face for updates, and a slow or blocked connection can make the first search hang for minutes.

## 7. Environment configuration

All settings are in `.env` (copy from `.env.example`). The important ones:

| Variable | Default | Meaning |
|---|---|---|
| `M2_CHROMA_DIR` | `data/chroma` | where the database is stored |
| `M2_COLLECTION_NAME` | `regulatory_kb` | one collection per embedding model / chunking experiment |
| `M2_EMBEDDING_MODEL` | `BAAI/bge-large-en-v1.5` | embedding model |
| `M2_RERANKER_ENABLED` | `true` | turn reranking on/off |
| `M2_RERANKER_MODEL` | `BAAI/bge-reranker-base` | or `BAAI/bge-reranker-large` |
| `M2_CANDIDATE_K` / `M2_FINAL_K` | `20` / `5` | candidates from ChromaDB / passages returned |
| `M2_MIN_RERANK_SCORE` | `0.0` | relevance gate (raw logit, **not a probability**) |
| `M2_MIN_RETRIEVAL_SCORE` | `0.55` | gate used when the reranker is off (cosine similarity) |
| `M2_DEVICE` | `cpu` | `cpu`, `cuda`, or `mps` |

A collection remembers which embedding model built it. If you change the model you must also change
`M2_COLLECTION_NAME`; otherwise you get a clear `EmbeddingModelMismatchError` instead of silently wrong
results.

The two `MIN_*` thresholds are **starting guesses**. Calibrate them on the expert benchmark before
reporting anything.

## 8. Loading processed passages

Member 3 delivers one JSON object per line. Required fields: `text`, `source_title`,
`issuing_organization`, `source_identifier`, `document_type`. Everything else is optional but strongly
recommended; missing values are stored as *missing* (never guessed) and flagged in citations.

```json
{"chunk_id": "ich-q6a-p12-c3", "text": "...passage text...", "source_title": "...",
 "issuing_organization": "ICH", "source_identifier": "<official URL or document code>",
 "document_version": "...", "publication_date": "YYYY-MM-DD", "effective_date": null,
 "page_number": 12, "ctd_section": "3.2.S.4.1", "document_type": "guideline",
 "applicability_status": "current", "chunk_index": 3, "chunk_size": 512, "chunk_overlap": 64,
 "content_hash": "<optional sha256; checked if given>", "language": "en"}
```

* `document_type`: guideline, guidance, regulation, act, monograph, general_chapter, template, q_and_a, other, synthetic_test
* `applicability_status`: current, superseded, draft, withdrawn, unknown
* Dates: `YYYY`, `YYYY-MM` or `YYYY-MM-DD` (partial dates allowed so nobody has to invent a day)
* No `chunk_id`? A stable one is generated: from position (source+version+page+chunk_index) if known, so
  corrected text updates the same record; otherwise from the content hash.

```powershell
# 1. Validate only (no model download, no writes)
python scripts/load_documents.py --input data/processed/passages.jsonl --dry-run
# 2. Load
python scripts/load_documents.py --input data/processed/passages.jsonl
# 3. Refuse to load anything if a single line is bad
python scripts/load_documents.py --input data/processed/passages.jsonl --strict
```

Example output:

```json
{"lines_read": 8, "valid_records": 8, "rejected": 0, "rejected_details": [],
 "skipped_duplicates": 0, "added": 8, "updated": 0, "unchanged": 0,
 "total_in_collection": 8, "collection": "regulatory_kb"}
```

Running the same file again gives `"unchanged": 8` and does not re-embed anything. Exit code `2` means
some lines were rejected (each with line number and field name, never the passage text).

**Try it with synthetic data:** `examples/synthetic_passages.jsonl` contains 8 clearly labelled
*SYNTHETIC PLACEHOLDER* passages (organisation `TEST`, type `synthetic_test`). They exist only to exercise
the pipeline; agents automatically flag them as "not real evidence".

## 9. Running retrieval

```powershell
python scripts/search.py "What should a drug substance specification include?" --section 3.2.S.4.1
python scripts/search.py "analytical method validation" --no-rerank --final-k 3 --current-only
```

In Python:

```python
from app.retrieval.retrieval_service import build_retrieval_service
from app.schemas import SearchFilters

service = build_retrieval_service()
result = service.retrieve("validation of an assay procedure",
                          filters=SearchFilters(ctd_sections=["3.2.S.4.3"]))
for p in result.passages:
    print(p.chunk_id, p.retrieval_score, p.rerank_score, p.metadata.source_title, p.metadata.page_number)
```

**CTD filtering is hierarchical:** `3.2.S.4` matches 3.2.S.4.1–3.2.S.4.5; by default parent headings
(e.g. a general passage tagged `3.2.S`, or the module heading `3.2`) are also included. Use `include_parent_sections=False` to switch that off.

Every passage keeps `retrieval_score` (cosine similarity) **and** `rerank_score` (cross-encoder logit) separately.

## 10. Evidence/RERA agent

```python
from app.integration import create_member2_components
from app.schemas import AgentRequest

m2 = create_member2_components()
findings = m2.agents["evidence_rera"].run(AgentRequest(
    ctd_section="3.2.S.4.3",
    assessment_question="What characteristics are assessed when validating an analytical procedure?"))
```

or `python scripts/run_agent.py evidence --section 3.2.S.4.3 --question "..."`

How it decides (rule-based, so it cannot invent anything):

| Situation | `evidence_status` | `qa_status` | Conclusion starts with |
|---|---|---|---|
| Knowledge base empty | `empty_knowledge_base` | `unsupported` | "Insufficient evidence" |
| Nothing matched | `no_passages_retrieved` | `unsupported` | "Insufficient evidence" (+ "absence does not prove…") |
| Retrieved, but all below the relevance gate | `retrieved_not_relevant` | `human-review` | "Insufficient evidence … Referred for human review" |
| Same document in 2+ versions | `candidate_evidence_found` | `conflicting` | "Potentially conflicting…" |
| Only superseded/withdrawn sources, synthetic data, or instruction-like text | `candidate_evidence_found` | `human-review` | "…requires human review" |
| Relevant, current sources | `candidate_evidence_found` | `partial` | "Candidate regulatory evidence retrieved" |

My agents **never** output `verified` — only Member 5's QA/Critic and the assessor can.

Real output (synthetic data, test embedder; trimmed):

```json
{
  "agent_name": "evidence_rera",
  "ctd_section": "3.2.S.4.3",
  "assessment_question": "What characteristics are assessed when validating an analytical procedure?",
  "regulatory_evidence": [
    {"chunk_id": "syn-a-p3-c0", "retrieval_score": 0.290957, "rerank_score": 1.5, "rerank_rank": 1,
     "metadata": {"source_title": "Synthetic Guideline Alpha", "document_version": "2.0", "page_number": 3,
                  "applicability_status": "current"}},
    {"chunk_id": "syn-a1-p3-c0", "retrieval_score": 0.196116, "rerank_score": 0.5, "rerank_rank": 2,
     "metadata": {"source_title": "Synthetic Guideline Alpha", "document_version": "1.0", "page_number": 3,
                  "applicability_status": "superseded"}}
  ],
  "citations": [{"chunk_id": "syn-a-p3-c0", "issuing_organization": "TEST", "source_identifier": "SYNTH-ALPHA",
                 "document_version": "2.0", "publication_date": "2024-01-15", "page_number": 3,
                 "content_hash": "17bff6c7…", "provenance_complete": true, "missing_provenance": []}],
  "conclusion": "Potentially conflicting regulatory evidence retrieved: 2 passage(s) for assessor review. This is not a compliance determination.",
  "uncertainty": "At least one source is marked superseded or withdrawn. Some passages are SYNTHETIC TEST DATA and are not regulatory evidence. The same document appears in more than one version. Versions found for TEST: Synthetic Guideline Alpha: 1.0, 2.0. …",
  "qa_status": "conflicting",
  "evidence_status": "candidate_evidence_found",
  "requires_human_review": true,
  "metadata": {"flags": ["contains_superseded_or_withdrawn_source", "synthetic_test_data_not_real_evidence",
                         "multiple_versions_of_same_document"],
               "retrieval": {"knowledge_base_size": 8, "reranked": true, "latency_ms": 4.84}}
}
```

## 11. S.4 Control agent

Topics → CTD headings: `specification` 3.2.S.4.1, `analytical_procedures` 3.2.S.4.2,
`method_validation` 3.2.S.4.3, `batch_analyses` 3.2.S.4.4, `justification_of_specification` 3.2.S.4.5,
`general` 3.2.S.4.

```powershell
python scripts/run_agent.py s4 --topic specification --question "Which tests should the specification contain?"
python scripts/run_agent.py s4 --request examples/s4_request.example.json
```

What it returns (a list of findings):
1. **Evidence finding** for the topic — same rules as Evidence/RERA, same shared retrieval service.
2. **Batch-vs-specification finding** (if `batch_results` supplied): are batch values inside the
   *sponsor's own* stated limits? This checks internal consistency only.
3. **Specification-vs-regulatory-limit finding** (if `regulatory_limits` supplied): is the sponsor's
   limit at least as strict as a limit that a person entered in structured form **with a `citation_chunk_id`
   that exists in the knowledge base**. Limits are never extracted or invented by the agent.

The comparison refuses (`not_compared` → `human-review`) when:
* the criterion or a unit is missing, or units are not safely convertible — a bare `%` is never converted
  (w/w? area %? label claim?); only explicit mass-fraction units (`% w/w`, ppm, ppb, mg/g, µg/g, mg/kg) are;
* the result is qualitative (`Complies`), `ND`/`BLQ` without a number, uses a comma decimal, or a `<x`
  value cannot be placed relative to the limits;
* two criteria share a test name (ambiguous).

Results within half a unit of the limit's last decimal are flagged **borderline** (rounding conventions
may change the outcome). Example from `examples/s4_request.example.json`: Assay 101.96 vs 98.0–102.0 % w/w
→ within, but borderline.

Sponsor values are stored under `metadata.confidential_comparison_rows` and removed by
`finding.model_dump_redacted()`.

**Future work (not implemented):** automatic reading of specification tables (needs Member 3's table
output), automatic extraction of limits from guideline text (needs expert-validated parsing),
method-validation completeness checklist, batch trend statistics.

## 12. Running tests

```powershell
python -m pytest                 # 160 unit tests, no downloads, temp databases only
python -m pytest -m integration  # 2 tests with REAL models (downloads bge-small + bge-reranker-base)
python -m pytest -v tests/test_s4_control.py
python -m ruff check             # lint (pip install -r requirements-dev.txt once; config in ruff.toml)
```

Unit tests use a fake embedder/reranker and a separate temporary ChromaDB folder per test, so they never
touch `data/chroma`.

## 13. Running benchmarks

1. Member 5 (domain lead) writes expert questions in `benchmarks/benchmark.jsonl`:
   ```json
   {"question_id": "Q001", "question": "...", "ctd_section": "3.2.S.4.3",
    "relevant_chunk_ids": ["..."], "relevant_pages": [{"source_identifier": "...", "page_number": 12}],
    "reference_answer": null, "expert_notes": "...", "labelled_by": "..."}
   ```
   The shipped file contains 3 **synthetic** smoke-test items only — replace them.
2. Load one collection per experiment arm (e.g. `regulatory_kb` with bge-large, `regulatory_kb_small`
   with bge-small, `regulatory_kb_c256` / `_c512` built from Member 3's output at different chunk sizes).
3. Edit `benchmarks/configs.json` (one entry per arm) and run:

```powershell
python scripts/evaluate_retrieval.py --benchmark benchmarks/benchmark.jsonl --configs benchmarks/configs.json
python scripts/evaluate_retrieval.py --benchmark benchmarks/benchmark.jsonl --configs benchmarks/configs.json --ragas
```

The shipped `configs.json` covers all five comparisons: dense only vs reranked, filter on vs off,
bge-large vs bge-small, chunk 256 vs 512 (page-level labels).

Output: `results/retrieval_benchmark_<UTC time>.json` with every setting, package versions, the benchmark
file's SHA-256, KB size, per-query results and these metrics: Recall@K, Precision@K, Hit@K, nDCG@K, MRR,
latency (mean/p50/p95/max, after a warm-up query), plus Ragas `non_llm_context_recall` and
`non_llm_context_precision_with_reference` with `--ragas`.

**Why page-level labels?** Chunk IDs change when the chunk size changes, so chunk labels from one chunking
cannot judge another. "Page 12 of ICH Q2 answers this" stays true for any chunking — that makes the
chunk-size comparison fair.

**Data leakage / label checks** run automatically and are written into the report: labelled chunk IDs
missing from the index, and questions that appear word-for-word inside indexed passages.

**Ragas metrics and what they need:**

| Metric | Needs | Used here |
|---|---|---|
| NonLLMContextRecall / NonLLMContextPrecisionWithReference | retrieved contexts + reference contexts (expert-labelled chunks) | ✅ yes, no LLM or API key |
| LLMContextRecall / LLMContextPrecisionWithReference | + reference answer, + an LLM judge | ❌ Member 4's harness |
| Faithfulness, ResponseRelevancy | + a generated response | ❌ my agents do not generate free text |

### Pilot results (2026-10-19)

These are **pilot results**, not the project's final evaluation: 4 public ICH guidelines (Q6A, Q2(R2),
Q3A(R2), Q11) converted by the temporary converter, and 20 questions (`benchmarks/pilot.jsonl`) labelled
at page level by Member 2 with AI assistance, checked against the page text but **not expert-verified**.

Setup: CPU only, `candidate_k=20`, `final_k=10`, reranker `BAAI/bge-reranker-base`, page-level relevance,
benchmark SHA-256 `e330d323b971…`. Command:
`python scripts/evaluate_retrieval.py --benchmark benchmarks/pilot.jsonl --configs benchmarks/configs.pilot.json --ragas`

| Configuration | Hit@1 | Recall@5 | Recall@10 | MRR | nDCG@10 | p50 latency | Ragas ctx recall | Ragas ctx precision |
|---|---|---|---|---|---|---|---|---|
| bge-large, 300 words, dense only | 0.80 | 0.95 | 0.95 | 0.88 | 0.883 | 0.1 s | 0.787 | 0.803 |
| **bge-large, 300 words, reranked** (main) | 0.80 | 0.93 | 0.95 | 0.88 | 0.876 | 5.9 s | 0.800 | 0.788 |
| bge-large, 300 words, reranked, no CTD filter | 0.80 | 0.95 | 1.00 | 0.90 | 0.904 | 5.4 s | 0.812 | 0.821 |
| bge-large, 150 words, reranked | 0.70 | 0.90 | 0.95 | 0.80 | 0.830 | 3.6 s | 0.580 | 0.674 |
| bge-small, 300 words, dense only | 0.85 | 0.90 | 0.95 | 0.87 | 0.875 | 0.03 s | 0.750 | 0.789 |
| bge-small, 300 words, reranked | 0.80 | 0.93 | 0.95 | 0.88 | 0.874 | 4.8 s | 0.787 | 0.780 |
| bge-small, 150 words, reranked | 0.70 | 0.90 | 0.95 | 0.80 | 0.827 | 2.6 s | 0.560 | 0.677 |

What can and cannot be concluded:

* **With 20 questions, one question changes a score by 0.05.** Most differences above are within one or two
  questions, so no configuration is shown to be better. A larger, expert-labelled set is needed.
* Every configuration found a labelled page in the top 10 for 19 or 20 of 20 questions.
* **Reranking** did not measurably improve ranking on this set, and adds about 5 seconds per query on CPU.
* **150-word chunks** ranked the first relevant page lower (MRR 0.80 vs 0.88). Their lower Ragas recall is
  partly an artefact: each labelled page is split into more chunks, all of which count as references.
* **CTD filter:** the one question missed with the filter (P008, impurity listing in a specification, asked
  for 3.2.S.4.1) is on ICH Q3A, which is tagged 3.2.S.3, so the filter excluded it. See Limitations.
* Data-leakage checks: no question appears word-for-word in the index; no labels point to missing passages.

**Re-run with SAHPRA guidelines added (2026-10-28).** Two public SAHPRA guidelines (Quality and
Bioequivalence, SAHPGL-PEM-02 v8; API Master File procedure, SAHPGL-PEM-03 v3) were added to the
bge-large 300-word collection (82 passages, 248 in total). The three bge-large 300-word configurations
were re-run with `benchmarks/configs.pilot_sahpra.json`: every score was identical to the table above,
so the extra passages did not displace the labelled ICH pages. The pilot questions are about ICH pages
only; SAHPRA-specific questions are evaluated separately below.

### SAHPRA pilot results (2026-11-03)

18 questions about the two SAHPRA guidelines (`benchmarks/pilot_sahpra.jsonl`): 12 on Module 3.2.S topics
(APIMF procedure, CEP / WHO-prequalified APIs, multiple API manufacturers, specification and stability
requirements) and 6 on SAHPRA review pathways. Labelled at page level by Member 2 with AI assistance,
checked against the page text, **not expert-verified**. Same collection (248 passages) and settings as above.
Command: `python scripts/evaluate_retrieval.py --benchmark benchmarks/pilot_sahpra.jsonl --configs benchmarks/configs.pilot_sahpra.json --ragas`

| Configuration | Hit@1 | Recall@5 | Recall@10 | MRR | nDCG@10 | p50 latency | Ragas ctx recall | Ragas ctx precision |
|---|---|---|---|---|---|---|---|---|
| bge-large, 300 words, dense only | 0.50 | 0.62 | 0.62 | 0.57 | 0.553 | 0.15 s | 0.528 | 0.533 |
| **bge-large, 300 words, reranked** (main) | 0.50 | 0.62 | 0.64 | 0.55 | 0.546 | 5.8 s | 0.500 | 0.498 |
| bge-large, 300 words, reranked, no CTD filter | 0.67 | 0.93 | 1.00 | 0.77 | 0.816 | 6.3 s | 0.708 | 0.717 |

What this shows:

* **Without the CTD filter every SAHPRA question found its page in the top 10**, and 12 of 18 at rank 1.
* **With the filter, 6 of 18 questions (S010–S015) cannot find their page at all.** The cause is coarse
  section tagging, not the search itself: most Quality and Bioequivalence pages carry the broad tag `3.2`,
  so a question filtered to `3.2.S.4.1` or `3.2.S.7` excludes them; page 17 covers both the specification
  (3.2.S.4.1) and stability (3.2.S.7) rules but carries only one tag. This is the same limitation as P008
  in the ICH pilot, and it is much larger on SAHPRA documents because they are organised by procedure
  rather than by CTD section.
* The tags were **not** changed to improve these scores.

**Filter fix and re-run (2026-11-06).** Investigating the misses above showed a bug in the parent-section
logic: `include_parent_sections` (on by default) added `3.2.S.4` and `3.2.S` but stopped before the module
heading `3.2`, so the 54 passages tagged `3.2` were never reachable through a 3.2.S filter. `ctd_ancestors()`
now includes the module heading (tests in `tests/test_retrieval.py`). No tags or questions were changed.
Re-run with the same command, collection and settings:

| Configuration | Hit@1 | Recall@5 | Recall@10 | MRR | nDCG@10 | p50 latency | Ragas ctx recall | Ragas ctx precision |
|---|---|---|---|---|---|---|---|---|
| bge-large, 300 words, dense only | 0.56 | 0.90 | 0.90 | 0.72 | 0.735 | 0.16 s | 0.722 | 0.661 |
| **bge-large, 300 words, reranked** (main) | 0.67 | 0.84 | 0.92 | 0.75 | 0.767 | 6.4 s | 0.639 | 0.701 |
| bge-large, 300 words, reranked, no CTD filter | 0.67 | 0.93 | 1.00 | 0.77 | 0.816 | 6.8 s | 0.708 | 0.717 |

* With the filter, 17 of 18 SAHPRA questions now find their page in the top 10 (was 12 of 18).
* The one remaining miss (S010, asked under 3.2.S.7) is on page 17, which covers both 3.2.S.4.1 and
  3.2.S.7 but can carry only one tag — the "one CTD section per passage" limitation (section 15).
* The ICH pilot was re-run with the fix: **every score was identical** to the earlier table.
* Caveat: the fix was found by looking at these 18 questions. Confirm it on new SAHPRA questions that
  were not used to find it before treating the improvement as final.

The full per-question output is in `results/retrieval_benchmark_<UTC time>.json` (git-ignored; regenerate
with the command above).

## 14. Integrating with the team

### For Member 1 (Orchestrator)

```python
from app.integration import create_member2_components
from app.schemas import AgentRequest, Finding

m2 = create_member2_components()                  # cheap; models load on first query
evidence_agent = m2.agents["evidence_rera"]      # .run(AgentRequest) -> list[Finding]
s4_agent       = m2.agents["s4_control"]          # .run(AgentRequest) -> list[Finding]
shared_retrieval = m2.retrieval                   # .retrieve(query, filters, candidate_k, final_k, use_reranker)
```

* `AgentRequest`: `task_id`, `ctd_section`, `assessment_question`, `sponsor_evidence`, `filters`, `parameters`.
* `Finding` fields: `schema_version, finding_id, agent_name, ctd_section, assessment_question,
  sponsor_evidence, regulatory_evidence, citations, conclusion, rationale, uncertainty, qa_status,
  evidence_status, requires_human_review, metadata, created_at`.
* Use `finding.model_dump(mode="json")` inside the secure app, `finding.model_dump_redacted()` for logs/exports.
* If an LLM ever reads retrieved text, pass it through `format_evidence_for_prompt()` — it wraps passages
  as escaped, clearly-labelled **untrusted data**.

### Integration checklist

**Member 1 — Orchestration**
- [ ] Agree the `Finding` field names in `app/schemas.py` (lock before Tier 0 skeleton)
- [ ] Route 3.2.S.4.x tasks to `s4_control`, evidence questions to `evidence_rera`
- [ ] Create components once at start-up and inject `m2.retrieval` into other agents
- [ ] Handle `InvalidQueryError` / `ValueError` from `run()` (bad question/section/parameters)

**Member 3 — Ingestion**
- [ ] Output JSONL matching `PassageRecord` (section 8); run `load_documents.py --dry-run` on it
- [ ] Provide `page_number`, `document_version`, dates and `applicability_status` wherever possible
- [ ] Keep `chunk_id` stable between runs (or supply `page_number` + `chunk_index`)
- [ ] Produce the same documents at 2+ chunk sizes for the chunking experiment
- [ ] Later: S.4.1 / S.4.4 tables → `AcceptanceCriterion` / `BatchResult` objects

**Member 4 — Memory & Evaluation**
- [ ] Read `results/retrieval_benchmark_*.json` into MLflow (all settings are inside)
- [ ] Baseline B (plain RAG) = config with `use_reranker=false`; baseline C uses the full pipeline
- [ ] End-to-end LLM-based Ragas metrics belong to the shared harness

**Member 5 — QA/Critic, UI, domain**
- [ ] Use `citations`, `flags`, `version_conflicts`, `below_threshold_candidates` in the Critic checks
- [ ] Only the Critic/assessor may raise a finding to `verified`
- [ ] Show `uncertainty` and `missing_provenance` prominently in the UI
- [ ] Write expert benchmark questions with chunk- and page-level labels; keep them out of the indexed corpus
- [ ] Review the default relevance thresholds after the first benchmark run

## 14a. Knowledge base v2 (aziz-and-sipho source list)

The knowledge base was rebuilt from the regulatory source list of the team's `aziz-and-sipho` branch
(github.com/Nolitha5/SAHPRA): 15 public ICH, WHO and SAHPRA guidelines, downloaded from the official
URLs, plus SAHPGL-PEM-03 (APIMF), which that list does not include. SAHPGL-PEM-02 **v9** (23 October 2025)
replaces v8, and SAHPGL-PEM-03 **v4** (17 July 2024) replaces v3, which SAHPRA now marks "archived (do not
use)". Their sponsor dossiers (confidential) and quarantined pharmacopoeial material were not used.

| | |
|---|---|
| Source list (committed) | `sources/kb_v2_manifest.json`: title, version, date, CTD tag and official URL of every PDF |
| PDFs (git-ignored) | `data/raw/kb_v2/` (downloaded by the build script) |
| Passages | `data/processed/kb_v2_w300.jsonl`: 761 passages, 300-word chunks, 50-word overlap |
| Collection | `kb_v2_large_w300` (bge-large-en-v1.5), the only knowledge base; the earlier pilot collections were removed |

Build (or rebuild) in one command; it downloads any missing PDF from its official URL, converts and
indexes them into the collection named in `.env` (`M2_COLLECTION_NAME=kb_v2_large_w300`):

```powershell
python scripts/build_knowledge_base.py                  # download + convert + index
python scripts/build_knowledge_base.py --download-only  # just fetch the PDFs
```

To add or replace a guideline, edit `sources/kb_v2_manifest.json` (copy the title, version and date from
the document itself) and run the script again.

CTD tags are one per document, chosen from each guideline's scope (e.g. Q1A/Q1B/WHO TRS 1010 Annex 10 →
3.2.S.7, Q14 → 3.2.S.4.2, Q7 → 3.2.S.2, M4Q → 3.2, Q8(R2) → 3.2.P.2). PEM-02 v9 page 18 (specification
and stability requirements) is tagged 3.2.S.4.1, mirroring v8 page 17.

**Benchmarks on v2.** Four documents are now different editions (PEM-02 v9, PEM-03 v4, the EMA print of
Q6A, the 35-page Q2(R2)), so their page labels moved. `scripts/remap_benchmark_pages.py` carries each
labelled page to the page of the new edition with the most shared 5-word phrases and writes **new** files
(`benchmarks/pilot_kb_v2.jsonl`, `benchmarks/pilot_sahpra_kb_v2.jsonl`); the original files are unchanged.
Every low-confidence match was checked against the text by hand (S009/S010 corrected to v9 p. 18). PEM-03 v4
is largely rewritten, so all eight PEM-03 questions (S001–S008) were relabelled by reading the v4 text.
One rule changed: v3 required the APIMF to reach SAHPRA not more than one month before and not later than
one week after the application; v4 (§3.1.2) only says it must be submitted *before* the application (S004).
Which files are current is explained in `benchmarks/README.md`. Configs: `benchmarks/configs.kb_v2.json`.

Results on KB v2 (2026-11-09; 761 passages incl. PEM-03 v4, `candidate_k=20`, `final_k=10`, same draft
labels, remapped and checked):

| Benchmark · configuration | Hit@1 | Recall@5 | Recall@10 | MRR | nDCG@10 | p50 latency |
|---|---|---|---|---|---|---|
| ICH pilot · dense only | 0.60 | 0.83 | 0.90 | 0.71 | 0.735 | 0.2 s |
| ICH pilot · **reranked** (main) | 0.60 | 0.75 | 0.90 | 0.70 | 0.737 | 6.7 s |
| ICH pilot · reranked, no CTD filter | 0.50 | 0.75 | 0.93 | 0.68 | 0.713 | 6.5 s |
| SAHPRA pilot · dense only | 0.33 | 0.68 | 0.90 | 0.53 | 0.593 | 0.2 s |
| SAHPRA pilot · **reranked** (main) | 0.56 | 0.91 | 0.94 | 0.72 | 0.752 | 5.6 s |
| SAHPRA pilot · reranked, no CTD filter | 0.61 | 0.94 | 1.00 | 0.78 | 0.815 | 5.5 s |

* **SAHPRA** questions held up with three times as many passages (main config Recall@10 0.92 → 0.94). With
  PEM-03 v4 the reranker matters more for SAHPRA: without it, the first relevant page ranks lower
  (dense-only Hit@1 0.33). The per-query results show the competition is inside PEM-03 v4 itself: v4 repeats
  near-identical document lists for new registrations, existing records and variations (pp. 11, 12, 15), so
  a neighbouring PEM-03 page is often ranked first (S003, S004, S005, S008).
* **ICH** ranking dropped (main config Hit@1 0.80 → 0.60, MRR 0.88 → 0.70). Five of the seven questions that
  ranked lower are on Q6A. Two causes, from the per-query results: (1) the EMA print of Q6A breaks pages in
  different places, so an answer that was on one page now often continues on the next, and the retriever
  ranks the neighbouring page first (e.g. P012: enantiomer text on pp. 10–11, p. 11 ranked first), which the
  single-page labels count as a miss; (2) genuinely competing new sources, mainly ICH Q6B (the biotech
  counterpart of Q6A) and the Q11 Q&A. The labels were **not** widened after seeing these results; an
  expert should decide which pages answer each question in the new editions.

**Coverage overview.** `GET /api/coverage` (shown at the top of the dashboard's Knowledge Base tab) lists every indexed source with
passage and page counts, flags sources in the manifest that are not indexed, and shows for each CTD 3.2.S
heading how many passages are tagged with it and how many a filtered search can reach through parent
headings. Metadata only; no passage text. Code: `app/knowledge_base/coverage.py`, tests: `tests/test_coverage.py`.

## 15. Limitations and future improvements

* **Public guidelines only.** Knowledge base v2 holds 16 public ICH, WHO and SAHPRA guidelines (section
  14a), converted by the temporary PDF converter. Pharmacopoeial and sponsor material is not included
  (pharmacopoeias are usually not freely redistributable; dossiers are confidential).
  Image-only pages (e.g. the Q6A decision trees) have no text until OCR is added.
* **Pilot labels are drafts.** The 20 pilot questions were labelled at page level by Member 2 with AI
  assistance and checked against the page text, but not by a domain expert.
* **One CTD section per passage.** A passage carries a single `ctd_section`. A guideline tagged with one
  section (e.g. ICH Q3A as 3.2.S.3) is hidden by a filter for another section where it is also relevant
  (Q3A's impurity-listing rules matter for 3.2.S.4.1). The pilots show this (questions P008 and S010). Mitigations:
  per-page tags in the converter manifest (`page_sections`), searching without the filter, or multi-section
  tags from Member 3.
* **CPU latency.** With the reranker, a query takes several seconds on CPU (section 13). A GPU
  (`M2_DEVICE=cuda`) or a smaller `M2_CANDIDATE_K` reduces this.
* Relevance thresholds are uncalibrated heuristics.
* Conflict detection uses **metadata only** (same document, different versions). Detecting two *different*
  documents that disagree in content needs NLP (e.g. an NLI model) — future work with Member 5.
* Conclusions describe what was retrieved; they do not summarise or interpret regulatory text.
* BGE models read at most 512 tokens; longer chunks are truncated by the model.
* English only (bge-*-en). Multilingual sources would need e.g. bge-m3 (no query instruction).
* Numeric comparison does not apply pharmacopoeial rounding rules; it flags borderline values instead.



## Before Member 3's data: pilot on public ICH guidelines

`scripts/pdf_to_jsonl.py` is a temporary stand-in for Member 3's pipeline. It converts text-based PDFs (for example ICH Q6A, Q2(R2), Q3A(R2), Q11) into the same JSONL format, with page numbers kept and running headers removed. Source details come from a manifest you fill in from each document's cover page; placeholders are refused. Step-by-step guide: **`docs/ICH_PILOT.md`**. Pilot benchmark configs: `benchmarks/configs.pilot.json`.

## Web API and dashboard

`app/api/server.py` exposes this component over HTTP for the React dashboard in the parent folder (and for any teammate who prefers HTTP to importing Python).

```powershell
python -m app.api        # http://127.0.0.1:8000, interactive docs at /api/docs
```

| Method | Path | Purpose | Needs editor token |
|---|---|---|---|
| GET | `/api/health` | KB size, models, whether editing is on | no |
| GET | `/api/passages` | Page through passages (filters: `ctd_section`, `organization`, `document_type`) | no |
| GET | `/api/passages/facets` | Counts per organisation, section, type, status | no |
| POST | `/api/passages/import` | Validate (`dry_run`) or index JSONL content | **yes** |
| DELETE | `/api/passages/{chunk_id}` | Remove one passage | **yes** |
| POST | `/api/search` | Shared retrieval service | no |
| POST | `/api/agents/evidence-rera` | Evidence/RERA (`AgentRequest` → `Finding[]`) | no |
| POST | `/api/agents/s4-control` | S.4 Control (`AgentRequest` → `Finding[]`) | no |
| POST | `/api/ask` | Just a question: searches everything once, picks the CTD section and agent from the best passages (`app/routing.py`), returns `{route, findings}` | no |
| GET/POST | `/api/benchmark/cases` | List / add benchmark questions | POST: **yes** |
| DELETE | `/api/benchmark/cases/{id}` | Remove a benchmark question | **yes** |
| GET | `/api/benchmark/results` | Summaries of `results/retrieval_benchmark_*.json` | no |

Security: listens on `127.0.0.1` by default; editing is off unless `M2_ADMIN_TOKEN` is set; validation errors list field names only (FastAPI's default would echo submitted values); model calls run one at a time. Tests: `tests/test_api.py`.

## 16. Data security and responsible regulatory use

* **Never commit** `.env`, `data/chroma`, `data/processed`, PDFs, sponsor dossiers or `results/` — the
  `.gitignore` blocks them.
* Logs are JSON and contain only IDs, counts, timings and a 12-character fingerprint of the question —
  never passage text, questions or sponsor content (tested in `tests/test_security.py`).
* Sponsor evidence is kept separate from regulatory evidence, hidden from `repr()`, and removed by
  `model_dump_redacted()`. Validation errors report field names, not values.
* Retrieved passages are treated as **untrusted data**: instruction-like text is flagged, and the prompt
  formatter escapes and labels it.
* Citations are built only from stored, re-validated metadata; the `Finding` model rejects any citation
  that does not match a returned passage.
* Scores mean "similar/relevant", not "correct" or "compliant". No finding from Member 2 is ever `verified`.
* **The qualified human assessor makes every regulatory decision.**

## Design decisions (short)

* **No LangChain / LlamaIndex.** The pipeline is three direct calls. A framework would add a large
  dependency tree and hide the exact query instruction, normalisation and score handling, which matter for
  explaining and defending the results.
* **ChromaDB with our own vectors** (`embedding_function=None`) so the embedding model is explicit,
  swappable and pinned per collection.
* **Raw reranker logits** (activation set to Identity explicitly) so scores are not mistaken for probabilities.
* **Deterministic agents.** No LLM writes conclusions in Member 2's component, which removes the risk of
  invented requirements or citations at this layer.
