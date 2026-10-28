"""Structured numerical comparisons for CTD 3.2.S.4 (pure functions, no I/O).

Two comparisons are supported:

A. Batch results vs the sponsor's OWN acceptance criteria (S.4.4 vs S.4.1).
   "Are the reported batch values inside the limits the sponsor declared?"

B. Sponsor acceptance criteria vs a regulatory limit (S.4.1 vs a guideline),
   ONLY when the regulatory limit is supplied in structured form with a
   chunk_id that resolves to a passage in the knowledge base.
   "Is the sponsor's limit at least as strict as the cited limit?"

Safety rules - a comparison is NOT performed (outcome = not_compared, which
forces human review) when:
* the acceptance criterion or its unit is missing,
* units differ and are not in the same explicit convertible family
  (a bare "%" is never converted, because it could mean w/w, area %, label
  claim, ...),
* the result is qualitative ("Complies", "Conforms"), "ND"/"BLQ" without a
  number, uses a comma decimal, or is otherwise unparseable,
* a "<x" result cannot be placed on one side of the limit.

Results within half a unit of the limit's last decimal place are flagged as
"borderline" because pharmacopoeial rounding conventions may change the
outcome.

Acceptance criteria are NEVER invented here; they only come from the caller.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_UNIT_ALIASES = {
    "%w/w": "%w/w", "% w/w": "%w/w", "percent w/w": "%w/w", "%(w/w)": "%w/w", "% (w/w)": "%w/w",
    "%": "%", "percent": "%",
    "ppm": "ppm", "ppb": "ppb",
    "mg/g": "mg/g", "ug/g": "ug/g", "µg/g": "ug/g", "μg/g": "ug/g", "mcg/g": "ug/g",
    "mg/kg": "mg/kg", "ng/g": "ng/g",
}

_MASS_FRACTION = {
    "%w/w": Decimal("1e-2"),
    "ppm": Decimal("1e-6"),
    "ppb": Decimal("1e-9"),
    "mg/g": Decimal("1e-3"),
    "ug/g": Decimal("1e-6"),
    "mg/kg": Decimal("1e-6"),
    "ng/g": Decimal("1e-9"),
}


def normalise_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    cleaned = re.sub(r"\s+", " ", unit.strip().lower())
    if not cleaned:
        return None
    return _UNIT_ALIASES.get(cleaned, _UNIT_ALIASES.get(cleaned.replace(" ", ""), cleaned))


def convert(value: Decimal, from_unit: str, to_unit: str) -> Decimal | None:
    """Convert between units; None if not safely convertible."""
    a, b = normalise_unit(from_unit), normalise_unit(to_unit)
    if a is None or b is None:
        return None
    if a == b:
        return value
    if a in _MASS_FRACTION and b in _MASS_FRACTION:
        return value * _MASS_FRACTION[a] / _MASS_FRACTION[b]
    return None


def _decimals(value: Decimal) -> int:
    exp = value.as_tuple().exponent
    return max(0, -exp) if isinstance(exp, int) else 0





class AcceptanceCriterion(BaseModel):
    """A numeric acceptance criterion for one test (sponsor or regulatory)."""

    model_config = ConfigDict(extra="forbid")

    test_name: str = Field(min_length=1, max_length=200)
    lower_limit: Decimal | None = None
    upper_limit: Decimal | None = None
    lower_inclusive: bool = True
    upper_inclusive: bool = True
    unit: str | None = None
    criterion_text: str | None = Field(default=None, max_length=300)
    source: Literal["sponsor_specification", "regulatory"] = "sponsor_specification"
    citation_chunk_id: str | None = Field(
        default=None, description="Required for regulatory limits: KB chunk the limit is taken from."
    )

    @model_validator(mode="after")
    def _check(self) -> AcceptanceCriterion:
        if self.lower_limit is not None and self.upper_limit is not None and self.lower_limit > self.upper_limit:
            raise ValueError("lower_limit cannot be greater than upper_limit")
        if self.source == "regulatory" and not self.citation_chunk_id:
            raise ValueError("regulatory limits must cite the knowledge-base chunk_id they come from")
        return self

    @property
    def is_numeric(self) -> bool:
        return self.lower_limit is not None or self.upper_limit is not None

    @classmethod
    def from_text(
        cls, test_name: str, text: str, unit: str | None = None, **kwargs
    ) -> AcceptanceCriterion:
        """Parse simple criterion text such as 'NMT 0.10%', 'NLT 98.0%',
        '98.0 - 102.0 %', '≤ 0.5 ppm'. Unparseable text gives a non-numeric
        criterion (which will not be compared automatically)."""
        lower, upper, parsed_unit = parse_criterion_text(text)
        return cls(
            test_name=test_name,
            lower_limit=lower,
            upper_limit=upper,
            unit=unit or parsed_unit,
            criterion_text=text,
            **kwargs,
        )


class BatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(min_length=1, max_length=100)
    test_name: str = Field(min_length=1, max_length=200)
    reported_value: str = Field(
        min_length=1, max_length=100, description="As reported, e.g. '0.05', '<0.05', 'Complies'"
    )
    unit: str | None = None


class Outcome(str, Enum):
    WITHIN_CRITERIA = "within_criteria"
    OUTSIDE_CRITERIA = "outside_criteria"
    AT_LEAST_AS_STRICT = "at_least_as_strict"
    LESS_STRICT = "less_strict"
    NOT_COMPARED = "not_compared"


class ComparisonRow(BaseModel):
    comparison: Literal["batch_vs_sponsor_spec", "sponsor_spec_vs_regulatory"]
    test_name: str
    batch_id: str | None = None
    reported_value: str | None = None
    reported_unit: str | None = None
    criterion_text: str | None = None
    criterion_unit: str | None = None
    citation_chunk_id: str | None = None
    outcome: Outcome
    reason: str
    borderline: bool = False





_NUM = r"(\d+(?:\.\d+)?)"
_UNIT = r"\s*(%\s*w/w|%|ppm|ppb|mg/g|µg/g|μg/g|ug/g|mcg/g|mg/kg|ng/g)?"


def _dec(text: str) -> Decimal:
    return Decimal(text)


def parse_criterion_text(text: str) -> tuple[Decimal | None, Decimal | None, str | None]:
    t = text.strip()
    patterns = [
        (rf"^(?:NMT|not more than|≤|<=)\s*{_NUM}{_UNIT}$", "upper"),
        (rf"^(?:NLT|not less than|≥|>=)\s*{_NUM}{_UNIT}$", "lower"),
        (rf"^{_NUM}{_UNIT}\s*(?:-|–|to)\s*{_NUM}{_UNIT}$", "range"),
    ]
    for pattern, kind in patterns:
        m = re.match(pattern, t, flags=re.IGNORECASE)
        if not m:
            continue
        if kind == "upper":
            return None, _dec(m.group(1)), m.group(2)
        if kind == "lower":
            return _dec(m.group(1)), None, m.group(2)
        u1, u2 = m.group(2), m.group(4)
        if u1 and u2 and normalise_unit(u1) != normalise_unit(u2):
            return None, None, None
        return _dec(m.group(1)), _dec(m.group(3)), u1 or u2
    return None, None, None


_QUALITATIVE = {"complies", "conforms", "passes", "pass", "positive", "negative", "meets requirements"}
_NONDETECT = {"nd", "n.d.", "not detected", "blq", "<loq", "< loq", "bql", "<lod", "< lod"}


def parse_reported_value(raw: str) -> tuple[str, Decimal | None, str]:
    """Return (kind, number, note). kind: numeric | below | above | unusable."""
    value = raw.strip()
    lowered = value.lower()
    if lowered in _QUALITATIVE:
        return "unusable", None, "qualitative result; requires assessor judgement"
    if lowered in _NONDETECT:
        return "unusable", None, "non-detect reported without a numeric limit (LOD/LOQ needed)"
    if "," in value:
        return "unusable", None, "comma in number is ambiguous (decimal or thousands separator)"
    m = re.fullmatch(r"(<|≤|<=|LT)\s*(\d+(?:\.\d+)?)", value, flags=re.IGNORECASE)
    if m:
        return "below", Decimal(m.group(2)), "reported as below a value"
    m = re.fullmatch(r"(>|≥|>=|GT)\s*(\d+(?:\.\d+)?)", value, flags=re.IGNORECASE)
    if m:
        return "above", Decimal(m.group(2)), "reported as above a value"
    try:
        return "numeric", Decimal(value), ""
    except InvalidOperation:
        return "unusable", None, "result is not a number"





def _within(v: Decimal, c: AcceptanceCriterion) -> bool:
    below = c.lower_limit is not None and (v < c.lower_limit or (v == c.lower_limit and not c.lower_inclusive))
    above = c.upper_limit is not None and (v > c.upper_limit or (v == c.upper_limit and not c.upper_inclusive))
    return not (below or above)


def _borderline(v: Decimal, c: AcceptanceCriterion) -> bool:
    for limit in (c.lower_limit, c.upper_limit):
        if limit is None:
            continue
        half_step = Decimal(1).scaleb(-_decimals(limit)) / 2
        if v != limit and abs(v - limit) < half_step:
            return True
    return False


def compare_batch_result(result: BatchResult, criterion: AcceptanceCriterion | None) -> ComparisonRow:
    row = dict(
        comparison="batch_vs_sponsor_spec",
        test_name=result.test_name,
        batch_id=result.batch_id,
        reported_value=result.reported_value,
        reported_unit=result.unit,
        criterion_text=criterion.criterion_text if criterion else None,
        criterion_unit=criterion.unit if criterion else None,
    )

    def not_compared(reason: str) -> ComparisonRow:
        return ComparisonRow(**row, outcome=Outcome.NOT_COMPARED, reason=reason)

    if criterion is None:
        return not_compared("no acceptance criterion supplied for this test")
    if not criterion.is_numeric:
        return not_compared("acceptance criterion is not numeric")
    if not criterion.unit:
        return not_compared("acceptance criterion has no unit")
    if not result.unit:
        return not_compared("batch result has no unit")

    kind, number, note = parse_reported_value(result.reported_value)
    if kind == "unusable" or number is None:
        return not_compared(note)
    value = convert(number, result.unit, criterion.unit)
    if value is None:
        return not_compared(f"units '{result.unit}' and '{criterion.unit}' are not safely comparable")

    if kind == "numeric":
        within = _within(value, criterion)
        border = _borderline(value, criterion)
        return ComparisonRow(
            **row,
            outcome=Outcome.WITHIN_CRITERIA if within else Outcome.OUTSIDE_CRITERIA,
            reason=("value within stated limits" if within else "value outside stated limits")
            + ("; borderline - rounding convention may affect the outcome" if border else ""),
            borderline=border,
        )
    if kind == "below":
        if criterion.upper_limit is not None and criterion.lower_limit is None and value <= criterion.upper_limit:
            return ComparisonRow(**row, outcome=Outcome.WITHIN_CRITERIA,
                                 reason="reported below a value that is not above the upper limit")
        return not_compared("'<' result cannot be placed relative to these limits")

    if criterion.lower_limit is not None and criterion.upper_limit is None and value >= criterion.lower_limit:
        return ComparisonRow(**row, outcome=Outcome.WITHIN_CRITERIA,
                             reason="reported above a value that is not below the lower limit")
    return not_compared("'>' result cannot be placed relative to these limits")


def compare_batches(
    specification: list[AcceptanceCriterion], batch_results: list[BatchResult]
) -> list[ComparisonRow]:
    by_test: dict[str, list[AcceptanceCriterion]] = {}
    for c in specification:
        by_test.setdefault(c.test_name.strip().lower(), []).append(c)
    rows = []
    for result in batch_results:
        matches = by_test.get(result.test_name.strip().lower(), [])
        if len(matches) > 1:
            rows.append(ComparisonRow(
                comparison="batch_vs_sponsor_spec", test_name=result.test_name, batch_id=result.batch_id,
                reported_value=result.reported_value, reported_unit=result.unit,
                outcome=Outcome.NOT_COMPARED, reason="ambiguous: more than one criterion for this test name",
            ))
            continue
        rows.append(compare_batch_result(result, matches[0] if matches else None))
    return rows





def compare_spec_to_regulatory(
    sponsor: AcceptanceCriterion, regulatory: AcceptanceCriterion, citation_resolves: bool
) -> ComparisonRow:
    row = dict(
        comparison="sponsor_spec_vs_regulatory",
        test_name=sponsor.test_name,
        reported_value=sponsor.criterion_text,
        reported_unit=sponsor.unit,
        criterion_text=regulatory.criterion_text,
        criterion_unit=regulatory.unit,
        citation_chunk_id=regulatory.citation_chunk_id,
    )

    def not_compared(reason: str) -> ComparisonRow:
        return ComparisonRow(**row, outcome=Outcome.NOT_COMPARED, reason=reason)

    if not citation_resolves:
        return not_compared("regulatory limit cites a chunk_id that is not in the knowledge base")
    if not (sponsor.is_numeric and regulatory.is_numeric):
        return not_compared("one of the criteria is not numeric")
    if not (sponsor.unit and regulatory.unit):
        return not_compared("missing unit on sponsor or regulatory criterion")

    checks: list[bool] = []
    if regulatory.upper_limit is not None:
        if sponsor.upper_limit is None:
            return not_compared("regulatory upper limit exists but sponsor has no upper limit")
        s_up = convert(sponsor.upper_limit, sponsor.unit, regulatory.unit)
        if s_up is None:
            return not_compared(f"units '{sponsor.unit}' and '{regulatory.unit}' are not safely comparable")
        checks.append(s_up <= regulatory.upper_limit)
    if regulatory.lower_limit is not None:
        if sponsor.lower_limit is None:
            return not_compared("regulatory lower limit exists but sponsor has no lower limit")
        s_lo = convert(sponsor.lower_limit, sponsor.unit, regulatory.unit)
        if s_lo is None:
            return not_compared(f"units '{sponsor.unit}' and '{regulatory.unit}' are not safely comparable")
        checks.append(s_lo >= regulatory.lower_limit)
    strict = all(checks)
    return ComparisonRow(
        **row,
        outcome=Outcome.AT_LEAST_AS_STRICT if strict else Outcome.LESS_STRICT,
        reason="sponsor limit is at least as strict as the cited limit"
        if strict
        else "sponsor limit is wider than the cited limit",
    )
