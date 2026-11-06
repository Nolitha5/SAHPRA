"""Independent byte-hash + passage-to-original-page audit of M2 research references.

Audits only exact extractive anchors in locally supplied PDFs. Successful results
DO NOT imply regulatory applicability, monograph licensing, or expert relevance.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import json
import fitz
from .schemas import RegulatoryChunk
from .technical_benchmark import source_pdf_map, verify_chunks


def audit_pdf_passages(root:Path, index:Path|None=None) -> dict:
    root=Path(root)
    index=Path(index) if index else root/'artifacts/real_corpus'
    manifest=json.loads((index/'REAL_CORPUS_MANIFEST.json').read_text(encoding='utf-8'))
    chunks=[RegulatoryChunk.model_validate_json(s) for s in
            (index/'REGULATORY_CHUNKS.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
    verify_chunks(chunks,manifest)
    pdf_paths=source_pdf_map(root,manifest)  # checks SHA-256 against the original bytes
    by_source={}
    for c in chunks:
        by_source.setdefault(c.source_id,[]).append(c)
    findings=[]
    audited=0
    docs=[]
    for src in manifest['sources']:
        sid=src['source_id']
        with fitz.open(pdf_paths[sid]) as pdf:
            if len(pdf)!=src['page_count']:
                raise ValueError(f'Page count changed for {sid}')
            page_text={}
            for c in by_source[sid]:
                if c.page not in page_text:
                    page_text[c.page]=' '.join(pdf[c.page-1].get_text(sort=True).split())
                # Corpus chunker normalizes whitespace when creating stored chunks.
                test=' '.join(c.text.split())
                if test not in page_text[c.page]:
                    findings.append({'source_id':sid,'pdf_page':c.page,
                                     'chunk_id':c.chunk_id,'issue':'PASSAGE_NOT_ON_CITED_PDF_PAGE'})
                audited+=1
        docs.append({'source_id':sid,'hash_verified':True,
                     'pages':src['page_count'],
                     'audited_chunks':len(by_source[sid]),
                     'regulatory_approved':False})
    return {'status':'PASS_ANCHORED_TECHNICAL_AUDIT' if not findings else 'FAIL_UNANCHORED_PASSAGES',
            'pdfs_sha256_verified':len(docs),
            'passages_audited':audited,
            'unanchored_passages':len(findings),
            'errors':findings[:30],
            'source_summary':docs,
            'expert_relevance_review':False,
            'pharmacopoeia_review':False,
            'regulatory_decision_ready':False,
            'limitations':'Passage presence on original page is technical provenance, not expert assessment of guideline applicability.'}
