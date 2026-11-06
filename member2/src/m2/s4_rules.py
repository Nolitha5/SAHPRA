"""Conservative numerical cross-checks against SPONSOR-STATED ranges only.

No regulatory limits are encoded here. Only compare like units and exact test names.
No chemistry equivalence, unit conversion, detection-limit inference or approval decision.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any
from .schemas import DossierChunk

RANGE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(%|ppm|mg/mL|mg)?\s*$",re.I)
NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(%|ppm|mg/mL|mg)?\s*$",re.I)

@dataclass
class Observation:
    issue_type: str
    description: str
    source_chunk_ids: list[str]
    test_name: str
    data: dict[str,Any]

def canonical_test(s: str) -> str:
    return " ".join(s.casefold().split())

def pick(row, *names):
    lowered={str(k).casefold().strip():v for k,v in row.items()}
    for name in names:
        if name in lowered and lowered[name] is not None:
            return str(lowered[name]).strip()
    return ""

def compare_sponsor_batch_data(chunks: list[DossierChunk]) -> list[Observation]:
    """Identifies potential out-of-range numeric values without interpreting regulatory acceptability."""
    specs={}; batches=[]
    for chunk in chunks:
        if chunk.quality_flag: continue  # garbled/redacted source cannot support precise comparisons
        for row in chunk.table_rows:
            test=pick(row,"test","parameter","test name","attribute")
            if not test:continue
            if chunk.ctd_section.upper().startswith("3.2.S.4.1"):
                limit=pick(row,"acceptance criteria","limits","limit","specification","criterion")
                m=RANGE.fullmatch(limit)
                if not m:continue
                low,high=float(m.group(1)),float(m.group(2))
                if high<low:continue
                specs[canonical_test(test)]=(low,high,(m.group(3) or "").casefold(),chunk.chunk_id,limit)
            if chunk.ctd_section.upper().startswith("3.2.S.4.4"):
                value=pick(row,"result","measured result","assay","value")
                m=NUMBER.fullmatch(value)
                if m:
                    batches.append((canonical_test(test),float(m.group(1)),(m.group(2) or "").casefold(),chunk.chunk_id,value))
    observations=[]
    for test,value,unit,chunk_id,raw in batches:
        if test not in specs:continue
        low,high,spec_unit,spec_chunk_id,limit=specs[test]
        if unit!=spec_unit:continue  # no unit inference or conversion
        if value<low or value>high:
            observations.append(Observation(issue_type="SPONSOR_INTERNAL_NUMERIC_DISCREPANCY",
                description=f"Reported {test} value {raw} appears outside the sponsor-stated specification range {limit}; verify the underlying table, method and units manually.",
                source_chunk_ids=[spec_chunk_id,chunk_id], test_name=test,
                data={"observed":value,"lower":low,"upper":high,"unit":unit}))
    return observations
