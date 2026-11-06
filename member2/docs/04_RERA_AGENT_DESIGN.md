# Evidence/RERA Agent Design
**Version:** 1.2 | **Date:** 2026-10-28

---

## 1. Purpose

The Evidence/RERA (Regulatory Evidence Retrieval Agent) retrieves regulatory passages to support provisional findings.
It never generates regulatory requirements from LLM memory.
Every retrieved passage includes a full citation traceable to a registered, provenance-verified source.

---

## 2. Retrieval Pipeline

```
EvidenceRequest
  ├── question (natural language)
  ├── filters (authorities, document_codes, sections, effective_on)
  └── top_k

Step 1: Source eligibility gate
  registry.eligible(source, filters, allow_synthetic)
  Rejects: unapproved, unverified, wrong authority/code, outside effective dates

Step 2: BM25 lexical scoring
  lexical_bm25(query, eligible_chunks) → {chunk_id: float}

Step 3: Semantic scoring
  store.semantic_search(query, candidates) → {chunk_id: float}
  (hash-demo in offline env; real BGE when model available)

Step 4: Hybrid fusion
  hybrid = (1 - weight) * bm25_norm + weight * semantic_norm
  + RRF fusion for reranking mode

Step 5: Optional cross-encoder reranking
  CrossEncoderReranker.rank(query, passage_texts) → reordered scores

Step 6: top_k selection + EvidencePassage construction
  Each passage: evidence_id, chunk_id, source_id, authority, document,
                citation, page, retrieval_score, provenance_verified

Step 7: Status determination
  ≥1 passage and min_query_token_overlap met → FOUND
  0 passages or below overlap threshold → INSUFFICIENT_EVIDENCE (requires_human_review=True)
```

---

## 3. Source Eligibility Rules

A source is eligible for retrieval if and only if:
- `approved == True`
- `provenance_verified == True`
- `source_type != SPONSOR`
- `source_type != SYNTHETIC` (unless `allow_synthetic=True` in research mode)
- `source_type != LITERATURE` (unless `filters.include_literature=True`)
- Authority matches filter if filter specified
- Document code matches filter if filter specified
- `effective_from` is set and `filters.effective_on >= effective_from`
- If `effective_to` set: `filters.effective_on <= effective_to`

Unknown applicability (no `effective_from`) is treated as ineligible; the system does not assume a source is current.

---

## 4. Citation Format

```
{authority} {document_code} {version} § {section} p.{page} [{source_id}]
Example: ICH ICH-Q11 v2013 § 3.2.S.4 p.12 [ICH-Q11]
```

---

## 5. Insufficient Evidence Handling

When eligible evidence cannot be found:
- `status = INSUFFICIENT_EVIDENCE`
- `requires_human_review = True`
- `reason` explains why (no approved source, filter mismatch, below overlap threshold)
- Evidence list is empty (enforced by Pydantic validator)

The agent never fabricates a regulatory passage.

---

## 6. Test Coverage

Key test file: `tests/test_retrieval.py`
- Retrieval returns evidence for known queries
- Retrieval returns INSUFFICIENT_EVIDENCE when no approved source
- Source isolation: synthetic sources not returned without allow_synthetic
- Authority filtering works correctly
- Effective-date filtering excludes out-of-date sources
- Overlap threshold enforced
