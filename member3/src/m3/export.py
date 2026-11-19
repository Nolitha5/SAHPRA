"""
Export DossierChunks in the exact shape M2's S4ReviewRequest expects
(member2/src/m2/schemas.py::S4ReviewRequest on the aziz-and-sipho branch),
so M2's own `scripts/export_m3_chunks_example.py` validator can be pointed
at our output directly with no translation step.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

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
    payload = to_case_json(case_id, chunks, as_of, relevant_regulatory_codes)
    return write_json(out_path, payload)


def write_json(out_path: str | Path, payload: dict | list) -> Path:
    """Publish complete JSON atomically, without leaving a partial output."""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8",
                                delete=False, prefix=".m3-", suffix=".tmp") as stream:
            temporary_path = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return path


def require_separate_output(out_path: str | Path, inputs: list[str]) -> None:
    output = Path(out_path).resolve()
    if output.suffix.lower() != ".json" or any(
        output == Path(source).resolve()
        or (output.exists() and Path(source).exists() and output.samefile(source))
        for source in inputs
    ):
        raise ValueError("Choose a .json output path separate from the input PDFs.")
