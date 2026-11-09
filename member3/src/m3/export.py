"""
Export DossierChunks in the exact shape M2's S4ReviewRequest expects
(member2/src/m2/schemas.py::S4ReviewRequest on the aziz-and-sipho branch),
so M2's own `scripts/export_m3_chunks_example.py` validator can be pointed
at our output directly with no translation step.
"""
from __future__ import annotations

import json
from pathlib import Path

from .schemas import DossierChunk


def to_case_json(
    case_id: str,
    chunks: list[DossierChunk],
    as_of: str | None = None,
    relevant_regulatory_codes: list[str] | None = None,
) -> dict:
    return {
        "case_id": case_id,
        "dossier_chunks": [c.model_dump(mode="json") for c in chunks],
        "as_of": as_of,
        "relevant_regulatory_codes": relevant_regulatory_codes or [],
    }


def write_case_json(
    out_path: str | Path,
    case_id: str,
    chunks: list[DossierChunk],
    as_of: str | None = None,
    relevant_regulatory_codes: list[str] | None = None,
) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = to_case_json(case_id, chunks, as_of, relevant_regulatory_codes)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
