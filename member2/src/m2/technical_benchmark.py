"""Reproducible engineering-only retrieval benchmark against real uploaded PDFs.

The queries are AUTHOR-CREATED NAVIGATION PROBES, not expert-labelled regulatory
relevance judgements. Metrics are source/page locator probes, never a claim of
compliance accuracy or evidence relevance for actual dossiers.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import math
import re

import numpy as np
import fitz
from .schemas import RegulatoryChunk
from .real_corpus import hash_file

TOKEN = re.compile(r"[a-z0-9]+")


def words(value: str) -> list[str]:
    return TOKEN.findall(value.lower())


def source_pdf_map(root: Path, manifest: dict) -> dict[str, Path]:
    mapping = {}
    folders = [root / 'regulatory_sources/user_supplied_unapproved',
               root / 'regulatory_sources/additional_unapproved']
    for source in manifest['sources']:
        matches = [base / source['pdf_file'] for base in folders
                   if (base / source['pdf_file']).is_file()]
        if len(matches) != 1 or hash_file(matches[0]) != source['sha256']:
            raise ValueError(f"PDF missing or hash mismatch: {source['source_id']}")
        mapping[source['source_id']] = matches[0]
    return mapping


def verify_probes(root: Path, manifest: dict, probes: list[dict[str, Any]]) -> list[dict]:
    """Confirm each claimed topic is literally discoverable in its source PDF.

    The returned page is only a text-location anchor, NOT an expert ground truth.
    """
    mapping = source_pdf_map(root, manifest)
    resolved = []
    for probe in probes:
        sid = probe['expected_source_id']
        if sid not in mapping:
            raise ValueError(f'Unknown source: {sid}')
        if len(probe.get('question', '')) < 8:
            raise ValueError('Short/uninformative navigation probe')
        phrase = probe['source_anchor_phrase'].lower()
        with fitz.open(mapping[sid]) as pdf:
            pages = [i+1 for i, page in enumerate(pdf)
                     if phrase in ' '.join(page.get_text(sort=True).lower().split())]
        if not pages:
            raise ValueError(f"Anchor not present in PDF: {sid} => {phrase}")
        # Prefer an actual substantive page over the front matter/TOC wherever possible.
        page = next((p for p in pages if p >= 6), pages[-1])
        resolved.append(dict(probe, anchor_pdf_page=page,
                             all_anchor_pdf_pages=pages))
    return resolved


def verify_chunks(chunks: list[RegulatoryChunk], manifest: dict):
    known = {s['source_id']: s for s in manifest['sources']}
    if len(chunks) != manifest['indexed_chunk_count']:
        raise ValueError('Chunk count differs from manifest')
    if len({c.chunk_id for c in chunks}) != len(chunks):
        raise ValueError('Duplicate chunk ids')
    for chunk in chunks:
        source = known.get(chunk.source_id)
        if not source:
            raise ValueError(f'Unknown chunk source: {chunk.source_id}')
        if chunk.page is None or chunk.page > source['page_count']:
            raise ValueError(f'Invalid chunk page: {chunk.source_id}:{chunk.page}')
    for sid in known:
        if not any(c.source_id == sid for c in chunks):
            raise ValueError(f'Missing indexed source: {sid}')


@dataclass
class NavigationRanker:
    chunks: list[RegulatoryChunk]

    def __post_init__(self):
        texts = [c.text for c in self.chunks]
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError as exc:
            raise RuntimeError('Install scikit-learn (pip install -e ".[experiment]")') from exc
        self.word_model = TfidfVectorizer(strip_accents='unicode', lowercase=True, ngram_range=(1,2),
                                          min_df=1, sublinear_tf=True, norm='l2')
        self.word_vectors = self.word_model.fit_transform(texts)
        self.char_model = TfidfVectorizer(analyzer='char_wb', ngram_range=(3,5),
                                          min_df=1, sublinear_tf=True, norm='l2')
        self.char_vectors = self.char_model.fit_transform(texts)
        self.terms = [words(t) for t in texts]
        self.tfs = [Counter(w) for w in self.terms]
        self.df = Counter(t for w in self.terms for t in set(w))
        self.avg_length = sum(len(w) for w in self.terms)/max(1,len(self.terms))
        self.lengths = np.array([len(w) for w in self.terms])
        # This is a deterministic token-hash engineering baseline, NOT an embedding model.
        self.hash_dimension = 384
        self.hash_vectors = np.stack([self._hash(text) for text in texts])

    def _hash(self, value: str) -> np.ndarray:
        vec = np.zeros(self.hash_dimension, dtype=np.float32)
        for token in words(value):
            h = hashlib.blake2s(token.encode(), digest_size=8).digest()
            vec[int.from_bytes(h[:4], 'big') % self.hash_dimension] += 1
        norm = np.linalg.norm(vec)
        return vec/norm if norm else vec

    def _bm25(self, query: str) -> np.ndarray:
        N = len(self.chunks)
        out = np.zeros(N, dtype=np.float64)
        for term in set(words(query)):
            df = self.df.get(term,0)
            if not df:
                continue
            idf = math.log(1 + (N-df+0.5)/(df+0.5))
            for i, tf in enumerate(self.tfs):
                f = tf.get(term,0)
                if f:
                    out[i] += idf * (f*2.2)/(f+1.2*(0.25+0.75*self.lengths[i]/max(self.avg_length,1)))
        return out

    @staticmethod
    def _rank(scores: np.ndarray) -> list[int]:
        return sorted(range(len(scores)), key=lambda i:(-scores[i], i))

    def rank(self, query: str, mode: str, top_k: int = 5) -> list[tuple[RegulatoryChunk,float]]:
        if mode=='tfidf_word':
            scores = (self.word_vectors @ self.word_model.transform([query]).T).toarray().ravel()
        elif mode=='tfidf_character':
            scores = (self.char_vectors @ self.char_model.transform([query]).T).toarray().ravel()
        elif mode=='bm25':
            scores = self._bm25(query)
        elif mode=='hash_demo':
            scores = self.hash_vectors @ self._hash(query)
        elif mode=='hybrid_rrf':
            lexical = self._rank(self._bm25(query))
            semantic = self._rank((self.word_vectors @ self.word_model.transform([query]).T).toarray().ravel())
            scores = np.zeros(len(self.chunks), dtype=np.float64)
            for rank, index in enumerate(lexical): scores[index] += .5/(60+rank+1)
            for rank, index in enumerate(semantic): scores[index] += .5/(60+rank+1)
        else:
            raise ValueError(f'Unknown retrieval baseline: {mode}')
        return [(self.chunks[i],float(scores[i])) for i in self._rank(scores)[:top_k]]


def evaluate_navigation(probes: list[dict], outputs: list[list[tuple[RegulatoryChunk,float]]], k:int=5) -> dict:
    if len(probes) != len(outputs):
        raise ValueError('Missing retrieval output for a probe')
    rows=[]
    for probe, results in zip(probes,outputs):
        sources=[c.source_id for c,_ in results[:k]]
        sid=probe['expected_source_id']
        first = next((i+1 for i,x in enumerate(sources) if x == sid),None)
        page=probe['anchor_pdf_page']
        page_hit = any(c.source_id==sid and c.page==page for c,_ in results[:k])
        rows.append({'id':probe['id'],'question':probe['question'],'expected_source_id':sid,
                     'anchor_pdf_page':page,'source_hit_at_1':int(bool(first and first<=1)),
                     'source_hit_at_3':int(bool(first and first<=3)),
                     'source_hit_at_5':int(bool(first and first<=5)),
                     'source_mrr_at_5':round(1/first if first else 0,6),
                     'anchor_page_hit_at_5':int(page_hit),
                     'top5':[{'source_id':c.source_id,'pdf_page':c.page,
                              'section':c.section,'chunk_id':c.chunk_id,
                              'score':round(score,6)} for c,score in results[:k]]})
    avg_keys=['source_hit_at_1','source_hit_at_3','source_hit_at_5','source_mrr_at_5','anchor_page_hit_at_5']
    return {'count':len(rows),'aggregate':{key:round(sum(r[key] for r in rows)/len(rows),4) for key in avg_keys},
            'per_probe':rows,'research_status':'AUTHOR_CREATED_SOURCE_NAVIGATION_ONLY_NOT_EXPERT_LABELS'}


def benchmark_from_files(root: Path, modes: list[str]|None=None,top_k:int=5) -> dict:
    index=root/'artifacts/real_corpus'
    manifest=json.loads((index/'REAL_CORPUS_MANIFEST.json').read_text())
    chunks=[RegulatoryChunk.model_validate_json(line) for line in (index/'REGULATORY_CHUNKS.jsonl').read_text(encoding="utf-8").splitlines() if line.strip()]
    verify_chunks(chunks,manifest)
    suite=json.loads((root/'examples/researcher_navigation_probes_v0.6.json').read_text(encoding="utf-8"))
    probes=verify_probes(root,manifest,suite['probes'])
    ranker=NavigationRanker(chunks)
    modes=modes or ['bm25','hash_demo','tfidf_word','tfidf_character','hybrid_rrf']
    results={}
    for mode in modes:
        outputs=[ranker.rank(probe['question'],mode,top_k) for probe in probes]
        results[mode]=evaluate_navigation(probes,outputs,k=top_k)
    return {'evaluation_type':'RESEARCHER_AUTHORED_NAVIGATION_SMOKE_NOT_EXPERT_GOLD',
            'source_count':len(manifest['sources']),'chunk_count':len(chunks),'k':top_k,
            'source_approvals_granted':False,'regulatory_decision_ready':False,
            'query_count':len(probes),'models':results,
            'limitation':'Document/page locator checks are NOT a measure of regulatory appropriateness, finding accuracy, or expert relevance.'}
