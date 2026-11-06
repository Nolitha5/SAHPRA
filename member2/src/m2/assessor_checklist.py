"""Nonbinding IPRP QWGG 2018 quality-assessor check prompts (review aid, not verdict)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

# Items paraphrase supplied IPRP QWGG v1.1 guidance; citations are PDF physical pages.
CHECKS = {
 '3.2.S.4.1': [
    ('proposed_specification','Record tests, acceptance criteria and specification version',14),
    ('compendial_claim','Record whether claimed standard is compendial or in-house',14),
    ('manufacturer_boundary','Distinguish the substance and drug-product manufacturer specifications',14)],
 '3.2.S.4.2': [
    ('analytical_methods','Determine whether methods follow a monograph or are in-house',15),
    ('method_description','Verify that descriptions and system suitability details are provided',15)],
 '3.2.S.4.3': [
    ('validation_evidence','Identify supporting validation information for in-house methods',15),
    ('method_equivalence','Identify comparative justification if a pharmacopoeial method is replaced',15)],
 '3.2.S.4.4': [
    ('batch_details','Record batch numbers, sites, manufacturing dates and sizes',16),
    ('numeric_results','Summarise numeric assay/impurity results and patterns rather than a blanket statement',16)],
 '3.2.S.4.5': [
    ('acceptance_justification','Document justification of tests, limits and any omitted tests',16),
    ('product_context','Record administration route and dose context before applicable limit assessment',17)],
 '3.2.S.5': [
    ('reference_standard_source','Identify primary, working and impurity standards, source and batch',18),
    ('reference_standard_evidence','Record certificates, purity assignments and characterisation where applicable',18)]
}


def prompts(section: str, *, extracted_sponsor_fields: dict[str, Any] | None = None) -> dict:
    """Creates questions/coverage state only; never auto-decides compliance."""
    fields=extracted_sponsor_fields or {}
    values=[]
    for key,desc,page in CHECKS.get(section, []):
        evidence=fields.get(key)
        values.append({'field':key,'assessment_question':desc,'supplied_evidence':evidence,
                       'capture_state':'REPORTED' if evidence is not None else 'NEEDS_REVIEW',
                       'guide_citation':f'IPRP QWGG Guidance for Quality Assessors – Drug Substance v1.1, PDF page {page}',
                       'source_binding':'NONBINDING_MODEL_GUIDANCE'})
    return {'ctd_section':section,'checklist':values,'decision':'HUMAN_ASSESSMENT_REQUIRED',
            'regulatory_verdict':None,'citation_status':'NONBINDING_ASSISTIVE_GUIDANCE',
            'message':'Prompts do not establish a regulatory requirement or compliance outcome.'}
