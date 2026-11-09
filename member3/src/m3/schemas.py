"""
Shared contract objects for M3 (Ingestion & Perception).

DossierChunk mirrors member2/src/m2/schemas.py::DossierChunk exactly (locked
with M2 on the aziz-and-sipho branch) so chunks can be handed to M2's S.4
review without any translation layer. Do not change field names/types here
without re-syncing with M2 — this is the seam the whole system depends on.

S5Claim mirrors Florah-M5's backend/models.py::S5Claim for the S.5
Reference Standards handoff to M5.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DossierChunk(StrictModel):
    """One retrieval-sized, CTD-section-tagged piece of a sponsor dossier.

    This is the sole hand-off object from M3 to the rest of the system.
    M2 enforces (on their side) that only chunks whose ctd_section starts
    with their section of interest and carry no quality_flag are reviewed —
    so quality_flag must be set (not silently dropped) whenever extraction
    is uncertain, empty, or garbled.
    """

    chunk_id: str
    document_id: str
    ctd_section: str  # e.g. "3.2.S.4.1" — exact CTD code, never a guess
    text: str
    page: Optional[int] = Field(default=None, ge=1)
    kind: str = "text"  # "text" | "table" | "figure_caption"
    table_rows: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    quality_flag: Optional[str] = None  # set => excluded from downstream review


class S5Claim(StrictModel):
    """Structured S.5 sponsor claim extracted from the dossier, for M5."""

    substance_name: str
    standard: str  # e.g. "BP", "USP", "Ph.Eur.", "IP"
    edition_claimed: str  # e.g. "BP 2019"
    test_method: Optional[str] = None
    submission_date: date
