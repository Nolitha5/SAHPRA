"""S.4 Control agent: evidence findings, numeric comparisons, units, missing specs."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.agents.s4_control import TOPIC_SECTIONS, S4ControlAgent, S4Topic
from app.agents.spec_comparison import (
    AcceptanceCriterion,
    BatchResult,
    Outcome,
    compare_batch_result,
    compare_spec_to_regulatory,
    convert,
    parse_criterion_text,
)
from app.schemas import AgentRequest, EvidenceStatus, Finding, QAStatus, SponsorEvidence


def spec(**kw):
    base = {"test_name": "Impurity A", "upper_limit": "0.10", "unit": "%", "criterion_text": "NMT 0.10%"}
    base.update(kw)
    return AcceptanceCriterion(**base)


def batch(value, unit="%", test="Impurity A", bid="B1"):
    return BatchResult(batch_id=bid, test_name=test, reported_value=value, unit=unit)



@pytest.mark.parametrize("topic", list(S4Topic))
def test_topic_maps_to_section(service, topic):
    finding = S4ControlAgent(service).retrieve_evidence("drug substance", topic)
    assert finding.ctd_section == TOPIC_SECTIONS[topic]
    assert finding.agent_name == "s4_control"
    assert finding.metadata["s4_topic"] == topic.value


def test_evidence_finding_uses_shared_service(service):
    agent = S4ControlAgent(service)
    assert agent.retrieval is service
    finding = agent.retrieve_evidence("validation of analytical procedures", S4Topic.METHOD_VALIDATION)
    assert finding.regulatory_evidence and finding.citations
    assert finding.regulatory_evidence[0].metadata.ctd_section in {"3.2.S.4.3", "3.2.S.4", "3.2.S"}


def test_s4_empty_kb(empty_service):
    findings = S4ControlAgent(empty_service).assess("specification tests", "specification")
    assert findings[0].evidence_status == EvidenceStatus.EMPTY_KNOWLEDGE_BASE
    assert findings[0].qa_status == QAStatus.UNSUPPORTED



@pytest.mark.parametrize(
    "text, expected",
    [
        ("NMT 0.10%", (None, Decimal("0.10"), "%")),
        ("Not less than 98.0 %", (Decimal("98.0"), None, "%")),
        ("98.0 - 102.0 % w/w", (Decimal("98.0"), Decimal("102.0"), "% w/w")),
        ("≤ 500 ppm", (None, Decimal("500"), "ppm")),
        ("Complies with reference", (None, None, None)),
        ("98.0 % - 102.0 ppm", (None, None, None)),
    ],
)
def test_parse_criterion_text(text, expected):
    assert parse_criterion_text(text) == expected


def test_unit_conversion_rules():
    assert convert(Decimal("0.05"), "% w/w", "ppm") == Decimal("500")
    assert convert(Decimal("1"), "mg/g", "%w/w") == Decimal("0.1")
    assert convert(Decimal("1"), "%", "ppm") is None
    assert convert(Decimal("1"), "°C", "ppm") is None
    assert convert(Decimal("1"), "µg/g", "ppm") == Decimal("1")


def test_invalid_criterion_rejected():
    with pytest.raises(ValueError):
        AcceptanceCriterion(test_name="x", lower_limit="5", upper_limit="1", unit="%")
    with pytest.raises(ValueError, match="cite"):
        AcceptanceCriterion(test_name="x", upper_limit="1", unit="%", source="regulatory")



@pytest.mark.parametrize(
    "value, unit, outcome",
    [
        ("0.05", "%", Outcome.WITHIN_CRITERIA),
        ("0.10", "%", Outcome.WITHIN_CRITERIA),
        ("0.12", "%", Outcome.OUTSIDE_CRITERIA),
        ("<0.05", "%", Outcome.WITHIN_CRITERIA),
        ("<0.5", "%", Outcome.NOT_COMPARED),
        ("ND", "%", Outcome.NOT_COMPARED),
        ("Complies", "%", Outcome.NOT_COMPARED),
        ("0,05", "%", Outcome.NOT_COMPARED),
        ("0.05", None, Outcome.NOT_COMPARED),
        ("500", "ppm", Outcome.NOT_COMPARED),
    ],
)
def test_batch_outcomes(value, unit, outcome):
    assert compare_batch_result(batch(value, unit), spec()).outcome == outcome


def test_missing_specification_not_compared():
    row = compare_batch_result(batch("0.05"), None)
    assert row.outcome == Outcome.NOT_COMPARED and "no acceptance criterion" in row.reason


def test_spec_without_unit_not_compared():
    row = compare_batch_result(batch("0.05"), spec(unit=None))
    assert row.outcome == Outcome.NOT_COMPARED and "no unit" in row.reason


def test_non_numeric_spec_not_compared():
    row = compare_batch_result(batch("0.05"), AcceptanceCriterion.from_text("Impurity A", "Report result"))
    assert row.outcome == Outcome.NOT_COMPARED


def test_mass_fraction_conversion_used_when_explicit():
    row = compare_batch_result(batch("400", "ppm"), spec(unit="% w/w", upper_limit="0.05"))
    assert row.outcome == Outcome.WITHIN_CRITERIA


def test_borderline_flagged():
    row = compare_batch_result(batch("101.96", "% w/w", "Assay"),
                               AcceptanceCriterion.from_text("Assay", "98.0 - 102.0 % w/w"))
    assert row.outcome == Outcome.WITHIN_CRITERIA and row.borderline


def test_exclusive_limit():
    row = compare_batch_result(batch("0.10"), spec(upper_inclusive=False))
    assert row.outcome == Outcome.OUTSIDE_CRITERIA


def test_batch_finding_structure_and_redaction(service):
    sponsor = [SponsorEvidence(evidence_id="SP-T1", content="confidential table")]
    finding = S4ControlAgent(service).compare_batch_results(
        [spec()], [batch("0.05"), batch("0.20", bid="B2"), batch("0.05", test="Unknown test", bid="B3")], sponsor
    )
    assert isinstance(finding, Finding)
    assert finding.ctd_section == "3.2.S.4.4"
    assert finding.evidence_status == EvidenceStatus.NOT_APPLICABLE
    assert finding.qa_status == QAStatus.HUMAN_REVIEW
    assert finding.metadata["comparison_counts"] == {
        "within_criteria": 1, "outside_criteria": 1, "at_least_as_strict": 0, "less_strict": 0, "not_compared": 1
    }
    assert "does not establish" in finding.conclusion
    redacted = json.dumps(finding.model_dump_redacted())
    assert "0.20" not in redacted and "confidential table" not in redacted


def test_all_within_is_partial_not_verified(service):
    finding = S4ControlAgent(service).compare_batch_results([spec()], [batch("0.05")])
    assert finding.qa_status == QAStatus.PARTIAL


def test_duplicate_spec_for_same_test_is_ambiguous(service):
    finding = S4ControlAgent(service).compare_batch_results([spec(), spec(upper_limit="0.2")], [batch("0.05")])
    assert finding.metadata["comparison_counts"]["not_compared"] == 1



def reg(**kw):
    base = {"test_name": "Impurity A", "upper_limit": "0.15", "unit": "%", "source": "regulatory",
            "citation_chunk_id": "syn-spec-1"}
    base.update(kw)
    return AcceptanceCriterion(**base)


def test_spec_vs_regulatory_outcomes():
    assert compare_spec_to_regulatory(spec(), reg(), True).outcome == Outcome.AT_LEAST_AS_STRICT
    assert compare_spec_to_regulatory(spec(upper_limit="0.2"), reg(), True).outcome == Outcome.LESS_STRICT
    assert compare_spec_to_regulatory(spec(), reg(), False).outcome == Outcome.NOT_COMPARED
    assert compare_spec_to_regulatory(spec(), reg(unit="ppm", upper_limit="1500"), True).outcome == Outcome.NOT_COMPARED


def test_regulatory_comparison_cites_kb_passage(service):
    finding = S4ControlAgent(service).compare_with_regulatory_limits([spec()], [reg()])
    assert [c.chunk_id for c in finding.citations] == ["syn-spec-1"]
    assert finding.regulatory_evidence[0].retrieval_method == "direct_lookup"
    assert finding.regulatory_evidence[0].retrieval_score is None
    assert finding.qa_status == QAStatus.HUMAN_REVIEW


def test_regulatory_limit_with_unknown_citation(service):
    finding = S4ControlAgent(service).compare_with_regulatory_limits([spec()], [reg(citation_chunk_id="nope")])
    assert finding.citations == []
    assert finding.metadata["comparison_counts"]["not_compared"] == 1
    assert "not found in the knowledge base" in finding.uncertainty



def test_run_with_parameters(service):
    req = AgentRequest(
        ctd_section="3.2.S.4.4",
        assessment_question="batch analyses representative batches",
        parameters={
            "specification": [{"test_name": "Impurity A", "upper_limit": "0.10", "unit": "%"}],
            "batch_results": [{"batch_id": "B1", "test_name": "Impurity A", "reported_value": "0.05", "unit": "%"}],
        },
    )
    findings = S4ControlAgent(service).run(req)
    assert len(findings) == 2
    assert findings[0].metadata["s4_topic"] == "batch_analyses"
    assert all(f.qa_status != QAStatus.VERIFIED for f in findings)


def test_run_regulatory_limits_default_to_regulatory_source(service):
    def run(limit):
        return S4ControlAgent(service).run(AgentRequest(
            ctd_section="3.2.S.4.1", assessment_question="specification tests and acceptance criteria",
            parameters={"specification": [{"test_name": "Impurity A", "upper_limit": "0.10", "unit": "% w/w"}],
                        "regulatory_limits": [limit]}))


    findings = run({"test_name": "Impurity A", "upper_limit": "0.15", "unit": "% w/w", "citation_chunk_id": "nope"})
    assert findings[-1].metadata["comparison_counts"]["not_compared"] == 1
    assert "not found in the knowledge base" in findings[-1].uncertainty
    with pytest.raises(ValueError, match=r"invalid S\.4 parameters"):
        run({"test_name": "Impurity A", "upper_limit": "0.15", "unit": "% w/w"})


def test_run_invalid_parameters_do_not_echo_values(service):
    req = AgentRequest(ctd_section="3.2.S.4.4", assessment_question="q",
                       parameters={"batch_results": [{"batch_id": "B1", "test_name": "T", "unit": "%",
                                                      "reported_value": "SECRET-123", "extra": 1}]})
    with pytest.raises(ValueError) as exc:
        S4ControlAgent(service).run(req)
    assert "SECRET-123" not in str(exc.value)


def test_example_request_file_is_valid(service):
    from pathlib import Path

    data = json.loads((Path(__file__).parent.parent / "examples" / "s4_request.example.json").read_text())
    findings = S4ControlAgent(service).run(AgentRequest(**data))
    counts = findings[1].metadata["comparison_counts"]
    assert counts["within_criteria"] == 4 and counts["not_compared"] == 1
