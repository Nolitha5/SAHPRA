"""Strict Ragas handoff. This layer never invents expert answers or calls cloud judges."""
from __future__ import annotations
import json
from pathlib import Path
from pydantic import BaseModel,Field

class RagasHandoffRow(BaseModel):
    user_input: str = Field(min_length=3)
    retrieved_contexts: list[str] = Field(min_length=1)
    response: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    case_id: str | None = None
    source_ids: list[str] = Field(min_length=1)


def export_ragas_jsonl(rows: list[RagasHandoffRow], target: str) -> None:
    if not rows:raise ValueError("No expert verified reference records")
    file=Path(target);file.parent.mkdir(parents=True,exist_ok=True)
    with file.open("w",encoding="utf-8") as f:
        for r in rows:
            # Includes approved reference and actual generated answer; caller supplies both.
            f.write(json.dumps(r.model_dump(mode="json"),ensure_ascii=False)+"\n")


def evaluate_with_ragas(rows: list[RagasHandoffRow], *, judge_llm, embeddings,
                        metrics=None):
    """Run only with explicitly configured LOCAL eval model/embeddings from M4.

    Ragas API versions vary; M4 must pin/test the same ragas and datasets versions.
    External judges are intentionally never selected by default.
    """
    if judge_llm is None or embeddings is None:
        raise ValueError("Explicit local evaluation LLM and embeddings are required")
    try:
        from datasets import Dataset
        from ragas import evaluate
    except ImportError as e:
        raise RuntimeError('Install optional evaluation tooling: pip install -e ".[experiment]" and datasets') from e
    if not rows:raise ValueError("No expert reference records")
    records=[{k:v for k,v in r.model_dump().items() if k in
              {'user_input','retrieved_contexts','response','reference'}} for r in rows]
    data=Dataset.from_list(records)
    if metrics is None:
        # Explicit choice avoids silently invoking unknown/judge-provider defaults.
        raise ValueError("Specify Ragas metric objects compatible with the pinned Ragas version")
    return evaluate(data,metrics=metrics,llm=judge_llm,embeddings=embeddings,raise_exceptions=True)
