# Member 2 — Real PDF Corpus Collection and Verification v0.5

## Scope and provenance

The 15 distinct documents in the previous source catalogue are now physically packaged as PDF files. The ZIP contains the three initial references and all 12 previously missing ICH/SAHPRA sources. Duplicate uploads of M4Q(R1), Q11, and WHO Annex 10 have not been recopied. All source bytes are preserved unchanged and hashed with SHA-256; exact file paths are in `REGULATORY_DOCUMENT_INVENTORY_v0.5.csv`.

## Technical validation versus regulatory approval

PDF signature, page count, extracted text, SHA-256 identity within this project, and page-anchored index builds are engineering checks. They **do not** certify publisher-byte equivalence, current regulatory applicability, legal reuse rights, independent expert labels, regulatory correctness, or use in a live dossier decision. The corpus is `PENDING_DOMAIN_REVIEW`.

## Critical items for domain review

- SAHPRA `SAHPGL-PEM-02`: filename/publication lists v9 but page 1 says v8 and includes apparent editorial drafting in the change history. Isolate regulatory use until correct publication/authenticity is confirmed.
- Q6B applies specifically to biotechnological/biological products; including it in a technical index does not mean it should be applied to chemical drug-substance cases.
- WHO stability guidance and ICH regional stability requirements may differ by context; selection and edition applicability require assessor validation.
- Q6A EMA-hosted text carries reuse restrictions; third-party/monograph licensing is separate from technical extraction.
- File hash comparison was against uploaded copies, not independent publisher-downloaded bytes.
- Unqualified relevance metrics are not presented: the included per-document queries are smoke tests only.

## Indexed data

Check `artifacts/real_corpus/REAL_CORPUS_MANIFEST.json` and `artifacts/real_corpus/QUERY_SMOKE_RESULTS_v0.5.json` for validated counts and smoke queries. SQLite/hash is a technical preview; **native ChromaDB, BGE, Ragas and real agent integration remain unverified** until the team installs dependencies and runs full assessments.

## Next actions

1. Review and approve versions, source jurisdiction and reuse/licensing with Member 5/domain supervisor.
2. Select the intended dossier product scope and enforce source-specific filters, especially Q6B and any restricted source.
3. Run native Chroma/BGE vector indexing and provenance-faithfulness tests on supported workstation.
4. Obtain expert-labelled question–passage pairs and assess retrieval using MRR/Recall@K/nDCG, independently of smoke tests.
5. Agree the Member 1–5 common contract and complete live integration/human evaluation.
