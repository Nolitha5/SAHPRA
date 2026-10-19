# How to present and defend Member 2's contribution

## The 60-second version

"I built the team's evidence layer. Member 3's pipeline turns regulatory PDFs into passages. My code
validates every passage, gives it a stable ID and a content fingerprint, and stores it in ChromaDB with
its source, version, page and CTD section. When any agent asks a question, my shared retrieval service
finds the closest passages with the BGE-large embedding model, then re-scores the best 20 with a BGE
cross-encoder reranker and returns the top 5 — each with a citation.

On top of that I built two agents. Evidence/RERA returns the evidence with citations and says
'insufficient evidence' when nothing fits. S.4 Control does the same for specifications, methods,
validation and batch analyses, and can check batch results against the sponsor's limits with strict unit
rules. Neither agent ever says a dossier is compliant — they label findings partial, conflicting,
unsupported or human-review, and the assessor decides."

## Likely questions and good answers

**Why two stages (embedding search + reranker)?**
The embedding model compares pre-computed vectors, so it is fast enough to search everything but less
precise. The cross-encoder reads question and passage together, so it is more precise but too slow for
the whole database. Using it only on 20 candidates gives most of the precision at a fraction of the cost.
The benchmark measures exactly this (config with vs without reranker).

**What is the query instruction?**
BGE v1.5 models were trained to embed short queries with the prefix "Represent this sentence for
searching relevant passages: ". Passages are embedded without it. Getting this wrong quietly lowers
retrieval quality.

**How do you stop hallucinated citations?**
1. Agents are rule-based — no language model writes conclusions. 2. A citation is built only from the
metadata stored with the passage. 3. The `Finding` model refuses to exist if a citation does not match a
returned passage, or a passage has no citation.

**What does "insufficient evidence" mean?**
Three distinct cases: the database is empty; nothing matched; or passages matched but none passed the
relevance threshold. The first two say explicitly that absence of results does not prove no rule exists.
The third shows the weak candidates to the assessor instead of hiding them.

**Are the reranker scores probabilities?**
No. I keep them as raw logits on purpose. They only rank passages and decide what is shown.

**How do you detect outdated or conflicting sources?**
From metadata: applicability status (current / superseded / withdrawn / draft) and the same document
appearing in more than one version. Content-level contradictions between different documents are listed
as future work.

**Why page-level labels in the benchmark?**
Changing chunk size changes chunk IDs, so chunk labels are not comparable across chunkings. Page labels
are, which makes the chunk-size experiment fair.

**Why no LangChain?**
Three direct calls do not need a framework; avoiding it keeps the dependency list small and every step
visible and testable.

**What results do you have?**
Honest answer: the pipeline and 139 tests are complete; real benchmark numbers need Member 3's processed
documents and Member 5's expert-labelled questions. Nothing has been reported that was not measured.

**How do you protect confidential sponsor data?**
Sponsor evidence is kept separate, never logged (logs hold only a short fingerprint), hidden from object
printouts and removed from exports by `model_dump_redacted()`. A test checks that the logs contain none of it.
