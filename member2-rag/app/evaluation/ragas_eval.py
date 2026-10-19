"""Optional Ragas evaluation of retrieval quality.

Which Ragas metrics need what:

| Metric                                   | Needs                                         | LLM? |
|------------------------------------------|-----------------------------------------------|------|
| NonLLMContextRecall                      | retrieved_contexts + reference_contexts       | no   |
| NonLLMContextPrecisionWithReference      | retrieved_contexts + reference_contexts       | no   |
| LLMContextRecall                         | retrieved_contexts + reference (answer)       | yes  |
| LLMContextPrecisionWithReference         | user_input + retrieved_contexts + reference   | yes  |
| Faithfulness                             | user_input + retrieved_contexts + response    | yes  |
| ResponseRelevancy                        | user_input + response (+ embeddings)          | yes  |

Member 2's agents do not generate free-text answers, so `response` is not
available here; Faithfulness / ResponseRelevancy belong to the end-to-end
evaluation run by Member 4. This module implements the two NON-LLM metrics,
which need only the expert-labelled reference passages - no API keys, no
external LLM, fully reproducible.

Reference contexts are the texts of the labelled relevant chunks, fetched from
the knowledge base by chunk ID. For page-level labels (used to compare chunk
sizes fairly) they are all chunks stored for the labelled pages, so each
configuration is judged against its own chunking of the same pages.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.evaluation.benchmark import BenchmarkItem
from app.retrieval.retrieval_service import RetrievalService


class RagasUnavailableError(RuntimeError):
    pass


def build_ragas_rows(
    service: RetrievalService,
    items: Sequence[BenchmarkItem],
    contexts_by_question: dict[str, list[str]],
) -> list[dict]:
    """Rows in Ragas' SingleTurnSample format (skips items whose labels match nothing stored)."""
    rows = []
    for item in items:
        if item.question_id not in contexts_by_question:
            continue
        refs = [p.text for p in service.store.get(item.relevant_chunk_ids)]
        if not refs:
            refs = _page_texts(service, item)
        if not refs:
            continue
        row = {
            "user_input": item.question,
            "retrieved_contexts": contexts_by_question[item.question_id],
            "reference_contexts": refs,
        }
        if item.reference_answer:
            row["reference"] = item.reference_answer
        rows.append(row)
    return rows


def _page_texts(service: RetrievalService, item: BenchmarkItem) -> list[str]:
    """Texts of every stored chunk on the item's labelled pages."""
    texts: list[str] = []
    for ref in item.relevant_pages:
        where = {"$and": [{"source_identifier": ref.source_identifier}, {"page_number": ref.page_number}]}
        _, passages = service.store.list_passages(where, limit=200)
        texts.extend(p.text for p in passages)
    return texts


def evaluate_non_llm(rows: list[dict]) -> dict[str, float]:
    """Run Ragas' non-LLM context metrics; returns mean scores."""
    if not rows:
        # Say so explicitly: an empty dict would look like Ragas silently failed.
        return {"ragas_samples": 0}
    try:
        from ragas import EvaluationDataset, SingleTurnSample, evaluate
        from ragas.metrics import NonLLMContextPrecisionWithReference, NonLLMContextRecall
    except ImportError as exc:
        raise RagasUnavailableError(
            "Ragas is not installed. Run: pip install -r requirements-eval.txt"
        ) from exc
    dataset = EvaluationDataset(
        samples=[
            SingleTurnSample(
                user_input=r["user_input"],
                retrieved_contexts=r["retrieved_contexts"],
                reference_contexts=r["reference_contexts"],
            )
            for r in rows
        ]
    )
    result = evaluate(
        dataset,
        metrics=[NonLLMContextRecall(), NonLLMContextPrecisionWithReference()],
        show_progress=False,
    )
    frame = result.to_pandas()
    out = {}
    for col in ("non_llm_context_recall", "non_llm_context_precision_with_reference"):
        if col in frame:
            out[col] = round(float(frame[col].mean()), 4)
    out["ragas_samples"] = len(rows)
    return out
