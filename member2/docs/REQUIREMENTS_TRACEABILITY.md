# Requirements traceability — Member 2

Source references are the PDF page numbers in the supplied documents, not proof of runtime evaluation.

| ID | Source requirement | Implementation | Automated verification | Actual-system status |
|---|---|---|---|---|
| RKB-01 | M2 spec p1: curate SAHPRA/ICH/WHO/pharmacopoeia corpus | `schemas.SourceRecord`, `registry.SourceRegistry`, `SOURCE_POLICY.md` | registry allow/deny/temporal tests | Actual authority/versions/permissions require M5 |
| RKB-02 | M2 p1: provenance authority/document/section/version/date | `SourceRecord`, `RegulatoryChunk`, `EvidencePassage` | citation/metadata tests | Actual source coordinates unverified pending real PDFs |
| RKB-03 | M2 p1: ChromaDB vector store | `storage.ChromaVectorStore`, immutable per-model collection | in-memory vector adapter tested | Chroma dependency unavailable in build environment; test on project machine |
| RKB-04 | M2 p1: chunk format with M3 | `schemas.DossierChunk`, `RegulatoryChunk`, `chunking` | CTD section boundary tests | M3 must ratify shared shape |
| RERA-01 | M2 p1: query embedding / retrieve top-K | `embeddings`, `storage`, `retrieval.EvidenceService` | retrieval tests | Live model download+Chroma pending |
| RERA-02 | M2 p1: rank/rerank candidate citations | hybrid BM25/RRF + optional `CrossEncoderReranker` | ranking/citation tests | BGE-reranker empirical effect pending real corpus |
| RERA-03 | M2 p1: metadata filtering | authority/document/section/date predicates | filter tests | Version applicability depends on verified dates |
| RERA-04 | M2 p1: fail closed without evidence | `EvidenceStatus` explicit negative and error states | no-evidence/error tests | Real false-negative rate pending expert scoring |
| RERA-05 | M2 p2: shared service for all agents | `integration.evidence_node`, `/m2/evidence` | integration/API tests | M1 state integration pending |
| S4-01 | M2 p1: S.4 specification/limits/methods/validation/batch | `s4.S4ControlAgent` + deterministic field extractor | S4 five-subsection tests | Domain-level extraction completeness pending real CTDs |
| S4-02 | Team Delegation p2: shared structured Finding | `schemas.Finding` provisional | schema/API tests | M1's canonical schema not yet supplied |
| S4-03 | M2 p1: S.4 completeness/consistency | missing material markers and sponsor-stated numeric comparisons in `s4_rules` | no-data & batch-range tests | Expert-reviewed S4 logic and true regulatory comparison pending |
| S4-04 | Full methodology: human gate | all Member-2 findings `QA=PENDING` and human-review required | S4 tests | M5 QA and human gate owned by M5/M1 |
| EVAL-01 | M2 p1: embedding model comparison | `experiments.run_grid`, configurable embedders | script source/arg paths tested; synthetic metrics | Actual model comparisons not run |
| EVAL-02 | M2 p1: 256/512/1024 and overlap | `chunking(... tokenizer=...)`, grid sizes | chunk tests | Exact tokenizer resources require install |
| EVAL-03 | M2 p1: Precision@K, Recall@K, MRR/nDCG | `evaluation`, `experiments.anchored_benchmark` | metric tests | Expert-labelled corpus not provided |
| EVAL-05 | M2 spec p1: Ragas support | `ragas_adapter` handoff with explicit judge/metrics required | adapter export test | Judge-based metrics pending local judge/M4 agreement |
| EVAL-04 | M2 p2: M4 scoring handoff | `BenchmarkReport`, JSON summaries | evaluation tests | M4 harness hookup pending |
| INT-01 | M1 spec p1: Tier-0 S1 with real Chroma passage | real-PDF CLI + Evidence node + instructions | synthetic stub integration tests | Real Tier-0 witness pending M1+M3+real guideline |
| INT-02 | M3 spec pp1–2: section-tagged, table-preserved input | `DossierChunk` and table_rows | structured table tests | Contract signoff pending |
| INT-03 | M4 spec pp1–2: source evidence, cross-section, metrics | citations + findings + report | output tests | Actual M4 memory/harness integration pending |
| INT-04 | M5 spec pp1–2: pharmacopoeia/version retrieval, critic | effective-on filters + passage locators | historical-date and no-source tests | Monographs unbundled; licence & ground truth pending |
| INT-05 | Delegation p2: shared repo / weekly integration | self-contained package + adapter + README | unit suite | Actual mono-repo URL/branch not supplied |
| SEC-01 | M3 spec: redaction/quality | `quality_flag` fail-closed for S4, no dossier RKB indexing | security/unit tests | M3 owns actual PII redaction |
| SEC-02 | M5: preserve human decisions | no M2 verdict or audit mutation | tests | M4/M5/M1 own human audit/workflow |
| SEC-03 | Governance: guarded research API | required `M2_SERVICE_TOKEN` in research mode | API auth test | Full M1 RBAC/network protections not supplied |
| TIER-03 | Full architecture p10: advanced learning/actuators deferred | excluded, documented | N/A | NOT IMPLEMENTED by design / outside M2 |

## What implementation *does not* certify

- That the RKB contains all applicable sources, or that editions are legally/currently applicable.
- That a missing source means no regulation exists.
- That the chosen local LLM is suitable or has been downloaded on the target ThinkPad.
- That S.4 reaches any research accuracy, precision, recall, sensitivity or faithfulness threshold.
- That expert panels, controlled pilot deployment or the A–D comparative research have been completed.
- That other members' actual nodes or monorepo pass integration tests.
