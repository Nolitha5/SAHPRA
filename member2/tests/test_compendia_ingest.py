from pathlib import Path
import zipfile
import json
import fitz
from m2.compendia_ingest import safe_entry,clean_html,init_db,search_unverified,build_discovery,detect_edition,ARCHIVE_SPECS


def test_sanitize_html():
    title,body=clean_html(b'<html><title>Ibuprofen - British Pharmacopoeia</title><script>EVIL</script><article>Identity. Assay specifications.</article></html>')
    assert 'Ibuprofen' in title and 'EVIL' not in body and 'Assay' in body

def test_edition_detection():
    assert '11.0' in detect_edition('PH_EUR_EXTRACT','EUROPEAN PHARMACOPOEIA 11.0')
    assert '2024' in detect_edition('BP_HTML','Home BP 2024 (Ph. Eur. 11.3 update)')

def test_unsafe_entries():
    with zipfile.ZipFile(Path(__file__).parent/'mini.zip','w') as z:
        z.writestr('../bad.html','bad');z.writestr('ok.html','<html>okay</html>')
    with zipfile.ZipFile(Path(__file__).parent/'mini.zip') as z:
        assert not safe_entry(z.getinfo('../bad.html'))
        assert safe_entry(z.getinfo('ok.html'))
    (Path(__file__).parent/'mini.zip').unlink()

def test_reference_only_default(tmp_path):
    db=tmp_path/'q.sqlite3';con=init_db(db);con.close()
    result=search_unverified(db,'ibuprofen')
    assert result['hits']==[] and not result['regulatory_evidence']

def test_zip_build_search_and_no_promote(tmp_path):
    source=tmp_path/'source';source.mkdir()
    z=source/'general-notices [webofpharma.com].zip'
    with zipfile.ZipFile(z,'w',compression=zipfile.ZIP_DEFLATED) as w:
        w.writestr('part-i.html','<title>General Notice</title><article>Ibuprofen specification reference is only illustrative.</article>')
    db=tmp_path/'idx.sqlite3'
    report=build_discovery(source,db,selected=[z.name])
    assert report['new_documents']==1 and not report['regulatory_approval']
    result=search_unverified(db,'ibuprofen',include_unreviewed=True)
    assert result['hits'] and not result['regulatory_evidence']
    assert result['hits'][0]['review_status'].startswith('QUARANTINED')

def test_duplicate_html_archives_do_not_double_count(tmp_path):
    folder=tmp_path/'data';folder.mkdir()
    names=['general-notices [webofpharma.com].zip','general-notices [webofpharma.com](1).zip']
    for name in names:
        with zipfile.ZipFile(folder/name,'w') as z:
            z.writestr('a.html','<article>Stable content demonstrating general notices for quality assessors</article>')
    rep=build_discovery(folder,tmp_path/'db.sqlite3',selected=names)
    assert rep['counts']['documents']==1 and rep['duplicate_file_entries_skipped']==1


def test_topic_filter_excludes_wrong_reference(tmp_path):
    source=tmp_path/'src';source.mkdir()
    with zipfile.ZipFile(source/'New folder (4).zip','w') as z:
        z.writestr('capsules.html','<article>Ibuprofen Capsules finished dosage form</article>')
    with zipfile.ZipFile(source/'New folder (8).zip','w') as z:
        z.writestr('api.html','<article>Ibuprofen API drug substance analytical specification</article>')
    db=tmp_path/'idx.db'
    build_discovery(source,db,selected=['New folder (4).zip','New folder (8).zip'])
    result=search_unverified(db,'Ibuprofen',topic='SUBSTANCE_MONOGRAPH',include_unreviewed=True)
    assert len(result['hits'])==1 and result['hits'][0]['topic']=='SUBSTANCE_MONOGRAPH'
