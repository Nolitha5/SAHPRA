from datetime import date
import pytest
from m2.schemas import EvidenceRequest,EvidenceFilters,EvidenceStatus,SourceType,SourceRecord,RegulatoryChunk
from m2.runtime import AppConfig,M2Runtime
from m2.registry import SourceRegistry


def q(query,**kw):return EvidenceRequest(request_id='r',question=query,requesting_agent='test',**kw)

def test_retrieve_citation_and_provenance(demo):
    res=demo.evidence.retrieve(q('analytical validation accuracy precision'))
    assert res.status==EvidenceStatus.FOUND
    assert res.evidence[0].authority=='TEST_ONLY'
    assert res.evidence[0].provenance_verified
    assert res.evidence[0].chunk_id=='synthetic-validation'
    assert '2026-demo-v1' in res.evidence[0].citation
    assert res.evidence[0].is_synthetic


def test_insufficient_when_no_topic(demo):
    res=demo.evidence.retrieve(q('galactic vaccine camel starlight extraterrestrial quasar'))
    assert res.status==EvidenceStatus.INSUFFICIENT_EVIDENCE
    assert res.requires_human_review and not res.evidence


def test_source_authority_filter(demo):
    res=demo.evidence.retrieve(q('analytical validation accuracy precision',filters=EvidenceFilters(authorities=['ICH'])))
    assert res.status==EvidenceStatus.INSUFFICIENT_EVIDENCE


def test_source_code_filter(demo):
    res=demo.evidence.retrieve(q('analytical validation accuracy precision',filters=EvidenceFilters(document_codes=['Q2'])))
    assert res.status==EvidenceStatus.INSUFFICIENT_EVIDENCE


def test_section_filter(demo):
    res=demo.evidence.retrieve(q('analytical validation accuracy precision',filters=EvidenceFilters(sections=['test-specification'])))
    assert res.status==EvidenceStatus.INSUFFICIENT_EVIDENCE


def test_effective_date_filter_requires_evidence(demo):
    res=demo.evidence.retrieve(q('analytical validation accuracy precision',filters=EvidenceFilters(effective_on=date(2026,1,1))))
    assert res.status==EvidenceStatus.INSUFFICIENT_EVIDENCE


def test_no_synthetic_when_production_flag_false(demo):
    demo.evidence.config.allow_synthetic=False
    assert demo.evidence.retrieve(q('analytical validation accuracy precision')).status==EvidenceStatus.INSUFFICIENT_EVIDENCE


def test_tampering_chunks_source_rejected(demo):
    with pytest.raises(ValueError):
        demo.index([RegulatoryChunk(chunk_id='fraud',source_id='fake',section='X',text='Fiction')])


def test_sponsor_material_rejected_at_index(demo):
    source=SourceRecord(source_id='bad',authority='SPONSOR',title='Dossier',document_code='SPON',version='1',approved=True,provenance_verified=True,source_type=SourceType.SPONSOR)
    demo.registry.register(source)
    with pytest.raises(ValueError):demo.index([RegulatoryChunk(chunk_id='x',source_id='bad',section='3.2.S.4.1',text='some text')])


def test_production_mode_rejects_demo_configuration():
    with pytest.raises(ValueError): M2Runtime(AppConfig(mode='research',allow_synthetic=True))


def test_index_is_idempotent(demo):
    count=demo.store.count()
    demo.store.upsert(demo.store.all_chunks())
    assert demo.store.count()==count


def test_backend_invalid():
    with pytest.raises(ValueError):M2Runtime(AppConfig(backend='not_a_store'))


def test_corrupted_store_error_is_not_legal_absence(demo):
    def failure(*_):raise RuntimeError('down')
    demo.store.all_chunks=failure
    result=demo.evidence.retrieve(q('analytical validation accuracy precision'))
    assert result.status==EvidenceStatus.ERROR
    assert result.requires_human_review


def test_literature_never_substitutes_for_regulation_by_default(demo):
    src=SourceRecord(source_id='paper',authority='JOURNAL',title='Scientific publication',document_code='PAPER',version='2026',approved=True,provenance_verified=True,source_type=SourceType.LITERATURE)
    demo.registry.register(src)
    demo.index([RegulatoryChunk(chunk_id='paper1',source_id='paper',section='article-1',text='literature assay analysis reproducibility evidence')])
    result=demo.evidence.retrieve(q('literature assay analysis reproducibility evidence'))
    assert all(p.source_id!='paper' for p in result.evidence)
    with_literature=demo.evidence.retrieve(q('literature assay analysis reproducibility evidence',filters=EvidenceFilters(include_literature=True)))
    assert any(p.source_id=='paper' and p.source_type==SourceType.LITERATURE for p in with_literature.evidence)
