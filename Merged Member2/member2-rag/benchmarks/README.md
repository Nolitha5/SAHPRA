# Benchmark files

All questions are page-labelled drafts (AI-assisted, checked against the page text, **not
expert-verified**). Member 5's expert set will replace them.

## Current: knowledge base v2 (`kb_v2_large_w300`, 16 guidelines)

| File | What it is |
|---|---|
| `pilot_kb_v2.jsonl` | 20 ICH questions (P001–P020), page labels for the KB v2 editions |
| `pilot_sahpra_kb_v2.jsonl` | 18 SAHPRA questions (S001–S018), page labels for PEM-02 v9 and PEM-03 v4 |
| `configs.kb_v2.json` | 3 arms: dense only, reranked, reranked without the CTD filter |

```powershell
python scripts/evaluate_retrieval.py                                                   # ICH pilot (defaults)
python scripts/evaluate_retrieval.py --benchmark benchmarks/pilot_sahpra_kb_v2.jsonl   # SAHPRA pilot
```

## Historical: previous knowledge base (`ich_large_w300` etc., 6 guidelines)

Kept because the results in `../README.md` §13 refer to them, and the tests check that they stay
valid. They need the old collections, which a fresh setup does not have.

| File | What it is |
|---|---|
| `pilot.jsonl`, `pilot_sahpra.jsonl` | The same questions with page labels for the old editions (ICH print of Q6A, PEM-02 v8, PEM-03 v3) |
| `configs.pilot.json`, `configs.pilot_sahpra.json` | The October 2026 pilot arms (bge-large/small, 150/300-word chunks) |

## Templates

| File | What it is |
|---|---|
| `benchmark.jsonl` | 3 SYNTHETIC smoke-test items showing the format |
| `configs.json`, `configs.minimal.json` | Example experiment arms (`regulatory_kb*` collections) showing the config format |

When a guideline is replaced by a new edition, carry the page labels over with
`scripts/remap_benchmark_pages.py` and check every match it flags.
