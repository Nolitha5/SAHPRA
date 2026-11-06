"""M5 expert-label import, independent checks and explicit validation boundaries.

A structured record is NOT automatically 'expert validated'. M5 must sign off the
actual review and record the appropriate evidence in its own project governance.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
from pydantic import BaseModel, Field, model_validator
from .experiments import AnchoredGoldQuery
from .registry import SourceRegistry, file_sha256

class ReviewRecord(BaseModel):
    reviewer_id: str = Field(min_length=2)
    reviewer_role: str = Field(min_length=2)
    reviewed_at_iso: str
    review_basis: str = Field(min_length=12)
    decision: str
    @model_validator(mode='after')
    def verify(self):
        datetime.fromisoformat(self.reviewed_at_iso.replace('Z','+00:00'))
        if self.decision not in {'APPROVED','REVISION_REQUIRED','REJECTED'}:raise ValueError('Invalid review decision')
        return self

class LabelBundle(BaseModel):
    dataset_name: str
    dataset_version: str
    labels: list[AnchoredGoldQuery]
    review_records: list[ReviewRecord] = Field(default_factory=list)
    created_from: str = 'RESEARCHER_DRAFT_NOT_EXPERT_VALIDATED'

    @model_validator(mode='after')
    def distinct_questions(self):
        ids=[q.query_id for q in self.labels]
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate query IDs')
        return self


def assess_labels(file: str|Path, registry_file: str|Path, pdf_dir: str|Path) -> dict:
    bundle=LabelBundle.model_validate_json(Path(file).read_text(encoding='utf-8'))
    registry=SourceRegistry.load(registry_file)
    misses=[]
    for q in bundle.labels:
        for anchor in q.relevant:
            source=registry.records.get(anchor.source_id)
            if source is None or not source.approved or not source.provenance_verified:
                misses.append({'query_id':q.query_id,'source_id':anchor.source_id,'problem':'source not approved/verified'})
                continue
            pdf=Path(pdf_dir)/f'{anchor.source_id}.pdf'
            if not pdf.exists() or not source.sha256 or source.sha256!=file_sha256(pdf):
                misses.append({'query_id':q.query_id,'source_id':anchor.source_id,'problem':'source PDF absent or hash mismatch'})
                continue
            if anchor.page is not None:
                import fitz
                with fitz.open(pdf) as doc:
                    if anchor.page<1 or anchor.page>len(doc):
                        misses.append({'query_id':q.query_id,'source_id':anchor.source_id,'problem':'page outside source bounds'})
    approvals=[r for r in bundle.review_records if r.decision=='APPROVED']
    reviewer_ids={r.reviewer_id for r in approvals}
    status=('ATTESTED_WITH_SOURCE_VERIFICATION' if not misses and len(reviewer_ids)>=2 and len(bundle.labels)>=1
            else 'NOT_EXPERT_VERIFIED')
    # Even ATTESTED records are only an attestation, not independent proof of credentials.
    return {'dataset':bundle.dataset_name,'version':bundle.dataset_version,'query_count':len(bundle.labels),
            'reviewer_approvals':len(reviewer_ids),'source_issues':misses,
            'status':status,'caution':'Research team must verify reviewer identities and qualifications out-of-band.'}


def template(path:str|Path):
    obj={'dataset_name':'SAHPRA-RKB-expert-labels','dataset_version':'draft-0',
         'created_from':'RESEARCHER_DRAFT_NOT_EXPERT_VALIDATED',
         'review_records':[],
         'labels':[{'query_id':'replace-me','question':'Replace with a real expert query',
                    'relevant':[{'source_id':'REPLACE_WITH_APPROVED_ID','section':None,'page':None}],
                    'filters':{'authorities':[],'document_codes':[],'sections':[],'effective_on':None,'include_literature':False}}]}
    dest=Path(path);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(obj,indent=2),encoding='utf-8')
    return dest
