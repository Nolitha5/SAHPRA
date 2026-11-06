from datetime import date
import pytest
from m2.schemas import SourceRecord, SourceType, EvidenceFilters, RegulatoryChunk
from m2.registry import SourceRegistry
from m2.chunking import section_chunks


def test_source_approved_and_provenance_gate():
    src=SourceRecord(source_id="s",authority="ICH",title="Demo",document_code="Q6A",version="v1")
    registry=SourceRegistry([src])
    assert not registry.eligible(src,EvidenceFilters(),False)
    src.approved=True
    assert not registry.eligible(src,EvidenceFilters(),False)
    src.provenance_verified=True
    assert registry.eligible(src,EvidenceFilters(),False)


def test_temporal_filter_denies_unknown_or_nonapplicable():
    src=SourceRecord(source_id="s",authority="ICH",title="Demo",document_code="Q6A",version="v1",approved=True,provenance_verified=True)
    registry=SourceRegistry([src])
    assert not registry.eligible(src,EvidenceFilters(effective_on=date(2025,1,1)),False)
    src.effective_from=date(2024,1,1);src.effective_to=date(2024,12,31)
    assert not registry.eligible(src,EvidenceFilters(effective_on=date(2025,1,1)),False)
    assert registry.eligible(src,EvidenceFilters(effective_on=date(2024,6,1)),False)


def test_sporadic_sponsor_source_cannot_pass():
    src=SourceRecord(source_id="s",authority="SPONSOR",title="Sponsor",document_code="SPON",version="1",approved=True,provenance_verified=True,source_type=SourceType.SPONSOR)
    assert not SourceRegistry([src]).eligible(src,EvidenceFilters(),True)


def test_immutable_reuse_of_source_id():
    registry=SourceRegistry()
    a=SourceRecord(source_id="id",authority="ICH",title="Q6A",document_code="Q6A",version="1")
    registry.register(a);registry.register(a)
    with pytest.raises(ValueError):registry.register(a.model_copy(update={"version":"2"}))


def test_chunks_respect_ctd_section_breaks():
    page='3.2.S.4.1 Specifications test one two three four five\n3.2.S.4.2 Analytical procedures six seven eight nine'
    chunks=section_chunks('r',[(1,page)],size=20,overlap=2)
    assert len(chunks)==2
    assert chunks[0].section=='3.2.S.4.1' and chunks[1].section=='3.2.S.4.2'
    assert 'Analytical' not in chunks[0].text
    assert chunks==section_chunks('r',[(1,page)],size=20,overlap=2)


def test_chunks_page_locators():
    chunks=section_chunks('r',[(1,'alpha beta gamma delta'),(2,'epsilon zeta')],size=3,overlap=1)
    assert {c.page for c in chunks}=={1,2}
    assert len({c.chunk_id for c in chunks})==len(chunks)


def test_bad_chunking_configuration():
    with pytest.raises(ValueError):section_chunks('x',[(1,'hello')],size=2,overlap=2)


def test_register_source_does_not_need_gpu_or_vector_backend(tmp_path):
    import json
    from m2.cli import main
    cfg=tmp_path/'config.json'
    cfg.write_text(json.dumps({'mode':'research','backend':'chroma','embedding_model':'BAAI/bge-large-en-v1.5',
        'registry_path':str(tmp_path/'sources.json')}))
    source=SourceRecord(source_id='placeholder',authority='ICH',title='Test',document_code='Q6A',version='unverified')
    path=tmp_path/'source.json';path.write_text(source.model_dump_json())
    main(['--config',str(cfg),'register-source','--input',str(path)])
    assert SourceRegistry.load(tmp_path/'sources.json').get('placeholder').source_id=='placeholder'
