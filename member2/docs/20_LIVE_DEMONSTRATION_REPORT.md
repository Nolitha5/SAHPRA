# 20. Live Demonstration Report
**Version:** v1.4.0  
**Date:** 2026-10-29  
**Application:** Member 2 — Regulatory Knowledge Base & Evidence Explorer  
**URL:** http://127.0.0.1:8501

---

## Launch Confirmation

The Streamlit application was launched successfully on 2026-10-29:

```
python -m streamlit run tools/member2_explorer/app.py \
    --server.address 127.0.0.1 --server.port 8501 \
    --server.headless true --browser.gatherUsageStats false
```

Port 8501 confirmed open via `Test-NetConnection`. Browser preview opened and confirmed rendering.

**App title:** "Member 2 — Regulatory Knowledge Base & Evidence Explorer"  
**Page A (Overview):** ChromaDB shown as 🟢 Connected for both collections.  
- Regulatory: 554 chunks  
- Dossier: 2064 chunks  

---

## Scenario 1 — Regulatory Evidence Retrieval (PASS)

**Query:** "What are the ICH requirements for analytical procedure validation under CTD section 3.2.S.4.3?"  
**Page:** C — Regulatory Evidence Search  
**Method:** BGE (bge-large-en-v1.5) + ChromaDB cosine similarity  

**Result:** Found 3 relevant sources from 15 candidate chunks.

| Rank | Source ID | Score | Section |
|---|---|---|---|
| 1 | ICH-Q14 | 0.8098 | 3.2.S.4.3 |
| 2 | (additional source) | — | — |
| 3 | (additional source) | — | — |

**Top retrieved passage (actual text):** 
> "3.2.S.4.2 for drug substance or section 3.1.P.5.2 for drug product. Validation data and supportive Information needed to justify the analytical procedure control strategy should be included in the CTD section 3.2.S.4.3 for drug substance or section 3.2.P.5.3 for drug product. Other analytical procedures used as part of the control strategy should be included in relevant CTD sections…"

Source verified: ICH-Q14, authority=ICH, version=Step 4 2023.  
Citation ID, authority, title, section, page and verification status all displayed.  
No external LLM API calls made.  
Evidence confirmed: **ACTUAL_CHROMADB + real BGE embeddings**.

---

## Scenario 2 — Drug-Substance Document Navigation (VERIFIED VIA DATA)

KB Browser page loads dossier source metadata from `validation/COMPLETE_KNOWLEDGE_BASE_AUDIT.json`.  
Dossier PDFs confirmed present in `pharmacopoeia/incoming/raw_from_pharmacy/` (45 files, 43 with indexed chunks).  
Source list filterable by substance (Valsartan / Amlodipine / Hydrochlorothiazide).  
**Note:** Full browser-click walk-through not completed due to BGE model load time between page transitions. Page code confirmed functional.

---

## Scenario 3 — Provisional S.4 Assessment (PASS)

**Substance:** Valsartan  
**Section:** S.4.1 — Specification  

Dual-panel layout confirmed:
- **Regulatory Evidence panel**: ICH-M4Q-R1 retrieved, score=0.787  
  - Label: UNAPPROVED_TECHNICAL_ONLY
- **Sponsor Dossier Evidence panel**: dossier_valsartan_edited_validation... retrieved  
  - Label: "⚠️ Class D — Sponsor dossier. requires_human_review=True. Not regulatory authority guidance."

QA Status block shown at bottom:
- Regulatory guidance found: Yes  
- Dossier evidence found: Yes  
- Status: PENDING_HUMAN_REVIEW  

Source isolation between panels confirmed visually.

---

## Scenario 4 — Missing Evidence Abstention (ARCHITECTURE VERIFIED)

The `page_evidence_search()` function in `tools/member2_explorer/app.py` returns:

> "**Insufficient evidence.** No passages found in the regulatory corpus. The system cannot provide an evidence-based answer to this question."

when `results` is empty. This path is exercised when the BGE search returns no results above threshold. Confirmed by code review; not live-clicked in this session.

---

## Scenario 5 — Source Isolation (PASS)

Verified via `validation/COMPLETE_KNOWLEDGE_BASE_AUDIT.json`:

| Isolation Check | Value | Expected |
|---|---|---|
| Dossier chunks in regulatory collection | 0 | 0 |
| Regulatory chunks in dossier collection | 0 | 0 |
| Compendial in ChromaDB | False | False |
| Quarantine HTML in ChromaDB | False | False |
| **Verdict** | **PASS** | PASS |

S.4 page display confirms dossier and regulatory evidence shown in separate panels with distinct labels.

---

## Regression Results

Full test suite run on 2026-10-29:

```
================= 186 passed, 3 warnings in 93.70s (0:01:33) ==================
```

3 non-blocking warnings (httpx deprecation + FutureWarning on SentenceTransformer).

---

## What This Demonstration Does NOT Claim

- Expert-labelled regulatory accuracy evaluation (not conducted)  
- BGE vs MiniLM / bge-m3 model comparison (not conducted)  
- Full M1–M5 integration (not yet integrated)  
- Authorised regulatory approval of any source document  
- Completion of human assessor pilot

---

## Demo Evidence Files

- `validation/live_demo/DEMO_EXECUTION_RECORD.json` — machine-readable execution record  
- `validation/CHROMA_SOURCE_ID_AUDIT.json` — ChromaDB source IDs verified  
- `validation/COMPLETE_KNOWLEDGE_BASE_AUDIT.json` — full isolation audit  
