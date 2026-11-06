from pathlib import Path
from types import SimpleNamespace
import fitz
import pytest
from m2.pharmacopoeia import PharmacopoeiaCatalogue
from m2.phint_acquisition import trusted,publisher_candidates,verify_pdf_bytes,acquire,acquire_four

CAT=Path(__file__).resolve().parents[1]/'pharmacopoeia/WHO_PHINT_RESEARCH_CATALOGUE_v0.7.json'

def catalogue():return PharmacopoeiaCatalogue.load(CAT)

def pdf_bytes(substance,cas):
 doc=fitz.open();p=doc.new_page();p.insert_text((55,70),f'{substance} CAS Reg. No. {cas}')
 p.insert_text((55,95),'The International Pharmacopoeia - Twelfth Edition 2025.')
 p.insert_text((55,115),'Synthetic test data ONLY: no pharmaceutical reference requirements.')
 payload=doc.tobytes();doc.close();return payload

class Response:
 def __init__(self, url, content, status_code=200):
  self.url=url;self.content=content;self.status_code=status_code;self.history=[]
  self.ok=status_code==200;self.text=content.decode('utf-8','ignore')
 def raise_for_status(self):
  if self.status_code>=400:raise ValueError('simulated unavailable document')

class FakeSession:
 def __init__(self, entry, payload, *, candidates=None):
  self.entry=entry;self.payload=payload;self.calls=[];self.candidates=candidates or []
 def get(self,url,**kw):
  self.calls.append(url)
  if url==self.entry.online_url:
   return Response(url,f'<html><a href="{self.entry.pdf_url}">Open section in PDF format</a></html>'.encode())
  return Response(url,self.payload)

def test_expected_candidate_urls_and_cas():
 cat=catalogue();api=[e for e in cat.entries if e.kind=='API_MONOGRAPH']
 assert len(api)==4 and all(e.pdf_url for e in api)
 assert cat.by_id['WHO-PHINT-METRONIDAZOLE-API'].cas == '443-48-1'
 assert 'Metronidazole-%28Metronidazolum%29.pdf' in cat.by_id['WHO-PHINT-METRONIDAZOLE-API'].pdf_url

def test_trusted_host_blocks_http_and_lookalikes():
 assert trusted('https://digicollections.net/phint/pdf/test.pdf')
 assert not trusted('https://digicollections.net.bad.org/path.pdf')
 assert not trusted('http://digicollections.net/path.pdf')
 assert not trusted('https://user:pass@digicollections.net/path')

def test_pdf_candidates_extracted_only_from_who():
 e=catalogue().entries[0]
 html='<a href="https://evil.org/a.pdf">Download</a><a href="/phint/pdf/test.pdf">Open section in PDF format</a>'
 u=publisher_candidates(e,html)
 assert any(x.endswith('/phint/pdf/test.pdf') for x in u)
 assert not any('evil.org' in x for x in u)

def test_pdf_identity_and_cas_accepts_matching():
 e=catalogue().entries[0]
 chk=verify_pdf_bytes(e,pdf_bytes(e.substance,e.cas))
 assert chk['pages']==1 and len(chk['sha256'])==64
 assert not chk['edition_and_regulatory_applicability_approved']

def test_rejects_misleading_pdf_of_different_substance():
 e=catalogue().entries[0]
 with pytest.raises(ValueError,match='identity'):
  verify_pdf_bytes(e,pdf_bytes('Ibuprofen','15687-27-1'))

def test_rejects_identity_match_with_wrong_cas():
 e=catalogue().entries[0]
 with pytest.raises(ValueError,match='CAS'):
  verify_pdf_bytes(e,pdf_bytes('Paracetamol','000-00-0'))

def test_rejects_invalid_pdf():
 e=catalogue().entries[0]
 with pytest.raises(ValueError):verify_pdf_bytes(e,b'<html/>')

def test_acquire_success_preserves_review_pending_and_receipt(tmp_path):
 e=catalogue().entries[0]; fake=FakeSession(e,pdf_bytes(e.substance,e.cas))
 a=acquire(e,tmp_path,session=fake)
 assert a['status']=='DOWNLOADED_PENDING_REVIEW'
 assert (tmp_path/f'{e.id}.pdf').is_file()
 assert (tmp_path/f'{e.id}.acquisition.json').is_file()
 assert acquire(e,tmp_path,session=fake)['status']=='PRESENT_PENDING_REVIEW'

def test_acquire_wrong_pdf_does_not_persist(tmp_path):
 e=catalogue().entries[0]; fake=FakeSession(e,pdf_bytes('Ibuprofen','15687-27-1'))
 a=acquire(e,tmp_path,session=fake)
 assert a['status']=='DOWNLOAD_FAILED_OR_SOURCE_UNVERIFIED'
 assert not (tmp_path/f'{e.id}.pdf').exists()

def test_acquire_all_four_with_mocked_whopdfs(tmp_path):
 cat=catalogue()
 class Session:
  def get(self,url,**kw):
   for e in cat.entries:
    if e.kind!='API_MONOGRAPH':continue
    if url==e.online_url:return Response(url,(f'<a href="{e.pdf_url}">Open section in PDF format</a>').encode())
    if url==e.pdf_url:return Response(url,pdf_bytes(e.substance,e.cas))
   return Response(url,b'',404)
 r=acquire_four(cat,tmp_path,session=Session())
 assert r['requested']==4 and r['present']==4
 assert r['status']=='PENDING_REVIEW_NOT_AUTHORITATIVE'

def test_local_manual_pdf_registration(tmp_path):
    import importlib.util
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('add_local_phint',root/'scripts/add_local_who_pdf.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    entry=catalogue().entries[0]
    incoming=tmp_path/'external.pdf';incoming.write_bytes(pdf_bytes(entry.substance,entry.cas))
    r=module.register(incoming,entry.id,tmp_path/'pending')
    assert r['status']=='MANUALLY_SUPPLIED_PENDING_REVIEW'
    assert Path(r['retained']).exists()
    assert r['edition_and_regulatory_applicability_approved'] is False
