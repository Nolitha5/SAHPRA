# Member 2 · Retrieval & Knowledge Base

Agentic QA-RAG for SAHPRA CTD Module 3.2.S (drug substance). Member 2 owns the regulatory knowledge base, the shared retrieval service, and two agents: **Evidence/RERA** and **S.4 Control**.

This is a research-support tool. Every finding is cited, carries an uncertainty statement and is marked for review. The qualified human assessor makes every regulatory decision.

---

## Technology

| Part | Choice |
|---|---|
| Language | Python 3.12 / 3.13 |
| Vector database | ChromaDB 1.5.9, persistent, cosine distance |
| Embeddings | BAAI/bge-large-en-v1.5 (1024 dimensions), used by the live collection `ich_large_w300`. Configurable per collection; bge-small-en-v1.5 was tested as a lighter comparison. The status bar shows the model in use. |
| Reranker | BAAI/bge-reranker-base (cross-encoder) |
| Model runtime | sentence-transformers 6.1.0 |
| Data validation | Pydantic 2.13 |
| Web API | FastAPI 0.143 (built on Pydantic) + uvicorn |
| Tests | pytest 9.1 |
| Evaluation | Ragas 0.4.3 (non-LLM context metrics), Recall@K, Precision@K, MRR, nDCG |
| Dashboard | React 18 + Vite 5 + TypeScript |

There is no hosted database. Passages and their metadata live in ChromaDB on your computer; benchmark questions live in `member2-rag/benchmarks/benchmark.jsonl`.

---

## How the pieces connect

```
 Browser (React dashboard, :5173 in dev)
        │  /api/...  (Vite forwards to :8000)
        ▼
 FastAPI server  member2-rag/app/api/server.py   (127.0.0.1:8000 by default)
        │
        ├── Evidence/RERA agent ─┐
        ├── S.4 Control agent ───┤──► Shared retrieval service
        │                        │       embed (BGE + query prefix)
        │                        │       → ChromaDB top 20 (CTD filters)
        │                        │       → BGE reranker → top 5
        │                        ▼
        ├── Knowledge base ◄──── ChromaDB  member2-rag/data/chroma/
        │      import JSONL passages (validated by Pydantic)
        │
        └── Benchmark ─────────► benchmarks/benchmark.jsonl, results/*.json
```

The dashboard and the server-side scripts all call the **same Python code**, so they behave consistently.

---

## Dashboard tabs

| Tab | What it does | API |
|---|---|---|
| Knowledge Base | Browse passages with their source, version, page, CTD section, status and provenance. Import a JSONL file (check first, then import). Delete a passage. | `GET /api/passages`, `GET /api/passages/facets`, `POST /api/passages/import`, `DELETE /api/passages/{chunk_id}` |
| Search | Run the shared retrieval service directly and see both scores for each passage. | `POST /api/search` |
| Agents | Run Evidence/RERA or S.4 Control and read the full Finding: conclusion, rationale, uncertainty, flags, citations, comparison rows. | `POST /api/agents/evidence-rera`, `POST /api/agents/s4-control` |
| Benchmark | See the latest benchmark run and manage the expert-labelled questions. | `GET/POST /api/benchmark/cases`, `DELETE /api/benchmark/cases/{id}`, `GET /api/benchmark/results` |
| Architecture | This page. | none |

Interactive API documentation is at `/api/docs` while the server runs.

---

## Inside the Python component

| Layer | Modules | Job |
|---|---|---|
| Entry points | `app/api/`, `app/integration.py`, `scripts/` | Web API, one-call setup for Member 1, command-line tools |
| Agents | `agents/evidence_rera.py`, `agents/s4_control.py`, `agents/common.py`, `agents/spec_comparison.py` | Decide what the evidence shows, using fixed rules |
| Retrieval | `retrieval/retrieval_service.py`, `vector_search.py`, `reranker.py` | The one shared search pipeline |
| Knowledge base | `knowledge_base/indexing.py`, `document_store.py`, `metadata.py`, `embeddings/bge_embeddings.py` | Validate, embed and store passages |
| Shared | `schemas.py`, `config.py`, `logging_utils.py`, `hashing.py` | Data contracts, settings, safe logging, stable IDs |
| Evaluation | `evaluation/benchmark.py`, `metrics.py`, `ragas_eval.py`, `case_store.py` | Benchmark runs and question storage |

---

## How an agent decides

| Situation | qa_status | Conclusion starts with |
|---|---|---|
| Knowledge base empty | unsupported | Insufficient evidence |
| Nothing matched | unsupported | Insufficient evidence (absence does not prove no rule exists) |
| Retrieved, but none relevant enough | human-review | Insufficient evidence … referred for human review |
| Same document in two or more versions | conflicting | Potentially conflicting regulatory evidence |
| Only outdated, synthetic or suspicious sources | human-review | Regulatory evidence that requires human review |
| Relevant, current sources | partial | Candidate regulatory evidence retrieved |

The agents do not output a verified conclusion. Only the qualified assessor can decide final compliance.

S.4 Control refuses to compare numbers (outcome *not compared*, which forces human review) when a limit or unit is missing, when units are not safely convertible (a bare `%` is never converted to ppm), or when a result is qualitative such as "Complies" or "ND". Values within rounding distance of a limit are flagged *borderline*.

---

## Security

* The server listens on **127.0.0.1** only, so nobody else on the network can reach it unless you change `M2_API_HOST`.
* Reading is open; **every change needs the editor token** (`X-Admin-Token`). If `M2_ADMIN_TOKEN` is not set in `member2-rag/.env`, editing is switched off completely.
* The token is typed into the dashboard and kept only for that browser tab. It is never stored in the code.
* Error messages list field names only. Submitted questions and sponsor values are never echoed back or logged.
* Sponsor data sent to the S.4 agent is used for that one request and is not stored.
* `.env`, `data/chroma/`, `data/processed/`, `results/` and PDFs are git-ignored.

---

## Limitations

* Benchmark results so far are a pilot: 20 questions labelled at page level, not yet verified by a domain expert. With 20 questions, one question changes a score by 0.05.
* Relevance thresholds are starting values and must be calibrated on the benchmark.
* Conflict detection uses metadata (versions and status), not the meaning of the text.
* The editor token is a simple shared secret suitable for a local research workspace. A deployed multi-user system would need real user accounts.
