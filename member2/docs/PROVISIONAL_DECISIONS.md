# Provisional decision register — must be ratified by team

All decisions below are reversible. They are provisional implementations needed to continue without blocking on a meeting. The original source documents are authoritative when the team chooses differently.

| ID | Decision implemented now | Basis and alternative | Responsible owners | Change point |
|---|---|---|---|---|
| D01 | Python package and shared Pydantic v2 models | M1 spec requests FastAPI/LangGraph/Pydantic, team rules require one interface | M1, M2 | Before team integration |
| D02 | ChromaDB for real local vector storage | M2 preferred. Qdrant is an alternative for study | M2 | Before large indexing |
| D03 | Regulatory and sponsor content are **different types** | Limits mistaken sponsor-as-law retrieval; optional case-specific indices require access policy | M1/M2/M3/M4 | Before M3 handoff |
| D04 | M3 owns OCR/section mapping, M2 owns regulatory index/chunk experiments | Prevent duplicate ingestion; both specs partly overlap | M2/M3 | Before final chunk schema |
| D05 | RERA as direct callable Python service, optional internal REST | Meets "one shared service" without exposing Chroma client | M1/M2 | Tier 0 integration |
| D21 | Native Python retrieval as baseline, optional LangChain Document adapter | The M2 spec permits LangChain or LlamaIndex; shared service remains framework independent | M1/M2 | Framework integration review |
| D06 | Dense + BM25 weighted reciprocal rank fusion; optional BGE reranker | Hybrid design phase requests hybrid; M2 spec requires reranking | M2/M4/M5 | On expert retrieval results |
| D07 | Chunks start at 512/128; compare 256/512/1024 and 64/128 overlap using fixed actual tokenizer | Document baseline + experimental comparison | M2/M3/M4 | Research benchmark |
| D08 | `bge-large-en-v1.5` preferred initial REAL embedding; BGE-M3/MiniLM alternatives | M2 personal spec | M2 | Following benchmarks |
| D09 | Ollama `llama3.1:8b` optional; M1 owns actual shared inference runtime | M1/M5 name 3.1; older materials mention 3.2 8B inconsistently | M1/M2/M5 | Model freeze |
| D10 | S.4 workflow checks subsections 3.2.S.4.1–3.2.S.4.5 | Standard section taxonomy and M2 job; rule-level checklist needs M5 signoff | M2/M5 | Before regulatory evaluation |
| D11 | All S.4 outputs are provisional and QA pending | Human final judgement is mandatory | M1/M2/M5 | Should not be weakened |
| D12 | Effective-on date filter fails closed if source date unknown | M5 S.5 historic monograph edition requirement | M2/M5 | After source verification |
| D13 | `QAStatus` separate from evidence sufficiency; no automatic approval | Reconciling M5 QA statuses vs older architecture terminology | M1/M5 | Shared schema freeze |
| D14 | RERA results use exact passages and provenance, never LLM source memory | M2 golden rule | M2 | Should not be weakened |
| D15 | Demo hash embedding + synthetic corpus disallowed in `research` mode | Safe reproducible engineering fixtures only | All | Should not be weakened |
| D16 | Experiment labels anchored by verified source/section/page, not per-run chunk ID | Fair chunk-size comparisons | M2/M4/M5 | Evaluation design review |
| D17 | M4 owns shared memory/audit and A–D harness; M2 exports inputs/results | Delegation agreement | M2/M4 | Before evaluation |
| D18 | Tier-3 learning/advanced actuators excluded from M2 package | Full-system document defers risky autonomy; no M2 assignment | M1/supervisor | Research governance |
| D19 | Real research API requires service token; mount inside M1 app with M1 access control | Confidentiality framework and shared application | M1/M2 | Integration/security review |
| D20 | No hidden regulatory source redistribution | Licensing and integrity must be verified with domain lead | M2/M5 | Corpus curation |

## Ratification workflow

At weekly integration sync, review each pending row; either accept or create an explicit decision record with owner, date, revised contract, migration plan and required regression tests. Change the adapters and config rather than forcing other members to replace unrelated modules.
